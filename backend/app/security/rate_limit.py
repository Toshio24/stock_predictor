"""Per-IP rate limiting via slowapi (which wraps limits + starlette).

Why per-IP and not per-user: most routes need to be hittable by an
unauthenticated origin (the public dashboard render). Once auth is fully
enabled we can add a stricter per-uid budget on top, but per-IP is the
right first line of defence against scrapers/scanners.

The limit string is built at import time from settings so a single env
variable controls it without touching code."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

# A token-bucket-ish budget: N per minute, with a small burst headroom.
# slowapi accepts multiple limits as a list, applied in order.
LIMITS = [
    f"{_settings.rate_limit_burst}/10 seconds",
    f"{_settings.rate_limit_per_minute}/minute",
]

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=LIMITS,
    headers_enabled=True,  # surface X-RateLimit-* headers
)
