"""Google News RSS — broad aggregator that often catches Bloomberg/FT/WSJ
articles before Finnhub. Free, no API key."""
from __future__ import annotations

import asyncio
import logging
import urllib.parse
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
    if t := entry.get("published_parsed"):
        published = datetime(*t[:6], tzinfo=timezone.utc)
    # Google News titles often look like "Headline - Source Name" — split out.
    src_label = None
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if 2 <= len(tail) <= 60:
            title = head.strip()
            src_label = tail.strip()
    return RawArticle(
        external_id=entry.get("id") or link,
        source=f"google_news:{src_label.lower().replace(' ', '_')}" if src_label else "google_news",
        source_url=link,
        headline=title,
        summary=entry.get("summary", ""),
        category="news",
        published_at=published,
        ticker_hints=[symbol],
    )


class GoogleNewsRSS:
    name = "google_news"
    cadence_seconds = 180
    URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        q = urllib.parse.quote_plus(f'"{symbol}" stock when:7d')
        url = self.URL.format(query=q)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
            parsed = await asyncio.to_thread(feedparser.parse, r.content)
        except (httpx.HTTPError, Exception) as e:
            log.warning(f"google_news[{symbol}] fetch failed: {e}")
            return []
        out = []
        for e in parsed.entries[:15]:
            if (a := _parse_entry(e, symbol)) is not None:
                out.append(a)
        return out

    async def fetch_global(self, tracked):
        return []
