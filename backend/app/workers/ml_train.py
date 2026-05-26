"""Auto-retrain worker — once a day, fits a fresh model per horizon using
every resolved outcome accumulated since the last run.

What this does
--------------
On every tick (default: every 24h):
  1. For each horizon (1d, 5d, 21d):
     - count resolved outcomes
     - if ≥ min_samples (default 50), train a new HistGradientBoostingClassifier
     - mark previous active model inactive, promote new one
  2. Log the result (or "still warming up" if data is thin).

What it does NOT do
-------------------
  - Online / incremental learning. Each run does a full retrain. That's
    the right call at our data scale; online learning brings overfitting
    risk and operational complexity we don't need yet.
  - Auto-rollback. If a new model is worse than the old, we still promote
    it (the trainer is honest about that — accuracy / brier score are
    recorded on every MlModel row so the dashboard makes regressions visible).
    If this becomes a problem we can add a hold-out check that refuses to
    promote a model worse than the current active one.

Why daily, not hourly?
----------------------
  - HGBC fits in seconds, but loading + scoring + DB round-trips per
    composite signal mean the active model is read ~50× per minute.
    Daily retrain is plenty given outcomes resolve on 1d/5d/21d timescales.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.db import session_scope
from app.ml.train import HORIZONS, MIN_SAMPLES_DEFAULT, _train_horizon

log = logging.getLogger(__name__)


# How often we retrain. Daily is the sweet spot: outcomes resolve on
# 1d/5d/21d timescales so anything faster is mostly wasted work.
RETRAIN_INTERVAL_SECONDS = 24 * 60 * 60

# Wait a bit after startup before the first run — gives the other workers
# time to come up and avoids hammering the DB during boot.
INITIAL_DELAY_SECONDS = 60


async def _tick() -> None:
    """One retraining pass — runs every horizon, logs results."""
    trained = 0
    skipped = 0
    with session_scope() as db:
        for h in HORIZONS:
            try:
                row = _train_horizon(db, h, min_samples=MIN_SAMPLES_DEFAULT)
                if row is not None:
                    trained += 1
                else:
                    skipped += 1
            except Exception:
                log.exception("auto-retrain failed for horizon=%s", h)
                skipped += 1

    if trained:
        log.info("ml.auto-retrain: trained %d / %d horizons", trained, len(HORIZONS))
    else:
        # Most common case in the first few weeks — not enough outcomes yet.
        log.info(
            "ml.auto-retrain: no horizons had enough resolved outcomes yet "
            "(need ≥%d each); will retry in 24h", MIN_SAMPLES_DEFAULT,
        )


async def run() -> None:
    log.info("ml.auto-retrain worker starting (interval=%ds)", RETRAIN_INTERVAL_SECONDS)
    await asyncio.sleep(INITIAL_DELAY_SECONDS)
    while True:
        try:
            await _tick()
        except Exception:
            log.exception("ml.auto-retrain tick crashed (will retry next interval)")
        await asyncio.sleep(RETRAIN_INTERVAL_SECONDS)
