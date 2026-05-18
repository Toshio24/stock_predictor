"""Quote refresher. Hits Finnhub /quote for every tracked ticker on a slow
cadence (default 5 min) and upserts into the quotes table."""
import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import session_scope
from app.models import Ticker, Quote
from app.ingest.finnhub import FinnhubClient

log = logging.getLogger(__name__)
_settings = get_settings()


def _upsert(ticker_id: int, q: dict) -> None:
    if not q or q.get("c") in (None, 0):
        return
    with session_scope() as db:
        stmt = pg_insert(Quote).values(
            ticker_id=ticker_id,
            price=Decimal(str(q.get("c"))),
            change=Decimal(str(q.get("dp", 0))),
            high=Decimal(str(q.get("h", 0))),
            low=Decimal(str(q.get("l", 0))),
            previous_close=Decimal(str(q.get("pc", 0))),
        ).on_conflict_do_update(
            index_elements=["ticker_id"],
            set_={
                "price": Decimal(str(q.get("c"))),
                "change": Decimal(str(q.get("dp", 0))),
                "high": Decimal(str(q.get("h", 0))),
                "low": Decimal(str(q.get("l", 0))),
                "previous_close": Decimal(str(q.get("pc", 0))),
            },
        )
        db.execute(stmt)


async def run() -> None:
    log.info("quote refresher starting")
    client = FinnhubClient()
    try:
        while True:
            with session_scope() as db:
                rows = db.execute(select(Ticker.id, Ticker.symbol).where(Ticker.is_active.is_(True))).all()
            for ticker_id, symbol in rows:
                try:
                    q = await client.quote(symbol)
                    _upsert(ticker_id, q)
                except Exception as e:
                    log.warning(f"quote {symbol}: {e}")
                await asyncio.sleep(1.2)  # ~50/min, well under Finnhub free
            log.info(f"refreshed {len(rows)} quotes; sleeping {_settings.quote_refresh_seconds}s")
            await asyncio.sleep(_settings.quote_refresh_seconds)
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [quotes] %(message)s")
    asyncio.run(run())
