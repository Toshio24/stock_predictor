"""Composite per-ticker signal from recent LLM analyses.

v1 is sentiment-only — once technicals/fundamentals/macro land, they slot in
here behind a configurable weight (see the architecture doc §6.1)."""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import LlmAnalysis, Ticker, CompositeSignal


# Time-decay half-life. Older sentiment counts less.
HALF_LIFE_HOURS = 18
WINDOW_HOURS = 72


def _weight(age_hours: float) -> float:
    return 0.5 ** (age_hours / HALF_LIFE_HOURS)


def compute_for_ticker(db: Session, ticker_id: int) -> CompositeSignal | None:
    """Build one composite signal row from the last WINDOW_HOURS of analyses."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)

    rows = db.execute(
        select(LlmAnalysis.sentiment_score, LlmAnalysis.confidence, LlmAnalysis.created_at,
               LlmAnalysis.sentiment_label, LlmAnalysis.rationale)
        .where(LlmAnalysis.ticker_id == ticker_id, LlmAnalysis.created_at >= cutoff)
        .order_by(LlmAnalysis.created_at.desc())
    ).all()

    if not rows:
        return None

    now = datetime.now(timezone.utc)
    weighted_sum = 0.0
    weight_total = 0.0
    confidences = []
    latest_rationale = rows[0].rationale

    for score, conf, ts, _label, _r in rows:
        age = (now - ts).total_seconds() / 3600
        w = _weight(age) * float(conf or 0.5)
        weighted_sum += float(score or 0) * w
        weight_total += w
        confidences.append(float(conf or 0.5))

    if weight_total <= 0:
        return None

    sentiment = weighted_sum / weight_total  # [-1, +1]

    # Map sentiment to a 0-100 score the frontend can show.
    score_0_100 = int(round(50 + sentiment * 50))
    score_0_100 = max(0, min(100, score_0_100))

    # Confidence: blend mean LLM-confidence with sample-size dampening.
    sample_size = len(rows)
    sample_factor = 1 - math.exp(-sample_size / 4)
    avg_conf = sum(confidences) / len(confidences)
    confidence_0_100 = int(round(avg_conf * sample_factor * 100))
    confidence_0_100 = max(20, min(99, confidence_0_100))

    if sentiment >= 0.15:
        label = "bullish"
    elif sentiment <= -0.15:
        label = "bearish"
    else:
        label = "neutral"

    return CompositeSignal(
        ticker_id=ticker_id,
        signal_label=label,
        score=score_0_100,
        confidence=confidence_0_100,
        sentiment_score=Decimal(str(round(sentiment, 3))),
        sample_size=sample_size,
        rationale=latest_rationale or "",
    )


def refresh_all(db: Session) -> int:
    ids = [r[0] for r in db.execute(select(Ticker.id).where(Ticker.is_active.is_(True))).all()]
    n = 0
    for tid in ids:
        signal = compute_for_ticker(db, tid)
        if signal is not None:
            db.add(signal)
            n += 1
    return n
