"""Daily price worker. Runs once on startup to backfill ~1y of bars per
ticker, then once every PRICE_REFRESH_SECONDS to pick up the latest close.

Idempotent: upserts on (ticker_id, bar_date) so re-runs just refresh today's
incomplete bar without duplicating history."""
import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import session_scope
from app.models import DailyBar, Ticker
from app.ingest.yahoo_prices import fetch_daily_bars

log = logging.getLogger(__name__)
_settings = get_settings()

# Tunable: refresh cadence after the initial backfill.
PRICE_REFRESH_SECONDS = 60 * 60 * 4  # every 4h is plenty for daily bars
INITIAL_RANGE = "1y"   # enough for SMA-200 + buffer
REFRESH_RANGE = "5d"   # only fetch recent bars on subsequent passes


def _upsert(ticker_id: int, bars: list[dict]) -> int:
    if not bars:
        return 0
    n = 0
    with session_scope() as db:
        for b in bars:
            stmt = pg_insert(DailyBar).values(
                ticker_id=ticker_id,
                bar_date=b["bar_date"],
                open=Decimal(str(b["open"])),
                high=Decimal(str(b["high"])),
                low=Decimal(str(b["low"])),
                close=Decimal(str(b["close"])),
                volume=int(b["volume"]),
            ).on_conflict_do_update(
                index_elements=["ticker_id", "bar_date"],
                set_={
                    "open": Decimal(str(b["open"])),
                    "high": Decimal(str(b["high"])),
                    "low": Decimal(str(b["low"])),
                    "close": Decimal(str(b["close"])),
                    "volume": int(b["volume"]),
                },
            )
            db.execute(stmt)
            n += 1
    return n


async def run() -> None:
    log.info("daily price worker starting")
    first_pass = True
    while True:
        try:
            with session_scope() as db:
                rows = db.execute(
                    select(Ticker.id, Ticker.symbol).where(Ticker.is_active.is_(True))
                ).all()
        except Exception:
            log.exception("could not load tickers")
            await asyncio.sleep(60)
            continue

        rng = INITIAL_RANGE if first_pass else REFRESH_RANGE
        total = 0
        for ticker_id, symbol in rows:
            try:
                bars = await fetch_daily_bars(symbol, range_=rng)
            except Exception:
                log.exception(f"prices[{symbol}] crashed")
                continue
            n = _upsert(ticker_id, bars)
            total += n
            await asyncio.sleep(0.8)  # pace requests politely

        log.info(f"price worker: upserted {total} bars across {len(rows)} tickers (range={rng})")
        first_pass = False
        await asyncio.sleep(PRICE_REFRESH_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [prices] %(message)s")
    asyncio.run(run())
