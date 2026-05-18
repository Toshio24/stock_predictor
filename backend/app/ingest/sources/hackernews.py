"""Hacker News via Algolia search — strong signal for tech stocks (NVDA,
GOOGL, META, MSFT, AAPL, TSLA, AMD, etc.). Free, no key, ~10k req/hour."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.ingest.tagger import find_tickers
from .base import RawArticle

log = logging.getLogger(__name__)


# Most-relevant tech-adjacent companies in our universe. HN won't talk about
# JPM or KO, but goes deep on these.
TECH_HEAVY = {"NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AMD",
              "NFLX", "AVGO", "INTC", "SHOP", "COIN", "PLTR", "CRWD", "SNOW",
              "DDOG", "ORCL", "CRM", "ADBE", "MSTR"}


def _parse_hit(hit: dict, ticker_hints: list[str]) -> RawArticle | None:
    title = (hit.get("title") or hit.get("story_title") or "").strip()
    url = hit.get("url") or hit.get("story_url")
    if not title:
        return None
    obj_id = hit.get("objectID")
    permalink = f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else None
    return RawArticle(
        external_id=obj_id,
        source="hackernews",
        source_url=url or permalink or "",
        headline=title,
        summary=(hit.get("story_text") or "")[:600],
        category="tech",
        published_at=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc) if hit.get("created_at_i") else None,
        ticker_hints=ticker_hints,
    )


class HackerNewsSearch:
    name = "hackernews"
    cadence_seconds = 600

    async def fetch_per_ticker(self, symbol):
        return []

    async def fetch_global(self, tracked: dict[str, int]) -> Iterable[RawArticle]:
        # Restrict to the tech-heavy subset to avoid noise from JPM/XOM/etc.
        targets = [s for s in tracked.keys() if s in TECH_HEAVY]
        out: list[RawArticle] = []
        async with httpx.AsyncClient(timeout=8.0) as c:
            # One broad query per cycle is plenty.
            try:
                # Look-back: most recent first; HN search ranks by relevance,
                # so we use "search_by_date" for stable ordering.
                r = await c.get(
                    "https://hn.algolia.com/api/v1/search_by_date",
                    params={"tags": "story", "hitsPerPage": 50},
                )
                r.raise_for_status()
                hits = r.json().get("hits", [])
            except Exception as e:
                log.warning(f"hn fetch failed: {e}")
                return []
            for hit in hits:
                title = (hit.get("title") or "").strip()
                if not title:
                    continue
                # tag with any of our tech tickers mentioned in the title
                found = [s for s in targets if find_tickers(title, [s])]
                if not found:
                    continue
                if (a := _parse_hit(hit, found)) is not None:
                    out.append(a)
        return out
