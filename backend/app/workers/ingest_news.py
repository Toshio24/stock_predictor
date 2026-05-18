"""News ingestion worker. Rotates through tracked tickers, pulling fresh
company news every ~60s and general market news every ~120s. Stores articles
with ticker links and leaves classification for the classifier worker."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import session_scope
from app.models import Article, ArticleTicker, Ticker
from app.ingest.finnhub import FinnhubClient
from app.ingest.dedup import seen, mark_seen, url_hash
from app.ingest.tagger import find_tickers

log = logging.getLogger(__name__)
_settings = get_settings()


def _tracked_tickers() -> dict[str, int]:
    """Returns {symbol: ticker_id}."""
    with session_scope() as db:
        rows = db.execute(select(Ticker.id, Ticker.symbol).where(Ticker.is_active.is_(True))).all()
        return {symbol: tid for tid, symbol in rows}


def _save_article(item: dict, source: str, ticker_ids: Iterable[int]) -> int | None:
    """Inserts a new article + ticker links. Returns the article id or None if
    already present."""
    url = item.get("url") or ""
    if not url or seen(url):
        return None

    published_ts = item.get("datetime") or 0
    if not published_ts:
        return None
    published_at = datetime.fromtimestamp(published_ts, tz=timezone.utc)

    headline = (item.get("headline") or "").strip()
    if not headline:
        return None

    with session_scope() as db:
        article = Article(
            external_id=str(item.get("id")) if item.get("id") else None,
            source=item.get("source") or source,
            source_url=url,
            headline=headline,
            summary=item.get("summary") or "",
            image_url=item.get("image"),
            category=item.get("category") or source,
            published_at=published_at,
            url_hash=url_hash(url),
            is_classified=False,
        )
        db.add(article)
        try:
            db.flush()  # get id without committing
        except IntegrityError:
            db.rollback()
            mark_seen(url)
            return None

        for tid in set(ticker_ids):
            db.add(ArticleTicker(article_id=article.id, ticker_id=tid, is_primary=True))

        article_id = article.id

    mark_seen(url)
    return article_id


async def poll_company_news(client: FinnhubClient, symbol: str, ticker_id: int) -> int:
    items = await client.company_news(symbol)
    new_count = 0
    for it in items[:25]:  # most-recent first; cap to stay polite
        if _save_article(it, source="finnhub:company", ticker_ids=[ticker_id]):
            new_count += 1
    return new_count


async def poll_general_news(client: FinnhubClient, tracked: dict[str, int]) -> int:
    items = await client.general_news()
    new_count = 0
    for it in items[:50]:
        text = (it.get("headline") or "") + " " + (it.get("summary") or "")
        found = find_tickers(text, tracked.keys())
        if not found:
            continue  # skip articles that don't reference our universe
        ticker_ids = [tracked[s] for s in found if s in tracked]
        if _save_article(it, source="finnhub:general", ticker_ids=ticker_ids):
            new_count += 1
    return new_count


async def run() -> None:
    log.info("ingest worker starting")
    client = FinnhubClient()
    symbols_cycled = 0
    try:
        while True:
            tracked = _tracked_tickers()
            if not tracked:
                log.warning("no tracked tickers — seed first")
                await asyncio.sleep(30)
                continue

            symbols = list(tracked.items())
            # Free tier: 60 req/min. Pull 1 company + every 2nd cycle pull general.
            for symbol, ticker_id in symbols:
                try:
                    n = await poll_company_news(client, symbol, ticker_id)
                    if n:
                        log.info(f"[{symbol}] +{n} new articles")
                except Exception as e:
                    log.warning(f"company-news {symbol} failed: {e}")
                await asyncio.sleep(1.2)  # pace requests (~50/min)

            symbols_cycled += 1
            if symbols_cycled % 2 == 0:
                try:
                    n = await poll_general_news(client, tracked)
                    if n:
                        log.info(f"[general] +{n} new articles")
                except Exception as e:
                    log.warning(f"general-news failed: {e}")

            log.info(f"cycle complete; sleeping {_settings.finnhub_poll_seconds}s")
            await asyncio.sleep(_settings.finnhub_poll_seconds)
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ingest] %(message)s")
    asyncio.run(run())
