"""Fundamentals + earnings worker.

Runs once a day. For each tracked ticker:
  - Refresh the `fundamentals` row (P/E, EPS, beta, margins, ...)
  - Upsert the next ~90 days of `earnings_events`

Finnhub free tier is 60 req/min — at 50 tickers × 2 calls each = 100 calls,
this comfortably fits inside the window. We still sleep between calls to
be polite."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import session_scope
from app.ingest.finnhub import FinnhubClient
from app.ingest.fundamentals.finnhub_fundamentals import (
    fetch_metrics, fetch_earnings_calendar, normalize_metrics,
)
from app.models import EarningsEvent, Fundamentals, Ticker

log = logging.getLogger(__name__)


async def _refresh_one(client: FinnhubClient, db_ticker: Ticker) -> None:
    metric = await fetch_metrics(client, db_ticker.symbol)
    if metric:
        norm = normalize_metrics(metric)
        with session_scope() as db:
            stmt = insert(Fundamentals).values(ticker_id=db_ticker.id, **norm)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker_id"],
                set_={**norm, "updated_at": datetime.now(timezone.utc)},
            )
            db.execute(stmt)

    # Earnings calendar.
    events = await fetch_earnings_calendar(client, db_ticker.symbol, days_forward=90)
    if events:
        with session_scope() as db:
            for e in events:
                date_str = e.get("date")
                if not date_str:
                    continue
                try:
                    event_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                stmt = insert(EarningsEvent).values(
                    ticker_id=db_ticker.id,
                    event_date=event_date,
                    period=f"Q{e.get('quarter','?')} {e.get('year','?')}",
                    eps_estimate=_dec(e.get("epsEstimate")),
                    eps_actual=_dec(e.get("epsActual")),
                    revenue_estimate=_dec(e.get("revenueEstimate")),
                    revenue_actual=_dec(e.get("revenueActual")),
                    hour=(e.get("hour") or "")[:10],
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_earnings_ticker_date",
                    set_={
                        "eps_estimate": stmt.excluded.eps_estimate,
                        "eps_actual": stmt.excluded.eps_actual,
                        "revenue_estimate": stmt.excluded.revenue_estimate,
                        "revenue_actual": stmt.excluded.revenue_actual,
                        "hour": stmt.excluded.hour,
                    },
                )
                db.execute(stmt)


def _dec(x):
    if x is None:
        return None
    try:
        return Decimal(str(float(x)))
    except (TypeError, ValueError):
        return None


async def _tick() -> None:
    settings = get_settings()
    if not settings.finnhub_api_key:
        log.info("FINNHUB_API_KEY not set — skipping fundamentals refresh")
        return

    with session_scope() as db:
        tickers = db.execute(select(Ticker).where(Ticker.is_active.is_(True))).scalars().all()
        # Detach so we can use them after the session closes.
        targets = [(t.id, t.symbol) for t in tickers]

    client = FinnhubClient()
    try:
        for tid, sym in targets:
            # Materialise just enough to pass into _refresh_one.
            t = Ticker(id=tid, symbol=sym)
            try:
                await _refresh_one(client, t)
            except Exception:
                log.exception("fundamentals refresh failed for %s", sym)
            # Throttle: 60 req/min = 1s spacing; we make 2 calls per ticker so 2s.
            await asyncio.sleep(2.0)
    finally:
        await client.close()
    log.info("fundamentals: refreshed %d tickers", len(targets))


async def run() -> None:
    settings = get_settings()
    while True:
        try:
            await _tick()
        except Exception:
            log.exception("fundamentals tick failed")
        await asyncio.sleep(settings.fundamentals_refresh_seconds)
