"""Composite per-ticker signal.

v2 blends two sources:
  - sentiment_score: time-decayed weighted average of recent LLM analyses
    (only the is_material=true ones)
  - technical_score: RSI/SMA/MACD/volume composite from daily bars

Weights are configurable below — defaulting to 0.6 sentiment / 0.4 technical,
which roughly matches the swing-trading weights in the architecture doc §6.1."""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import LlmAnalysis, Ticker, CompositeSignal
from app.signals.technical import score_ticker as technical_score_for


# Component weights — sum to 1.0. Easy knob to retune later.
W_SENTIMENT = 0.6
W_TECHNICAL = 0.4


# Time-decay half-life. Older sentiment counts less.
HALF_LIFE_HOURS = 18
WINDOW_HOURS = 72


def _weight(age_hours: float) -> float:
    return 0.5 ** (age_hours / HALF_LIFE_HOURS)


def _sentiment_component(db: Session, ticker_id: int) -> tuple[float | None, int, float, str]:
    """Returns (sentiment in [-1, +1] or None, sample_size, avg_confidence,
    latest rationale). None means no material analyses in the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    rows = db.execute(
        select(LlmAnalysis.sentiment_score, LlmAnalysis.confidence, LlmAnalysis.created_at,
               LlmAnalysis.rationale, LlmAnalysis.is_material)
        .where(
            LlmAnalysis.ticker_id == ticker_id,
            LlmAnalysis.created_at >= cutoff,
            (LlmAnalysis.is_material.is_(None)) | (LlmAnalysis.is_material.is_(True)),
        )
        .order_by(LlmAnalysis.created_at.desc())
    ).all()

    if not rows:
        return None, 0, 0.0, ""

    now = datetime.now(timezone.utc)
    weighted_sum = 0.0
    weight_total = 0.0
    confs = []
    for score, conf, ts, _r, _mat in rows:
        age = (now - ts).total_seconds() / 3600
        w = _weight(age) * float(conf or 0.5)
        weighted_sum += float(score or 0) * w
        weight_total += w
        confs.append(float(conf or 0.5))

    if weight_total <= 0:
        return None, len(rows), 0.0, ""

    sentiment = weighted_sum / weight_total
    return sentiment, len(rows), sum(confs) / len(confs), rows[0].rationale or ""


def compute_for_ticker(db: Session, ticker_id: int) -> CompositeSignal | None:
    """Build a composite signal row blending sentiment + technical components.
    Returns None when neither component has any data to work with."""
    sent, sample_size, avg_conf, sent_rationale = _sentiment_component(db, ticker_id)
    tech, indicators, tech_rationale = technical_score_for(db, ticker_id)

    if sent is None and tech is None:
        return None

    # Reweight on the fly if one component is missing — we don't want to
    # pull the composite toward zero just because one input is absent.
    weights = []
    components = []
    if sent is not None:
        weights.append(W_SENTIMENT)
        components.append(sent)
    if tech is not None:
        weights.append(W_TECHNICAL)
        components.append(tech)
    weight_sum = sum(weights)
    composite = sum(w * c for w, c in zip(weights, components)) / weight_sum  # [-1, +1]

    # 0-100 score the frontend can show.
    score_0_100 = int(round(50 + composite * 50))
    score_0_100 = max(0, min(100, score_0_100))

    # Confidence: blend sentiment confidence (with sample-size dampening) and
    # whether we had both components (cross-confirmation boosts it).
    sample_factor = 1 - math.exp(-(sample_size or 0) / 4)
    sent_conf = avg_conf * sample_factor if sent is not None else 0.0
    tech_conf = 0.7 if tech is not None else 0.0  # flat baseline; refine later
    pieces = [c for c in (sent_conf, tech_conf) if c > 0]
    confidence = sum(pieces) / len(pieces) if pieces else 0.0
    # Cross-confirmation bonus when sentiment and technical agree on direction
    if sent is not None and tech is not None and (sent > 0) == (tech > 0):
        confidence = min(1.0, confidence + 0.10)
    confidence_0_100 = max(20, min(99, int(round(confidence * 100))))

    if composite >= 0.15:
        label = "bullish"
    elif composite <= -0.15:
        label = "bearish"
    else:
        label = "neutral"

    rationale_bits = []
    if sent is not None and sent_rationale:
        rationale_bits.append(f"News: {sent_rationale[:160]}")
    if tech is not None and tech_rationale:
        rationale_bits.append(f"Technicals: {tech_rationale}")
    rationale = "  |  ".join(rationale_bits) or "Awaiting more data."

    return CompositeSignal(
        ticker_id=ticker_id,
        signal_label=label,
        score=score_0_100,
        confidence=confidence_0_100,
        sentiment_score=Decimal(str(round(sent if sent is not None else 0.0, 3))),
        sample_size=sample_size,
        rationale=rationale,
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
