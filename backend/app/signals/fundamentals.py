"""Fundamentals overlay — per-ticker valuation tilt.

We're not trying to do real fundamental analysis here (that would need
DCF / peer comp models). What we ARE doing: a small valuation sanity
adjustment so that egregiously overvalued names need a stronger sentiment
push to score "bullish", and undervalued names get a small head start.

Plus an "earnings imminent" flag — within ±2 days of a scheduled earnings
release we widen the confidence band (less certain) because the news layer
won't have seen the post-earnings update yet.

Output is a small adjustment in [-0.10, +0.10] on sentiment_score and a
boolean for the earnings flag. Both are best-effort — missing data → 0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EarningsEvent, Fundamentals


@dataclass
class FundamentalsOverlay:
    adjustment: float
    earnings_within_days: int | None  # None = no upcoming earnings tracked
    factors: list[str]


def compute(db: Session, ticker_id: int) -> FundamentalsOverlay:
    adj = 0.0
    factors: list[str] = []

    f = db.execute(select(Fundamentals).where(Fundamentals.ticker_id == ticker_id)).scalar_one_or_none()
    if f is not None:
        # P/E heuristics — these are sector-blind, intentionally crude.
        # We deliberately give a small tilt, never a deciding vote.
        if f.pe_ratio is not None:
            pe = float(f.pe_ratio)
            if 0 < pe < 12:
                adj += 0.04
                factors.append(f"P/E {pe:.1f} — cheap")
            elif pe > 60:
                adj -= 0.04
                factors.append(f"P/E {pe:.1f} — rich valuation")
        if f.debt_to_equity is not None and float(f.debt_to_equity) > 2.0:
            adj -= 0.03
            factors.append(f"D/E {float(f.debt_to_equity):.1f} — leveraged")
        if f.profit_margin is not None and float(f.profit_margin) > 0.20:
            adj += 0.02
            factors.append(f"Margin {float(f.profit_margin)*100:.1f}% — profitable")
        elif f.profit_margin is not None and float(f.profit_margin) < 0:
            adj -= 0.02
            factors.append("Unprofitable on TTM")

    adj = max(-0.10, min(0.10, adj))

    # Earnings proximity.
    now = datetime.now(timezone.utc)
    upcoming = db.execute(
        select(EarningsEvent.event_date)
        .where(EarningsEvent.ticker_id == ticker_id, EarningsEvent.event_date >= now)
        .order_by(EarningsEvent.event_date.asc())
        .limit(1)
    ).scalar_one_or_none()

    if upcoming is not None:
        if upcoming.tzinfo is None:
            upcoming = upcoming.replace(tzinfo=timezone.utc)
        days = (upcoming - now).days
        if 0 <= days <= 2:
            factors.append(f"Earnings in {days}d")
        return FundamentalsOverlay(adjustment=adj, earnings_within_days=days, factors=factors)

    return FundamentalsOverlay(adjustment=adj, earnings_within_days=None, factors=factors)
