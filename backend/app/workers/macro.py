"""Macro worker — pulls FRED series every hour and upserts them.

Cheap: 6 series × 1 call each = 6 HTTP calls/hr. FRED is free, no key
rotation concerns, no rate limits worth worrying about at this rate."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import session_scope
from app.ingest.macro.fred import fetch_all
from app.models import MacroIndicator

log = logging.getLogger(__name__)


async def _tick() -> None:
    observations = await fetch_all()
    if not observations:
        return
    with session_scope() as db:
        for obs in observations:
            stmt = insert(MacroIndicator).values(
                series_id=obs.series_id,
                label=obs.label,
                value=obs.value,
                observed_at=obs.observed_at,
            )
            # Upsert on (series_id, observed_at). If we re-fetch the same
            # observation later (e.g. FRED revises a stale day), refresh
            # the value but don't dupe rows.
            stmt = stmt.on_conflict_do_update(
                constraint="uq_macro_series_observed",
                set_={"value": stmt.excluded.value, "label": stmt.excluded.label},
            )
            db.execute(stmt)
    log.info("macro: refreshed %d series", len(observations))


async def run() -> None:
    settings = get_settings()
    while True:
        try:
            await _tick()
        except Exception:
            log.exception("macro tick failed")
        await asyncio.sleep(settings.macro_refresh_seconds)
