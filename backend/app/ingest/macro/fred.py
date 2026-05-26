"""Thin FRED (St. Louis Fed) API client.

Free key (no rate-limit hassles in practice). We pull a small handful of
macro series that reliably move equity markets:

  CPIAUCSL   — CPI, all urban consumers (inflation)
  FEDFUNDS   — Effective federal funds rate
  DGS10      — 10-Year Treasury yield
  UNRATE     — Unemployment rate
  VIXCLS     — VIX (fear index)
  GDP        — Real GDP (quarterly)

We store the latest observation per series. The macro scorer in
signals/macro.py turns these into a tiny adjustment on top of the
sentiment + technical composite."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings

log = logging.getLogger(__name__)
BASE = "https://api.stlouisfed.org/fred/series/observations"


# (series_id, friendly label) — keep this list tight to control API usage.
SERIES: list[tuple[str, str]] = [
    ("CPIAUCSL", "CPI (urban)"),
    ("FEDFUNDS", "Fed Funds Rate"),
    ("DGS10", "10-Year Treasury"),
    ("UNRATE", "Unemployment Rate"),
    ("VIXCLS", "VIX"),
    ("GDP", "Real GDP"),
]


@dataclass(frozen=True)
class FredObservation:
    series_id: str
    label: str
    value: float
    observed_at: datetime


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def fetch_latest(client: httpx.AsyncClient, series_id: str, api_key: str) -> dict | None:
    """Return the most recent observation row for a series, or None on
    transient errors / no data. FRED puts '.' in `value` for missing days
    — we skip those and keep walking backward until we find one."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 20,  # cover holidays / missing days
    }
    r = await client.get(BASE, params=params)
    r.raise_for_status()
    data = r.json()
    for obs in data.get("observations", []):
        v = obs.get("value", ".")
        if v == "." or v is None or v == "":
            continue
        try:
            return {"value": float(v), "date": obs["date"]}
        except (TypeError, ValueError):
            continue
    return None


async def fetch_all() -> list[FredObservation]:
    """Pull the latest value for every series in SERIES. Skips silently
    when FRED_API_KEY is unset (so the worker doesn't crash dev)."""
    settings = get_settings()
    key = settings.fred_api_key
    if not key:
        log.info("FRED_API_KEY not set — skipping macro refresh")
        return []

    out: list[FredObservation] = []
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "signal/0.1"}) as c:
        for sid, label in SERIES:
            try:
                obs = await fetch_latest(c, sid, key)
            except Exception as e:
                log.warning("FRED fetch failed for %s: %s", sid, e)
                continue
            if not obs:
                continue
            dt = datetime.fromisoformat(obs["date"]).replace(tzinfo=timezone.utc)
            out.append(FredObservation(series_id=sid, label=label, value=obs["value"], observed_at=dt))
    return out
