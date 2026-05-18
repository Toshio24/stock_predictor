"""Classifier worker. Pulls unclassified articles, calls Claude Haiku, and
writes LlmAnalysis rows. Designed to coexist with the ingest worker."""
import asyncio
import logging
from decimal import Decimal

import anthropic
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import session_scope
from app.models import Article, ArticleTicker, LlmAnalysis, Ticker
from app.llm.client import classify_article

log = logging.getLogger(__name__)
_settings = get_settings()
BATCH_SIZE = 5
SLEEP_BETWEEN_BATCHES = 5  # seconds


def _claim_batch() -> list[tuple[Article, list[tuple[int, Ticker]]]]:
    """Pull a batch of unclassified articles plus their ticker links.
    Returns [(article, [(ticker_id, ticker), ...]), ...]."""
    with session_scope() as db:
        rows = (
            db.execute(
                select(Article)
                .where(Article.is_classified.is_(False))
                .order_by(Article.published_at.desc())
                .limit(BATCH_SIZE)
                .options(joinedload(Article.tickers).joinedload(ArticleTicker.ticker))
            )
            .unique()
            .scalars()
            .all()
        )

        batch = []
        for article in rows:
            links = [(at.ticker_id, at.ticker) for at in article.tickers if at.ticker]
            if not links:
                # No ticker link — mark classified to skip forever.
                article.is_classified = True
                continue
            # detach a copy of the fields we need (avoid expired-object surprises)
            batch.append((
                {
                    "id": article.id,
                    "headline": article.headline,
                    "summary": article.summary,
                },
                [(tid, {"symbol": t.symbol, "name": t.name, "sector": t.sector}) for tid, t in links],
            ))
        return batch


def _persist(article_payload: dict, ticker_id: int, parsed, meta: dict) -> None:
    with session_scope() as db:
        analysis = LlmAnalysis(
            article_id=article_payload["id"],
            ticker_id=ticker_id,
            model_used=meta["model"],
            sentiment_score=Decimal(str(round(parsed.sentiment_score, 3))),
            sentiment_label=parsed.sentiment_label,
            confidence=Decimal(str(round(parsed.confidence, 3))),
            event_type=parsed.event_type,
            rationale=parsed.rationale,
            latency_ms=meta["latency_ms"],
            input_tokens=meta["input_tokens"],
            output_tokens=meta["output_tokens"],
            cost_usd=Decimal(str(meta["cost_usd"])),
        )
        db.add(analysis)
        db.execute(
            update(Article).where(Article.id == article_payload["id"]).values(is_classified=True)
        )


async def run() -> None:
    log.info("classifier worker starting (model=%s)", _settings.claude_model)
    if not _settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY missing — classifier will idle until set")

    daily_cost = 0.0
    while True:
        try:
            batch = _claim_batch()
        except Exception:
            log.exception("failed to claim batch")
            await asyncio.sleep(SLEEP_BETWEEN_BATCHES)
            continue

        if not batch:
            await asyncio.sleep(SLEEP_BETWEEN_BATCHES)
            continue

        for article_payload, ticker_links in batch:
            for ticker_id, ticker_info in ticker_links:
                try:
                    parsed, meta = await asyncio.to_thread(
                        classify_article,
                        headline=article_payload["headline"],
                        summary=article_payload["summary"],
                        ticker=ticker_info["symbol"],
                        company_name=ticker_info["name"],
                        sector=ticker_info["sector"],
                    )
                except anthropic.RateLimitError:
                    log.warning("rate limited; sleeping 30s")
                    await asyncio.sleep(30)
                    continue
                except anthropic.APIError as e:
                    log.warning(f"API error: {e!r}")
                    continue
                except RuntimeError:
                    log.error("ANTHROPIC_API_KEY missing — sleeping 60s")
                    await asyncio.sleep(60)
                    break

                _persist(article_payload, ticker_id, parsed, meta)
                daily_cost += meta["cost_usd"]
                log.info(
                    f"[{ticker_info['symbol']}] {parsed.sentiment_label} "
                    f"score={parsed.sentiment_score:+.2f} conf={parsed.confidence:.2f} "
                    f"cache_read={meta['cache_read_tokens']} cost=${meta['cost_usd']:.5f}"
                )

        log.info(f"running cost since worker start: ${daily_cost:.4f}")
        await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [classify] %(message)s")
    asyncio.run(run())
