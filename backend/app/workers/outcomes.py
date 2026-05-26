"""Outcome resolver. Reads pending SignalOutcome rows and fills in the
realized forward return once enough trading days have passed.

For each signal, we compare entry_price (the close at signal time) to the
close N trading days later, where N ∈ {1, 5, 21}. We look up the close
from daily_bars; if the bar doesn't exist yet (weekend, holiday, or just
the future), we leave it NULL and try again next pass."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, or_, update
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import DailyBar, MlPrediction, SignalOutcome

log = logging.getLogger(__name__)

RESOLVER_CADENCE_SECONDS = 60 * 60   # every hour is plenty


def _nth_trading_close(db: Session, ticker_id: int, after: datetime, n: int) -> Optional[float]:
    """Returns the close price of the n-th trading bar strictly after
    `after`. None if we don't have that many bars yet."""
    rows = db.execute(
        select(DailyBar.close)
        .where(DailyBar.ticker_id == ticker_id, DailyBar.bar_date > after)
        .order_by(DailyBar.bar_date.asc())
        .limit(n)
    ).all()
    if len(rows) < n:
        return None
    return float(rows[-1][0]) if rows[-1][0] is not None else None


def _pct(entry: float, exit_: float) -> Decimal:
    return Decimal(str(round(((exit_ - entry) / entry) * 100, 4)))


def _resolve_one(db: Session, row: SignalOutcome) -> tuple[bool, dict]:
    """Try to fill in any horizons whose bars now exist. Returns
    (changed, summary_dict)."""
    if row.entry_price is None or float(row.entry_price) <= 0:
        return False, {}
    entry = float(row.entry_price)
    changed = False
    now = datetime.now(timezone.utc)
    summary = {}

    for horizon, col_return, col_resolved in (
        (1, "return_1d", "resolved_1d_at"),
        (5, "return_5d", "resolved_5d_at"),
        (21, "return_21d", "resolved_21d_at"),
    ):
        if getattr(row, col_return) is not None:
            continue
        exit_close = _nth_trading_close(db, row.ticker_id, row.signaled_at, horizon)
        if exit_close is None:
            continue
        pct = _pct(entry, exit_close)
        setattr(row, col_return, pct)
        setattr(row, col_resolved, now)
        summary[f"{horizon}d"] = float(pct)
        changed = True
    return changed, summary


def _resolve_pending(db: Session, limit: int = 200) -> int:
    """One pass — pick up signals with at least one unresolved horizon."""
    rows = db.execute(
        select(SignalOutcome)
        .where(or_(
            SignalOutcome.return_1d.is_(None),
            SignalOutcome.return_5d.is_(None),
            SignalOutcome.return_21d.is_(None),
        ))
        .order_by(SignalOutcome.signaled_at.asc())
        .limit(limit)
    ).scalars().all()

    n_changed = 0
    for row in rows:
        changed, summary = _resolve_one(db, row)
        if changed:
            n_changed += 1
            log.info(f"resolved signal {row.signal_id} ({row.signal_label} score={row.signal_score}): {summary}")
            # Mirror the realised return onto any matching ML prediction
            # so the performance dashboard can read it without joining.
            values = {}
            if "1d" in summary and row.return_1d is not None:
                values["realized_1d"] = row.return_1d
            if "5d" in summary and row.return_5d is not None:
                values["realized_5d"] = row.return_5d
            if "21d" in summary and row.return_21d is not None:
                values["realized_21d"] = row.return_21d
            if values:
                db.execute(
                    update(MlPrediction)
                    .where(MlPrediction.signal_id == row.signal_id)
                    .values(**values)
                )
    return n_changed


async def run() -> None:
    log.info("outcome resolver starting")
    while True:
        try:
            with session_scope() as db:
                n = _resolve_pending(db)
            if n:
                log.info(f"outcome pass: {n} signals advanced")
        except Exception:
            log.exception("outcome resolver crashed (will retry)")
        await asyncio.sleep(RESOLVER_CADENCE_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [outcomes] %(message)s")
    asyncio.run(run())
