FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Build deps + libpq for psycopg. curl is kept around for the container
# healthcheck. Everything else is purged in the same RUN to keep the
# layer small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as a non-root user. The api/worker processes do not need to write
# anywhere under /app at runtime, so this works cleanly with the
# read_only: true filesystem in docker-compose.prod.yml.
RUN useradd --create-home --shell /usr/sbin/nologin signal && chown -R signal:signal /app
USER signal

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Default to running the API. docker-compose overrides this with --reload
# for dev, and the worker service overrides it with `python -m app.workers.run`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
