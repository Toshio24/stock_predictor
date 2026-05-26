"""Health endpoints — intentionally unauthenticated so load balancers and
uptime probes can hit them. Reveal nothing about internal state."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@router.get("/readyz", include_in_schema=False)
def readyz() -> dict:
    return {"ok": True}
