"""Response-header hardening middleware.

Adds the standard "boring but important" security headers to every
response. Matches the headers a reasonable security scanner expects:
CSP, X-Frame-Options, Referrer-Policy, HSTS (prod only), etc.

The API is JSON-only — there's no HTML being served from here — so we can
ship a very strict CSP (default-src 'none'). The HTML frontend has its
own helmet config."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings = get_settings()

        # The API never serves HTML or executes JS. Lock everything down.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        # Cross-origin isolation — safe defaults for a JSON API.
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        if settings.is_prod:
            # Only set HSTS in prod (so it doesn't pin localhost). 1y + preload.
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Strip a couple of leaky defaults. Starlette's MutableHeaders
        # doesn't implement .pop(), so we use the dict-style del.
        if "server" in response.headers:
            del response.headers["server"]
        return response
