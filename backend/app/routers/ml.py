"""ML performance dashboard — read-only.

GET /api/v1/ml/performance
  Full dashboard payload: per-horizon hit rate, calibration buckets,
  active-model metadata, and the most-recent 25 predictions joined to
  their realised outcomes.

GET /api/v1/ml/predictions/{symbol}
  Per-ticker recent predictions (last 25).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ml.metrics import performance, recent_predictions
from app.models import MlPrediction, Ticker, CompositeSignal
from app.security.auth import current_user, User

router = APIRouter()


@router.get("/ml/performance")
def ml_performance(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return performance(db)


@router.get("/ml/predictions/{symbol}")
def ml_predictions_for(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    if not symbol or len(symbol) > 10:
        raise HTTPException(400, "invalid symbol")
    t = db.execute(select(Ticker).where(Ticker.symbol == symbol.upper())).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "ticker not tracked")

    rows = db.execute(
        select(MlPrediction, CompositeSignal.signal_label, CompositeSignal.score)
        .join(CompositeSignal, CompositeSignal.id == MlPrediction.signal_id)
        .where(MlPrediction.ticker_id == t.id)
        .order_by(MlPrediction.predicted_at.desc())
        .limit(25)
    ).all()
    out = []
    for p, label, score in rows:
        out.append({
            "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
            "composite_label": label,
            "composite_score": int(score) if score is not None else None,
            "prob_up_1d": float(p.prob_up_1d) if p.prob_up_1d is not None else None,
            "prob_up_5d": float(p.prob_up_5d) if p.prob_up_5d is not None else None,
            "prob_up_21d": float(p.prob_up_21d) if p.prob_up_21d is not None else None,
            "realized_1d": float(p.realized_1d) if p.realized_1d is not None else None,
            "realized_5d": float(p.realized_5d) if p.realized_5d is not None else None,
            "realized_21d": float(p.realized_21d) if p.realized_21d is not None else None,
        })
    return out
