"""Train one calibration model per horizon (1d / 5d / 21d).

Usage:
    docker compose run --rm api python -m app.ml.train [--min-samples 50]

What it does:
  1. Pull every resolved SignalOutcome (return_<horizon> is not NULL).
  2. Join back to the CompositeSignal that produced it; extract features.
  3. Label = 1 if return > 0 else 0 (binary classification).
  4. Train HistGradientBoostingClassifier, evaluate on a holdout split.
  5. Persist the model file + a row in ml_models. Mark previous models
     for the same horizon as inactive.

Why HistGradientBoostingClassifier (HGBC):
  - Robust on small samples; no scaling needed.
  - Native NaN handling — fundamentals/macro can be missing.
  - Predict probabilities directly (we surface those as 'confidence-of-up').
  - sklearn-only — no torch, no GPU.

When training data is too thin we exit gracefully without saving — the
inference layer just keeps using the previous model (or returns None if
this is the first run)."""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import session_scope
from app.ml.features import FEATURE_NAMES, extract_batch
from app.models import CompositeSignal, MlModel, SignalOutcome

log = logging.getLogger(__name__)

# Where joblib files live. Mounted as a volume in docker-compose so models
# survive container restarts.
MODEL_DIR = Path(os.environ.get("ML_MODEL_DIR", "/app/ml_artifacts"))
MIN_SAMPLES_DEFAULT = 50
HORIZONS = ("1d", "5d", "21d")


def _load_training_data(db: Session, horizon: str) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Pull resolved outcomes for a horizon + their composite-signal features.

    Returns (X, y, signal_ids). y[i] = 1 if return > 0 else 0."""
    return_col = getattr(SignalOutcome, f"return_{horizon}")
    rows = db.execute(
        select(SignalOutcome.signal_id, return_col)
        .where(return_col.is_not(None))
    ).all()
    if not rows:
        return np.empty((0, len(FEATURE_NAMES))), np.empty(0), []

    signal_ids = [r[0] for r in rows]
    returns = np.array([float(r[1]) for r in rows], dtype=np.float64)
    y = (returns > 0).astype(np.int8)

    # Pull the matching composite signals. Order-preserving lookup.
    signals = db.execute(
        select(CompositeSignal).where(CompositeSignal.id.in_(signal_ids))
    ).scalars().all()
    sig_by_id = {s.id: s for s in signals}
    aligned = [sig_by_id[sid] for sid in signal_ids if sid in sig_by_id]
    if len(aligned) != len(signal_ids):
        # Some signals were deleted under our feet — drop those rows.
        keep_mask = np.array([sid in sig_by_id for sid in signal_ids])
        y = y[keep_mask]
        signal_ids = [sid for sid in signal_ids if sid in sig_by_id]

    X = extract_batch(db, aligned)
    return X, y, signal_ids


def _train_horizon(db: Session, horizon: str, min_samples: int) -> MlModel | None:
    X, y, _ = _load_training_data(db, horizon)
    n = len(y)
    log.info("horizon=%s: %d resolved outcomes available", horizon, n)
    if n < min_samples:
        log.warning("skip %s — need %d samples, have %d", horizon, min_samples, n)
        return None

    # Need both classes present, or a classifier won't fit.
    if len(np.unique(y)) < 2:
        log.warning("skip %s — only one class present in training labels", horizon)
        return None

    # 80/20 split. With small n stratify to keep class balance honest.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if n >= 20 else None
    )

    clf = HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.05,
        max_depth=4,
        l2_regularization=1.0,        # mild regularisation — we're data-thin
        random_state=42,
    )
    clf.fit(X_train, y_train)

    preds = clf.predict(X_test)
    probs = clf.predict_proba(X_test)[:, 1]
    acc = float(accuracy_score(y_test, preds))
    try:
        auc = float(roc_auc_score(y_test, probs))
    except ValueError:
        auc = None
    brier = float(brier_score_loss(y_test, probs))

    # HGBC exposes feature_importances_ via permutation in newer sklearn;
    # fallback to a uniform map so the dashboard always has something.
    try:
        importances = dict(zip(FEATURE_NAMES, [float(v) for v in clf.feature_importances_]))
    except AttributeError:
        importances = {name: 1.0 / len(FEATURE_NAMES) for name in FEATURE_NAMES}

    # Persist artifact.
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_path = MODEL_DIR / f"model_{horizon}_{ts}.joblib"
    joblib.dump({"model": clf, "feature_names": FEATURE_NAMES}, artifact_path)

    # Flip previous models for this horizon to inactive, then insert new one.
    db.execute(
        update(MlModel)
        .where(MlModel.horizon == horizon, MlModel.is_active.is_(True))
        .values(is_active=False)
    )
    row = MlModel(
        horizon=horizon,
        model_type="hgbc",
        n_train_samples=int(len(y_train)),
        n_test_samples=int(len(y_test)),
        accuracy=round(acc, 4),
        roc_auc=round(auc, 4) if auc is not None else None,
        brier_score=round(brier, 4),
        feature_importances=importances,
        artifact_path=str(artifact_path),
        is_active=True,
    )
    db.add(row)
    db.flush()
    log.info(
        "trained %s: n_train=%d n_test=%d acc=%.3f auc=%s brier=%.3f -> %s",
        horizon, len(y_train), len(y_test), acc,
        f"{auc:.3f}" if auc is not None else "n/a", brier, artifact_path,
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES_DEFAULT,
                        help=f"Skip a horizon below this many resolved outcomes (default {MIN_SAMPLES_DEFAULT})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ml.train] %(message)s")

    trained = 0
    with session_scope() as db:
        for h in HORIZONS:
            if _train_horizon(db, h, min_samples=args.min_samples):
                trained += 1

    print(f"Trained {trained}/{len(HORIZONS)} horizons.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
