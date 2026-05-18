"""Single entrypoint that runs every background worker in one process.
Docker-compose `worker` service runs this. Good enough for v1 — split out
later if any worker needs its own scaling envelope."""
import asyncio
import logging

from app.workers import ingest_news, classify, quotes, composite


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    await asyncio.gather(
        ingest_news.run(),
        classify.run(),
        quotes.run(),
        composite.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
