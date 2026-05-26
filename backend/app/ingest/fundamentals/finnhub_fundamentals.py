"""Finnhub fundamentals + earnings calendar fetcher.

Free-tier Finnhub gives us:
  /stock/metric?metric=all   — P/E, EPS, market cap, beta, margins, etc.
  /calendar/earnings         — upcoming + recent earnings dates

The fundamentals snapshot is refreshed once per day per ticker (numbers
don't change intraday). Earnings calendar is refreshed daily for the
forward 60-day window."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.ingest.finnhub import FinnhubClient

log = logging.getLogger(__name__)


async def fetch_metrics(client: FinnhubClient, symbol: str) -> dict[str, Any] | None:
    """Pull the all-metrics blob for a single ticker. Returns the inner
    `metric` dict, or None on missing data."""
    try:
        data = await client._get("/stock/metric", symbol=symbol, metric="all")
    except Exception as e:
        log.warning("finnhub metrics failed for %s: %s", symbol, e)
        return None
    return data.get("metric") if isinstance(data, dict) else None


async def fetch_earnings_calendar(client: FinnhubClient, symbol: str, days_forward: int = 90) -> list[dict]:
    """Earnings events in a forward window. Finnhub returns both past
    and future events when you query by symbol — we filter to the window
    and let upserts handle duplicates."""
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days_forward)
    try:
        data = await client._get(
            "/calendar/earnings",
            symbol=symbol,
            **{"from": today.isoformat(), "to": end.isoformat()},
        )
    except Exception as e:
        log.warning("finnhub earnings calendar failed for %s: %s", symbol, e)
        return []
    return data.get("earningsCalendar") if isinstance(data, dict) else []


def _decimal(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    # Finnhub uses 0 / null indistinguishably for "missing" sometimes; we
    # treat exactly 0 on ratios as missing too — better to display nothing
    # than something misleading.
    return v if v != 0 else None


def normalize_metrics(metric: dict[str, Any]) -> dict[str, float | None]:
    """Translate the Finnhub metric blob to our column shapes. Field names
    are stable on Finnhub free tier as of this writing — if anything 404s
    or 'KeyError's, treat as None and move on."""
    return {
        "pe_ratio": _decimal(metric.get("peTTM") or metric.get("peNormalizedAnnual")),
        "eps_ttm": _decimal(metric.get("epsTTM") or metric.get("epsBasicExclExtraItemsTTM")),
        "market_cap": _decimal(metric.get("marketCapitalization")),
        "dividend_yield": _decimal(metric.get("currentDividendYieldTTM")),
        "beta": _decimal(metric.get("beta")),
        "revenue_ttm": _decimal(metric.get("revenuePerShareTTM")),  # share-level, no shares-outstanding
        "profit_margin": _decimal(metric.get("netProfitMarginTTM")),
        "debt_to_equity": _decimal(metric.get("totalDebt/totalEquityAnnual")),
    }
