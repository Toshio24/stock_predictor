"""Feature extraction for the ML calibration layer.

The model's job is straightforward: take the composite-signal layer's
outputs and learn how well they actually predict positive forward
returns. So the features are exactly the things we'd want a calibrator to
weigh:

  score             — composite score (0..100), the primary input
  confidence        — composite confidence (0..100)
  sample_size       — number of LLM analyses that fed sentiment
  sentiment_score   — raw weighted sentiment (-1..+1)
  is_bullish        — 1 if label == bullish (one-hot)
  is_bearish        — 1 if label == bearish
  pe_ratio          — fundamentals overlay (NaN if missing — HGBC handles it)
  beta              — fundamentals overlay
  vix               — most recent VIX value
  ten_yr_yield      — most recent 10y treasury

Keep this list short and stable: the same function runs in training and
inference, so any change here requires retraining. Document changes by
bumping the model_type in train.py."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompositeSignal, Fundamentals, MacroIndicator


# Order matters — must match exactly between train and predict. Don't
# reorder without retraining.
FEATURE_NAMES: tuple[str, ...] = (
    "score",
    "confidence",
    "sample_size",
    "sentiment_score",
    "is_bullish",
    "is_bearish",
    "pe_ratio",
    "beta",
    "vix",
    "ten_yr_yield",
)


@dataclass(frozen=True)
class FeatureRow:
    values: np.ndarray
    signal_id: int


def _macro_latest(db: Session, series_id: str) -> float:
    row = db.execute(
        select(MacroIndicator.value)
        .where(MacroIndicator.series_id == series_id)
        .order_by(MacroIndicator.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row is not None else np.nan


def extract_one(db: Session, signal: CompositeSignal) -> np.ndarray:
    """Build the feature vector for a single composite signal. NaNs are
    fine — HistGradientBoostingClassifier handles missing features
    natively."""
    fund = db.execute(
        select(Fundamentals).where(Fundamentals.ticker_id == signal.ticker_id)
    ).scalar_one_or_none()

    pe = float(fund.pe_ratio) if fund and fund.pe_ratio is not None else np.nan
    beta = float(fund.beta) if fund and fund.beta is not None else np.nan
    vix = _macro_latest(db, "VIXCLS")
    ten = _macro_latest(db, "DGS10")

    label = (signal.signal_label or "neutral").lower()
    return np.array(
        [
            float(signal.score or 50),
            float(signal.confidence or 30),
            float(signal.sample_size or 0),
            float(signal.sentiment_score or 0),
            1.0 if label == "bullish" else 0.0,
            1.0 if label == "bearish" else 0.0,
            pe,
            beta,
            vix,
            ten,
        ],
        dtype=np.float64,
    )


def extract_batch(db: Session, signals: Sequence[CompositeSignal]) -> np.ndarray:
    """Stack feature rows for many signals — used in training."""
    if not signals:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)
    rows = [extract_one(db, s) for s in signals]
    return np.vstack(rows)
