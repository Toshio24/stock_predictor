"""URL-hash dedup backed by Redis SET (with DB unique constraint as fallback)."""
import hashlib
import redis

from app.config import get_settings

_settings = get_settings()
_r = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
DEDUP_KEY = "signal:seen_urls"
DEDUP_TTL = 60 * 60 * 24 * 7  # 7 days


def url_hash(url: str) -> str:
    return hashlib.sha256((url or "").strip().lower().encode()).hexdigest()


def seen(url: str) -> bool:
    if not url:
        return False
    return bool(_r.sismember(DEDUP_KEY, url_hash(url)))


def mark_seen(url: str) -> None:
    if not url:
        return
    _r.sadd(DEDUP_KEY, url_hash(url))
    # rotate occasionally — refresh TTL on the whole set each call is cheap
    _r.expire(DEDUP_KEY, DEDUP_TTL)
