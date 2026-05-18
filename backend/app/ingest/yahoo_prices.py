"""Daily OHLCV from Yahoo's chart API. No API key required.

Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
Returns adjusted daily bars going back as far as `range` requests.
We use range=1y interval=1d which is plenty for SMA-200 + buffer."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo's chart API enforces UA gating just like the RSS feed.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Signal/0.1"
    ),
    "Accept": "application/json",
}


async def fetch_daily_bars(symbol: str, range_: str = "1y") -> list[dict]:
    """Return a list of {bar_date, open, high, low, close, volume} dicts,
    oldest-first. Empty list on failure."""
    params = {"range": range_, "interval": "1d", "includePrePost": "false"}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as c:
            r = await c.get(URL.format(symbol=symbol), params=params)
    except httpx.HTTPError as e:
        log.warning(f"yahoo_prices[{symbol}] network error: {e}")
        return []

    if r.status_code != 200:
        log.warning(f"yahoo_prices[{symbol}] HTTP {r.status_code}")
        return []

    try:
        payload = r.json()
    except Exception as e:
        log.warning(f"yahoo_prices[{symbol}] bad json: {e}")
        return []

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    res0 = result[0]

    timestamps = res0.get("timestamp") or []
    indicators = (res0.get("indicators") or {}).get("quote") or [{}]
    q = indicators[0]
    opens, highs, lows, closes, volumes = (
        q.get("open") or [], q.get("high") or [],
        q.get("low") or [], q.get("close") or [],
        q.get("volume") or [],
    )

    bars: list[dict] = []
    for i, ts in enumerate(timestamps):
        # Skip rows where the price arrays have a None (holiday gap, etc.)
        if any(arr[i] is None for arr in (opens, highs, lows, closes) if i < len(arr)):
            continue
        if i >= len(closes) or closes[i] is None:
            continue
        bars.append({
            "bar_date": datetime.fromtimestamp(ts, tz=timezone.utc),
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
        })
    return bars
