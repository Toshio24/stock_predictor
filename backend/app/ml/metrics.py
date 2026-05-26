"""Performance metrics for the ML layer.

We compute these on demand for the dashboard. The dataset is small enough
that scanning all ml_predictions rows on each request is fine — when we
hit five-figure prediction counts we can move to a materialised view."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompositeSignal, LlmAnalysis, MlModel, MlPrediction, Ticker


def _bucket_calibration(probs: list[float], outcomes: list[int], n_bins: int = 10) -> list[dict]:
    """Reliability diagram data: bin predictions into deciles, report
    mean predicted prob vs. actual hit rate in each bin. Perfect
    calibration → mean_pred ≈ hit_rate on every row."""
    if not probs:
        return []
    out = []
    edges = [i / n_bins for i in range(n_bins + 1)]
    for lo, hi in zip(edges[:-1], edges[1:]):
        pairs = [(p, o) for p, o in zip(probs, outcomes) if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if not pairs:
            continue
        avg_pred = sum(p for p, _ in pairs) / len(pairs)
        actual = sum(o for _, o in pairs) / len(pairs)
        out.append({
            "bucket": f"{lo:.1f}–{hi:.1f}",
            "n": len(pairs),
            "predicted_prob": round(avg_pred, 3),
            "actual_hit_rate": round(actual, 3),
        })
    return out


def _per_horizon(db: Session, horizon: str) -> dict:
    prob_col = getattr(MlPrediction, f"prob_up_{horizon}")
    real_col = getattr(MlPrediction, f"realized_{horizon}")

    # Active model metadata.
    active = db.execute(
        select(MlModel)
        .where(MlModel.horizon == horizon, MlModel.is_active.is_(True))
        .order_by(MlModel.trained_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    # All predictions with a known outcome.
    rows = db.execute(
        select(prob_col, real_col).where(prob_col.is_not(None), real_col.is_not(None))
    ).all()

    resolved_n = len(rows)
    if resolved_n == 0:
        return {
            "horizon": horizon,
            "model": _model_meta(active),
            "resolved": 0,
            "pending": _pending_count(db, horizon),
            "hit_rate_pct": None,
            "high_conf_hit_rate_pct": None,
            "mean_predicted_prob": None,
            "mean_realized_return_pct": None,
            "calibration": [],
        }

    probs = [float(p) for p, _ in rows]
    returns = [float(r) for _, r in rows]
    outcomes = [1 if r > 0 else 0 for r in returns]
    hit_rate = sum(outcomes) / len(outcomes)
    high_conf = [o for p, o in zip(probs, outcomes) if p >= 0.6]
    high_conf_hit = (sum(high_conf) / len(high_conf)) if high_conf else None
    return {
        "horizon": horizon,
        "model": _model_meta(active),
        "resolved": resolved_n,
        "pending": _pending_count(db, horizon),
        "hit_rate_pct": round(hit_rate * 100, 1),
        "high_conf_hit_rate_pct": round(high_conf_hit * 100, 1) if high_conf_hit is not None else None,
        "mean_predicted_prob": round(sum(probs) / len(probs), 3),
        "mean_realized_return_pct": round(sum(returns) / len(returns), 3),
        "calibration": _bucket_calibration(probs, outcomes),
    }


def _pending_count(db: Session, horizon: str) -> int:
    prob_col = getattr(MlPrediction, f"prob_up_{horizon}")
    real_col = getattr(MlPrediction, f"realized_{horizon}")
    return int(db.execute(
        select(prob_col).where(prob_col.is_not(None), real_col.is_(None))
    ).all().__len__())


def _model_meta(m: MlModel | None) -> dict | None:
    if m is None:
        return None
    return {
        "id": m.id,
        "model_type": m.model_type,
        "trained_at": m.trained_at.isoformat() if m.trained_at else None,
        "n_train_samples": m.n_train_samples,
        "n_test_samples": m.n_test_samples,
        "holdout_accuracy_pct": round(float(m.accuracy) * 100, 1) if m.accuracy is not None else None,
        "roc_auc": float(m.roc_auc) if m.roc_auc is not None else None,
        "brier_score": float(m.brier_score) if m.brier_score is not None else None,
        "feature_importances": m.feature_importances or {},
    }


def recent_predictions(db: Session, limit: int = 25) -> list[dict]:
    rows = db.execute(
        select(MlPrediction, Ticker.symbol, CompositeSignal.signal_label, CompositeSignal.score)
        .join(Ticker, Ticker.id == MlPrediction.ticker_id)
        .join(CompositeSignal, CompositeSignal.id == MlPrediction.signal_id)
        .order_by(MlPrediction.predicted_at.desc())
        .limit(limit)
    ).all()
    out = []
    for p, sym, label, score in rows:
        out.append({
            "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
            "ticker": sym,
            "composite_label": label,
            "composite_score": int(score) if score is not None else None,
            "prob_up_5d": float(p.prob_up_5d) if p.prob_up_5d is not None else None,
            "realized_5d_pct": float(p.realized_5d) if p.realized_5d is not None else None,
            "hit_5d": (
                None if p.realized_5d is None or p.prob_up_5d is None
                else bool((float(p.realized_5d) > 0) == (float(p.prob_up_5d) >= 0.5))
            ),
        })
    return out


def claude_spend(db: Session) -> dict:
    """Aggregate Anthropic API spend straight from the llm_analyses table.
    Each row records cost_usd at write time, so this is real, not estimated.

    Returns spend buckets the UI needs: today, this calendar month, total,
    plus the count of analyses (a proxy for activity volume)."""
    from sqlalchemy import func as sa_func

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_n, total_usd = db.execute(
        select(sa_func.count(LlmAnalysis.id), sa_func.coalesce(sa_func.sum(LlmAnalysis.cost_usd), 0))
    ).one()
    today_n, today_usd = db.execute(
        select(sa_func.count(LlmAnalysis.id), sa_func.coalesce(sa_func.sum(LlmAnalysis.cost_usd), 0))
        .where(LlmAnalysis.created_at >= today_start)
    ).one()
    month_n, month_usd = db.execute(
        select(sa_func.count(LlmAnalysis.id), sa_func.coalesce(sa_func.sum(LlmAnalysis.cost_usd), 0))
        .where(LlmAnalysis.created_at >= month_start)
    ).one()

    return {
        "today_usd": round(float(today_usd or 0), 4),
        "today_n": int(today_n or 0),
        "month_usd": round(float(month_usd or 0), 4),
        "month_n": int(month_n or 0),
        "total_usd": round(float(total_usd or 0), 4),
        "total_n": int(total_n or 0),
        "avg_usd_per_call": round(float(total_usd or 0) / total_n, 4) if total_n else None,
    }


def performance(db: Session) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizons": [_per_horizon(db, h) for h in ("1d", "5d", "21d")],
        "recent": recent_predictions(db, limit=25),
        "spend": claude_spend(db),
    }
