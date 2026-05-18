"""Reddit discussion sentiment from finance subreddits. Free JSON endpoints,
unauthenticated rate limit is generous with a real User-Agent."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.ingest.tagger import find_tickers
from .base import RawArticle

log = logging.getLogger(__name__)

SUBREDDITS = ["wallstreetbets", "stocks", "investing", "StockMarket"]


class RedditDiscussions:
    name = "reddit"
    cadence_seconds = 300
    HEADERS = {"User-Agent": "Signal/0.1 (financial research bot; +https://github.com/Toshio24/stock_predictor)"}

    async def fetch_per_ticker(self, symbol):
        return []

    async def fetch_global(self, tracked: dict[str, int]) -> Iterable[RawArticle]:
        out: list[RawArticle] = []
        async with httpx.AsyncClient(timeout=8.0, headers=self.HEADERS) as c:
            for sub in SUBREDDITS:
                try:
                    r = await c.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=50")
                    r.raise_for_status()
                    payload = r.json()
                except Exception as e:
                    log.warning(f"reddit[{sub}]: {e}")
                    continue
                for child in payload.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = (post.get("title") or "").strip()
                    body = (post.get("selftext") or "").strip()[:1200]
                    permalink = post.get("permalink", "")
                    if not title or not permalink:
                        continue
                    found = find_tickers(title + " " + body, tracked.keys())
                    if not found:
                        continue
                    out.append(RawArticle(
                        external_id=post.get("name"),
                        source=f"reddit:{sub}",
                        source_url=f"https://www.reddit.com{permalink}",
                        headline=title,
                        summary=body[:600],
                        category="social",
                        published_at=datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc) if post.get("created_utc") else None,
                        ticker_hints=list(found),
                    ))
        return out
