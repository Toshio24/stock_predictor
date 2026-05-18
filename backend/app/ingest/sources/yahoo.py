"""Yahoo Finance per-ticker RSS. Free, no API key."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import httpx

from .base import RawArticle

log = logging.getLogger(__name__)


def _parse_entry(entry, symbol: str) -> RawArticle | None:
    link = entry.get("link")
    title = (entry.get("title") or "").strip()
    if not link or not title:
        return None
    published = None
    if t := entry.get("published_parsed") or entry.get("updated_parsed"):
        published = datetime(*t[:6], tzinfo=timezone.utc)
    summary = entry.get("summary", "") or entry.get("description", "")
    return RawArticle(
        external_id=entry.get("id") or link,
        source="yahoo",
        source_url=link,
        headline=title,
        summary=summary,
        category="news",
        published_at=published,
        ticker_hints=[symbol],
    )


class YahooFinanceRSS:
    name = "yahoo"
    cadence_seconds = 90
    URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
    HEADERS = {"User-Agent": "Signal/0.1 (news ingestion)"}

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        url = self.URL.format(symbol=symbol)
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=self.HEADERS) as c:
                r = await c.get(url)
                r.raise_for_status()
            parsed = await asyncio.to_thread(feedparser.parse, r.content)
        except (httpx.HTTPError, Exception) as e:
            log.warning(f"yahoo[{symbol}] fetch failed: {e}")
            return []
        out = []
        for e in parsed.entries[:20]:
            if (a := _parse_entry(e, symbol)) is not None:
                out.append(a)
        return out

    async def fetch_global(self, tracked):
        return []
