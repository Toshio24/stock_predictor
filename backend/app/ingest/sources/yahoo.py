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


# Yahoo 404s requests without a "real" User-Agent. Our primary UA is fine
# today, but Yahoo has tightened gating before — if it changes again, we
# transparently retry once with a browser UA, and log loudly so it shows up.
PRIMARY_UA = "Signal/0.1 (news ingestion)"
FALLBACK_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) RSS/1.0"
)


class YahooFinanceRSS:
    name = "yahoo"
    cadence_seconds = 90
    URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

    def __init__(self) -> None:
        # Sticky flag: once Yahoo starts blocking PRIMARY_UA we stay on the
        # fallback until process restart. Avoids paying the 404 on every call.
        self._ua = PRIMARY_UA
        self._fallback_active = False

    async def _get(self, url: str, ua: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": ua}) as c:
            return await c.get(url)

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        url = self.URL.format(symbol=symbol)
        try:
            r = await self._get(url, self._ua)
        except httpx.HTTPError as e:
            log.warning(f"yahoo[{symbol}] network error: {e}")
            return []

        if r.status_code == 404 and not self._fallback_active:
            log.error(
                f"yahoo HTTP 404 with UA={self._ua!r} — Yahoo may have tightened "
                "their User-Agent gating. Retrying with browser UA; consider "
                "updating PRIMARY_UA in sources/yahoo.py."
            )
            try:
                r = await self._get(url, FALLBACK_UA)
            except httpx.HTTPError as e:
                log.warning(f"yahoo[{symbol}] fallback retry failed: {e}")
                return []
            if r.status_code == 200:
                self._ua = FALLBACK_UA
                self._fallback_active = True

        if r.status_code != 200:
            log.warning(f"yahoo[{symbol}] HTTP {r.status_code}; skipping")
            return []

        try:
            parsed = await asyncio.to_thread(feedparser.parse, r.content)
        except Exception as e:
            log.warning(f"yahoo[{symbol}] parse error: {e}")
            return []

        out: list[RawArticle] = []
        for e in parsed.entries[:20]:
            if (a := _parse_entry(e, symbol)) is not None:
                out.append(a)
        return out

    async def fetch_global(self, tracked):
        return []
