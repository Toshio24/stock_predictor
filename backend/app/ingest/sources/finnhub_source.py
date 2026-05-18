"""Wraps the existing FinnhubClient as two distinct Source objects."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from app.ingest.finnhub import FinnhubClient
from .base import RawArticle

log = logging.getLogger(__name__)


def _convert(item: dict, source_label: str, ticker_hints: list[str]) -> RawArticle | None:
    url = item.get("url") or ""
    headline = (item.get("headline") or "").strip()
    if not url or not headline:
        return None
    ts = item.get("datetime") or 0
    published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
    return RawArticle(
        external_id=str(item.get("id")) if item.get("id") else None,
        source=source_label,
        source_url=url,
        headline=headline,
        summary=item.get("summary") or "",
        image_url=item.get("image"),
        category=item.get("category") or "news",
        published_at=published,
        ticker_hints=ticker_hints,
    )


class FinnhubCompanyNews:
    name = "finnhub"
    cadence_seconds = 60

    def __init__(self) -> None:
        self._client: FinnhubClient | None = None

    def _c(self) -> FinnhubClient:
        if self._client is None:
            self._client = FinnhubClient()
        return self._client

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        items = await self._c().company_news(symbol)
        return [a for it in items[:25] if (a := _convert(it, "finnhub", [symbol]))]

    async def fetch_global(self, tracked):
        return []


class FinnhubGeneralNews:
    name = "finnhub:general"
    cadence_seconds = 180

    def __init__(self) -> None:
        self._client: FinnhubClient | None = None

    def _c(self) -> FinnhubClient:
        if self._client is None:
            self._client = FinnhubClient()
        return self._client

    async def fetch_per_ticker(self, symbol: str):
        return []

    async def fetch_global(self, tracked: dict[str, int]) -> Iterable[RawArticle]:
        items = await self._c().general_news()
        # No ticker hints — let the tagger find matches downstream.
        return [a for it in items[:50] if (a := _convert(it, "finnhub:general", []))]
