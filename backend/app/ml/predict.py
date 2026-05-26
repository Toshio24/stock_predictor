"""Inference helper — loads the active model per horizon and predicts a
calibrated probability of positive forward return.

Returns None for any horizon that doesn't yet have a trained model. The
composite worker calls this once per new signal and persists results to
ml_predictions. The performance dashboard reads those rows back."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_NAMES, extract_one
from app.models import CompositeSignal, MlModel

log = logging.getLogger(__name__)

# Cached models: { horizon: (model_id, sklearn_estimator, mtime_or_id_marker) }
# We invalidate when a fresher MlModel row appears (id changes).
_CACHE: dict[str, tuple[int, Any]] = {}


def _load_active(db: Session, horizon: str) -> tuple[int, Any] | None:
    row = db.execute(
        select(MlModel)
        .where(MlModel.horizon == horizon, MlModel.is_active.is_(True))
        .order_by(MlModel.trained_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not row:
        return None

    cached = _CACHE.get(horizon)
    if cached and cached[0] == row.id:
        return cached

    path = Path(row.artifact_path)
    if not path.exists():
        log.warning("ml model artifact missing on disk: %s", path)
        return None
    payload = joblib.load(path)
    model = payload["model"] if isinstance(payload, dict) else payload
    _CACHE[horizon] = (row.id, model)
    return row.id, model


def predict_all(db: Session, signal: CompositeSignal) -> dict[str, tuple[int, float] | None]:
    """For one composite signal, return {horizon: (model_id, prob_up) or None}."""
    features = extract_one(db, signal).reshape(1, -1)
    out: dict[str, tuple[int, float] | None] = {}
    for horizon in ("1d", "5d", "21d"):
        loaded = _load_active(db, horizon)
        if not loaded:
            out[horizon] = None
            continue
        model_id, model = loaded
        try:
            prob = float(model.predict_proba(features)[0, 1])
        except Exception as e:
            log.warning("predict failed for horizon=%s: %s", horizon, e)
            out[horizon] = None
            continue
        out[horizon] = (model_id, max(0.0, min(1.0, prob)))
    return out
