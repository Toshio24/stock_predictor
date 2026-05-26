"""Macro overlay — surfaces FRED indicators (CPI, fed funds, 10y, unemp).
The actual fetching lives in `app.workers.macro`; this router only reads."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MacroIndicator
from app.security.auth import current_user, User

router = APIRouter()


@router.get("/macro")
def list_macro(
    series: str | None = Query(None, max_length=20, pattern=r"^[A-Za-z0-9_]{1,20}$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    q = select(MacroIndicator).order_by(MacroIndicator.observed_at.desc()).limit(200)
    if series:
        q = q.where(MacroIndicator.series_id == series.upper())
    rows = db.execute(q).scalars().all()
    return [
        {
            "series": r.series_id,
            "value": float(r.value) if r.value is not None else None,
            "observed_at": r.observed_at.isoformat() if r.observed_at else None,
            "label": r.label,
        }
        for r in rows
    ]
