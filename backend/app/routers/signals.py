from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Ticker
from app.routers._helpers import (
    latest_signal_for, quote_for, recent_spark, signal_payload,
)

router = APIRouter()


@router.get("/signals")
def list_signals(db: Session = Depends(get_db)) -> list[dict]:
    """All active signals — sorted by score desc, then |sentiment| so the
    strongest bull/bear surface first."""
    tickers = db.execute(select(Ticker).where(Ticker.is_active.is_(True))).scalars().all()
    out = []
    for t in tickers:
        sig = latest_signal_for(db, t.id)
        q = quote_for(db, t.id)
        spark = recent_spark(db, t.id)
        out.append(signal_payload(t, sig, q, spark))
    out.sort(key=lambda r: (r["score"], abs(r["score"] - 50)), reverse=True)
    return out


@router.get("/signals/{symbol}")
def signal_for(symbol: str, db: Session = Depends(get_db)) -> dict:
    ticker = db.execute(select(Ticker).where(Ticker.symbol == symbol.upper())).scalar_one_or_none()
    if not ticker:
        raise HTTPException(404, "ticker not tracked")
    return signal_payload(
        ticker,
        latest_signal_for(db, ticker.id),
        quote_for(db, ticker.id),
        recent_spark(db, ticker.id),
    )
