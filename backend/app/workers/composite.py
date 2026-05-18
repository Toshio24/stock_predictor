"""Composite signal refresher — recomputes one row per ticker every N sec."""
import asyncio
import logging

from app.config import get_settings
from app.db import session_scope
from app.signals.composite import refresh_all

log = logging.getLogger(__name__)
_settings = get_settings()


async def run() -> None:
    log.info("composite refresher starting")
    while True:
        try:
            with session_scope() as db:
                n = refresh_all(db)
            if n:
                log.info(f"refreshed {n} composite signals")
        except Exception:
            log.exception("composite refresh failed")
        await asyncio.sleep(_settings.composite_refresh_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [composite] %(message)s")
    asyncio.run(run())
