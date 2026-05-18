"""SEC EDGAR per-ticker filings (8-K, 10-Q, 10-K, 13-D, S-1, 6-K).
Free, no API key. SEC requires a descriptive User-Agent with contact info."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import httpx

from .base import RawArticle

log = logging.getLogger(__name__)


# Material filing types that move price. 8-K = material events, 10-Q/10-K =
# earnings, 13-D/13-G = activist stakes, S-1 = IPO/follow-on, 6-K = foreign.
FILING_TYPES = ["8-K", "10-Q", "10-K", "13D", "S-1", "6-K"]


def _parse_entry(entry, symbol: str) -> RawArticle | None:
    link = entry.get("link")
    title = (entry.get("title") or "").strip()
    if not link or not title:
        return None
    published = None
    if t := entry.get("updated_parsed") or entry.get("published_parsed"):
        published = datetime(*t[:6], tzinfo=timezone.utc)
    summary = entry.get("summary", "")
    return RawArticle(
        external_id=entry.get("id") or link,
        source="sec_edgar",
        source_url=link,
        headline=f"SEC filing: {title}",
        summary=summary,
        category="filing",
        published_at=published,
        ticker_hints=[symbol],
    )


class SecEdgarFilings:
    name = "sec_edgar"
    cadence_seconds = 600  # filings don't update every minute
    URL = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcompany&CIK={symbol}&type={filing_type}"
        "&dateb=&owner=include&count=10&output=atom"
    )
    HEADERS = {
        "User-Agent": "Signal Research signal-research@example.com",
        "Accept": "application/atom+xml",
    }

    async def _fetch_type(self, client: httpx.AsyncClient, symbol: str, filing_type: str) -> list[RawArticle]:
        url = self.URL.format(symbol=symbol, filing_type=filing_type)
        try:
            r = await client.get(url)
            r.raise_for_status()
            parsed = await asyncio.to_thread(feedparser.parse, r.content)
        except (httpx.HTTPError, Exception) as e:
            log.warning(f"edgar[{symbol}/{filing_type}]: {e}")
            return []
        out = []
        for e in parsed.entries[:5]:
            if (a := _parse_entry(e, symbol)) is not None:
                a.headline = f"SEC {filing_type}: {a.headline.removeprefix('SEC filing: ')}"
                out.append(a)
        return out

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        async with httpx.AsyncClient(timeout=8.0, headers=self.HEADERS) as c:
            articles: list[RawArticle] = []
            for ft in FILING_TYPES:
                articles.extend(await self._fetch_type(c, symbol, ft))
                # SEC asks for ≤10 req/sec — be polite.
                await asyncio.sleep(0.15)
            return articles

    async def fetch_global(self, tracked):
        return []
