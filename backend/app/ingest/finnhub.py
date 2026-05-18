"""Thin Finnhub REST client. Free-tier friendly (60 req/min)."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings

log = logging.getLogger(__name__)
BASE = "https://finnhub.io/api/v1"


class FinnhubClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_settings().finnhub_api_key
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError,)),
    )
    async def _get(self, path: str, **params: Any) -> Any:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is not configured")
        params["token"] = self.api_key
        r = await self._client.get(f"{BASE}{path}", params=params)
        if r.status_code == 429:
            log.warning("Finnhub rate limit hit; sleeping 30s")
            await asyncio.sleep(30)
            r.raise_for_status()
        r.raise_for_status()
        return r.json()

    async def general_news(self, category: str = "general") -> list[dict]:
        return await self._get("/news", category=category)

    async def company_news(self, symbol: str, days_back: int = 2) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days_back)
        return await self._get(
            "/company-news",
            symbol=symbol,
            **{"from": start.isoformat(), "to": today.isoformat()},
        )

    async def quote(self, symbol: str) -> dict:
        return await self._get("/quote", symbol=symbol)
