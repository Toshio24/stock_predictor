"""Firebase ID token verification for FastAPI.

How auth flows:
  1. Frontend signs the user in with Firebase client SDK (Google / email /
     etc), gets back an ID token (JWT).
  2. Frontend sends `Authorization: Bearer <id_token>` on every backend
     request.
  3. This module verifies the token against Firebase's public keys, checks
     the project id matches FIREBASE_PROJECT_ID, and exposes the verified
     claims as `Depends(current_user)` to routers.

We DON'T pull in the heavy `firebase-admin` SDK — it requires a service
account JSON file at startup, which is one more secret to manage. Instead
we verify the JWT directly against Firebase's public x509 certs (fetched
on demand, cached for 1h). This is exactly what `firebase-admin` does
under the hood, just stripped down.

Auth is **opt-in**: if FIREBASE_PROJECT_ID is empty, `current_user` returns
a synthetic dev user and lets requests through. This keeps local dev
frictionless while production stays locked down (the config validator
above refuses to start prod without a project id).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError

from app.config import get_settings

log = logging.getLogger(__name__)

# Google publishes Firebase ID-token public certs at this URL. We cache
# them in-process; rotation is ~daily, so we re-fetch every hour.
GOOGLE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)
_CERT_CACHE: dict[str, Any] = {"certs": {}, "fetched_at": 0.0}
_CERT_TTL_SECONDS = 3600


@dataclass(frozen=True)
class User:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None
    is_dev: bool = False  # true if we synthesised this in unauth dev mode


async def _fetch_certs() -> dict[str, str]:
    now = time.time()
    if _CERT_CACHE["certs"] and now - _CERT_CACHE["fetched_at"] < _CERT_TTL_SECONDS:
        return _CERT_CACHE["certs"]
    async with httpx.AsyncClient(timeout=5.0) as c:
        r = await c.get(GOOGLE_CERTS_URL)
        r.raise_for_status()
        certs = r.json()
    _CERT_CACHE["certs"] = certs
    _CERT_CACHE["fetched_at"] = now
    return certs


async def _verify_firebase_token(token: str, project_id: str) -> dict:
    """Verify the JWT signature + claims. Returns the decoded payload."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token") from e

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing kid")

    certs = await _fetch_certs()
    cert = certs.get(kid)
    if not cert:
        # Token might be signed with a rotated key — force re-fetch once.
        _CERT_CACHE["fetched_at"] = 0
        certs = await _fetch_certs()
        cert = certs.get(kid)
    if not cert:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key")

    try:
        payload = jwt.decode(
            token,
            cert,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from e
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from e

    if not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    return payload


async def current_user(
    authorization: str | None = Header(default=None),
) -> User:
    """FastAPI dependency. Yields the verified user, or 401s.

    In dev (no FIREBASE_PROJECT_ID) returns a synthetic user so routes work
    locally without auth. We never reach that branch in prod — the config
    validator blocks startup if prod has no project id."""
    settings = get_settings()

    if not settings.auth_enabled:
        return User(uid="dev-user", email="dev@local", email_verified=True, name="Dev", is_dev=True)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = authorization.split(None, 1)[1].strip()
    payload = await _verify_firebase_token(token, settings.firebase_project_id)

    user = User(
        uid=payload["sub"],
        email=payload.get("email"),
        email_verified=bool(payload.get("email_verified")),
        name=payload.get("name"),
    )

    # Optional private-beta allow-list. Empty list = open to any verified user.
    allow = settings.allowed_user_list
    if allow:
        identifier = (user.email or user.uid).lower()
        if identifier not in allow and user.uid.lower() not in allow:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User not in beta allow-list")

    return user


# Convenience aliases for routers to use.
CurrentUser = Depends(current_user)
