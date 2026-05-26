"""Per-ticker fundamentals + upcoming earnings dates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EarningsEvent, Fundamentals, Ticker
from app.security.auth import current_user, User

router = APIRouter()


@router.get("/fundamentals/{symbol}")
def fundamentals_for(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if not symbol or len(symbol) > 10:
        raise HTTPException(400, "invalid symbol")
    t = db.execute(select(Ticker).where(Ticker.symbol == symbol.upper())).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "ticker not tracked")

    f = db.execute(select(Fundamentals).where(Fundamentals.ticker_id == t.id)).scalar_one_or_none()
    next_earnings = db.execute(
        select(EarningsEvent)
        .where(EarningsEvent.ticker_id == t.id)
        .order_by(EarningsEvent.event_date.asc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "symbol": t.symbol,
        "fundamentals": (
            {
                "pe_ratio": float(f.pe_ratio) if f and f.pe_ratio is not None else None,
                "eps_ttm": float(f.eps_ttm) if f and f.eps_ttm is not None else None,
                "market_cap": float(f.market_cap) if f and f.market_cap is not None else None,
                "dividend_yield": float(f.dividend_yield) if f and f.dividend_yield is not None else None,
                "beta": float(f.beta) if f and f.beta is not None else None,
                "updated_at": f.updated_at.isoformat() if f and f.updated_at else None,
            }
            if f else None
        ),
        "next_earnings": (
            {
                "event_date": next_earnings.event_date.isoformat() if next_earnings else None,
                "period": next_earnings.period if next_earnings else None,
                "eps_estimate": float(next_earnings.eps_estimate) if next_earnings and next_earnings.eps_estimate is not None else None,
            }
            if next_earnings else None
        ),
    }
