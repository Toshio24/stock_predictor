from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Ticker
from app.routers._helpers import latest_signal_for

router = APIRouter()


@router.get("/search")
def search(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
) -> dict:
    q = q.strip()
    if not q:
        return {"tickers": [], "pages": []}

    needle = f"%{q.lower()}%"
    rows = db.execute(
        select(Ticker)
        .where(or_(Ticker.symbol.ilike(needle), Ticker.name.ilike(needle)))
        .limit(8)
    ).scalars().all()

    out = []
    for t in rows:
        sig = latest_signal_for(db, t.id)
        out.append({
            "ticker": t.symbol,
            "name": t.name,
            "signal": (sig.signal_label if sig else "neutral"),
            "score": (sig.score if sig else 50),
        })
    return {"tickers": out, "pages": []}
