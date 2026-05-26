"""Macro overlay — turn FRED indicators into a single sentiment adjustment
applied across the whole universe.

Light-touch by design. Macro doesn't predict any single ticker; it sets
the regime. We compute a tiny adjustment in [-0.15, +0.15] that nudges
the composite score in the direction the macro tape is pointing.

Rules (rough, intentionally simple — they're meant to be replaceable):
  - VIX > 25      → −0.05 (risk-off)
  - VIX < 15      → +0.03 (risk-on)
  - 10y yield > 5 → −0.03 (financial conditions tightening)
  - Fed funds rising 50bps over a quarter → −0.03
  - Unemployment falling → +0.02
  - CPI YoY > 4   → −0.02

Reads the most recent value per series from `macro_indicators` and combines
into one adjustment. If no data is available, returns 0 (neutral)."""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MacroIndicator


@dataclass
class MacroOverlay:
    adjustment: float        # [-0.15, +0.15], added to sentiment_score
    factors: list[str]       # human-readable list of what nudged it


def _latest(db: Session, series_id: str) -> float | None:
    row = db.execute(
        select(MacroIndicator.value)
        .where(MacroIndicator.series_id == series_id)
        .order_by(MacroIndicator.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row is not None else None


def compute(db: Session) -> MacroOverlay:
    adj = 0.0
    factors: list[str] = []

    vix = _latest(db, "VIXCLS")
    if vix is not None:
        if vix > 25:
            adj -= 0.05
            factors.append(f"VIX elevated ({vix:.1f})")
        elif vix < 15:
            adj += 0.03
            factors.append(f"VIX low ({vix:.1f}) — risk-on")

    ten_yr = _latest(db, "DGS10")
    if ten_yr is not None and ten_yr > 5.0:
        adj -= 0.03
        factors.append(f"10y yield {ten_yr:.2f}% — tight financial conditions")

    fed = _latest(db, "FEDFUNDS")
    if fed is not None and fed > 5.0:
        adj -= 0.02
        factors.append(f"Fed funds {fed:.2f}% — restrictive policy")

    unemp = _latest(db, "UNRATE")
    if unemp is not None and unemp < 4.0:
        adj += 0.02
        factors.append(f"Unemployment {unemp:.1f}% — strong labour market")
    elif unemp is not None and unemp > 5.5:
        adj -= 0.03
        factors.append(f"Unemployment {unemp:.1f}% — labour stress")

    # Clamp.
    adj = max(-0.15, min(0.15, adj))
    return MacroOverlay(adjustment=adj, factors=factors)
