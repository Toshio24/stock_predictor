"""News ingestion worker.

Drives every Source in `app.ingest.sources` on its own cadence:

  - per-ticker sources rotate through tracked symbols and call
    `fetch_per_ticker(symbol)`. Pacing is 1.2s between requests to stay
    under all free-tier rate limits.
  - global sources call `fetch_global(tracked)` once per cadence; the
    regex tagger finds tracked tickers in the headline + summary.

All sources produce `RawArticle`s, which the worker normalizes into
`Article` + `ArticleTicker` rows. The classifier worker picks them up
afterwards. Sources don't touch the DB."""
import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import session_scope
from app.models import Article, ArticleTicker, Ticker
from app.ingest.dedup import seen, mark_seen, url_hash
from app.ingest.tagger import find_tickers
from app.ingest.sources import (
    PER_TICKER_SOURCES, GLOBAL_SOURCES, RawArticle, Source,
)

log = logging.getLogger(__name__)
_settings = get_settings()


def _tracked_tickers() -> dict[str, int]:
    with session_scope() as db:
        rows = db.execute(select(Ticker.id, Ticker.symbol).where(Ticker.is_active.is_(True))).all()
        return {symbol: tid for tid, symbol in rows}


def _save(article: RawArticle, ticker_ids: Iterable[int]) -> bool:
    url = (article.source_url or "").strip()
    if not url or seen(url):
        return False
    if not article.headline.strip():
        return False
    published = article.published_at or datetime.now(timezone.utc)

    with session_scope() as db:
        row = Article(
            external_id=article.external_id,
            source=article.source,
            source_url=url,
            headline=article.headline.strip()[:1000],
            summary=(article.summary or "")[:4000],
            image_url=article.image_url,
            category=article.category,
            published_at=published,
            url_hash=url_hash(url),
            is_classified=False,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            mark_seen(url)
            return False

        for tid in set(ticker_ids):
            db.add(ArticleTicker(article_id=row.id, ticker_id=tid, is_primary=True))
    mark_seen(url)
    return True


def _resolve_ticker_ids(article: RawArticle, tracked: dict[str, int]) -> list[int]:
    """Returns the ticker_id list to attach to this article.
    - if the source already knew the ticker(s), trust it
    - otherwise scan the headline+summary for our tracked symbols"""
    if article.ticker_hints:
        return [tracked[s] for s in article.ticker_hints if s in tracked]
    found = find_tickers((article.headline or "") + " " + (article.summary or ""), tracked.keys())
    return [tracked[s] for s in found if s in tracked]


# Schedule state: when each source last ran.
_last_run: dict[str, float] = defaultdict(lambda: 0.0)


async def _run_per_ticker(source: Source, tracked: dict[str, int]) -> int:
    saved = 0
    for symbol, _tid in tracked.items():
        try:
            articles = list(await source.fetch_per_ticker(symbol))
        except Exception:
            log.exception(f"{source.name}[{symbol}] fetch crashed")
            continue
        for a in articles:
            ticker_ids = _resolve_ticker_ids(a, tracked)
            if not ticker_ids:
                continue
            if _save(a, ticker_ids):
                saved += 1
        # be polite — Yahoo, Google News, SEC EDGAR all care
        await asyncio.sleep(1.2)
    return saved


async def _run_global(source: Source, tracked: dict[str, int]) -> int:
    try:
        articles = list(await source.fetch_global(tracked))
    except Exception:
        log.exception(f"{source.name} global fetch crashed")
        return 0
    saved = 0
    for a in articles:
        ticker_ids = _resolve_ticker_ids(a, tracked)
        if not ticker_ids:
            continue
        if _save(a, ticker_ids):
            saved += 1
    return saved


async def run() -> None:
    log.info(
        "ingest worker starting: %d per-ticker sources, %d global sources",
        len(PER_TICKER_SOURCES), len(GLOBAL_SOURCES),
    )
    while True:
        tracked = _tracked_tickers()
        if not tracked:
            log.warning("no tracked tickers — seed first")
            await asyncio.sleep(30)
            continue

        now = time.monotonic()
        ran_any = False

        for source in PER_TICKER_SOURCES:
            if now - _last_run[source.name] < source.cadence_seconds:
                continue
            _last_run[source.name] = now
            ran_any = True
            t0 = time.monotonic()
            n = await _run_per_ticker(source, tracked)
            dt = time.monotonic() - t0
            log.info(f"[{source.name}] per-ticker cycle: +{n} new in {dt:.1f}s")

        for source in GLOBAL_SOURCES:
            if now - _last_run[source.name] < source.cadence_seconds:
                continue
            _last_run[source.name] = now
            ran_any = True
            n = await _run_global(source, tracked)
            log.info(f"[{source.name}] global cycle: +{n} new")

        # Idle a bit if nothing ran this iteration.
        await asyncio.sleep(5 if ran_any else 15)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ingest] %(message)s")
    asyncio.run(run())
