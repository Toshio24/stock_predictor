"""FastAPI entrypoint.

Layers, outermost first:
  TrustedHostMiddleware  — reject host-header spoofing
  CORSMiddleware         — strict origin allow-list
  SecurityHeadersMiddleware — CSP / HSTS / X-Frame / etc.
  SlowAPI rate limiter   — per-IP request budget
  GZip                   — bandwidth saver
  Routers                — versioned under /api/v1
Auth is per-route via `Depends(current_user)`. Health is intentionally
public so load balancers can probe it.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.routers import signals, news, tickers, search, health, macro, fundamentals, ml
from app.security import scrub
from app.security.headers import SecurityHeadersMiddleware
from app.security.rate_limit import limiter

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
scrub.install()  # filter secrets out of every log record

app = FastAPI(
    title="Signal API",
    version="0.1.0",
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
)
app.state.limiter = limiter

# Outer-most: reject requests whose Host header doesn't match. Prevents
# host-header injection / cache poisoning attacks.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list or ["*"])

# CORS — explicit origins only; never allow credentials with "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=512)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so we never bleed a stack trace to clients in prod.
    The full traceback still goes to logs (via the scrubbing filter)."""
    logging.getLogger("app").exception("unhandled error on %s", request.url.path)
    detail = "Internal server error" if settings.is_prod else f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


app.include_router(health.router)
app.include_router(signals.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(tickers.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(macro.router, prefix="/api/v1")
app.include_router(fundamentals.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
