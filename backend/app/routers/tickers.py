"""Ticker management.

Beyond the basic read endpoints, this router exposes the controls that
flip a ticker's `is_active` flag. That flag is the **single switch** that
every worker (ingest, classify, quotes, composite, fundamentals) keys
off when deciding what to spend API credits on — so deactivating a
ticker here immediately stops Finnhub / Claude calls for it.

In v1 the active-set is global (single-user app). Once Firebase auth
lands we'll join a per-user `watchlists` table on top and the API will
read the union as the active set."""
from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Article, ArticleTicker, LlmAnalysis, Ticker
from app.routers._helpers import (
    latest_signal_for, news_payload, quote_for, recent_spark, signal_payload,
)
from app.routers.news import _latest_label, _ticker_symbols
from app.security.auth import current_user, User

router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


class AddTickerRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=200)
    sector: str | None = Field(None, max_length=100)
    industry: str | None = Field(None, max_length=100)
    exchange: str | None = Field(None, max_length=20)


def _normalize_symbol(raw: str) -> str:
    sym = raw.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(400, "invalid symbol — A-Z 0-9 . - only, max 10 chars")
    return sym


@router.get("/tickers")
def list_tickers(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    """Default returns only the active set. Pass include_inactive=true to
    get the full universe — used by the ticker management UI."""
    q = select(Ticker)
    if not include_inactive:
        q = q.where(Ticker.is_active.is_(True))
    q = q.order_by(Ticker.symbol.asc())
    tickers = db.execute(q).scalars().all()
    return [
        {
            "symbol": t.symbol,
            "name": t.name,
            "sector": t.sector,
            "industry": t.industry,
            "exchange": t.exchange,
            "is_active": bool(t.is_active),
        }
        for t in tickers
    ]


@router.post("/tickers/{symbol}/activate")
def activate_ticker(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    sym = _normalize_symbol(symbol)
    t = db.execute(select(Ticker).where(Ticker.symbol == sym)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "ticker not in universe — add it first")
    if not t.is_active:
        db.execute(update(Ticker).where(Ticker.id == t.id).values(is_active=True))
        db.commit()
    return {"symbol": sym, "is_active": True}


@router.post("/tickers/{symbol}/deactivate")
def deactivate_ticker(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Stops every worker from spending API credits on this ticker. Past
    data (articles, signals, outcomes) is preserved — flip it back on
    later and processing resumes."""
    sym = _normalize_symbol(symbol)
    t = db.execute(select(Ticker).where(Ticker.symbol == sym)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "ticker not in universe")
    if t.is_active:
        db.execute(update(Ticker).where(Ticker.id == t.id).values(is_active=False))
        db.commit()
    return {"symbol": sym, "is_active": False}


@router.post("/tickers")
def add_ticker(
    body: AddTickerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Add a new symbol to the universe (active by default). Idempotent
    on symbol — re-adding an existing one just flips it active and
    refreshes the metadata."""
    sym = _normalize_symbol(body.symbol)
    existing = db.execute(select(Ticker).where(Ticker.symbol == sym)).scalar_one_or_none()
    if existing:
        db.execute(
            update(Ticker)
            .where(Ticker.id == existing.id)
            .values(
                name=body.name,
                sector=body.sector or existing.sector,
                industry=body.industry or existing.industry,
                exchange=body.exchange or existing.exchange,
                is_active=True,
            )
        )
        db.commit()
        return {"symbol": sym, "created": False, "is_active": True}

    t = Ticker(
        symbol=sym,
        name=body.name,
        sector=body.sector,
        industry=body.industry,
        exchange=body.exchange,
        is_active=True,
    )
    db.add(t)
    db.commit()
    return {"symbol": sym, "created": True, "is_active": True}


@router.get("/ticker/{symbol}")
def ticker_detail(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if not symbol or len(symbol) > 10:
        raise HTTPException(400, "invalid symbol")
    ticker = db.execute(select(Ticker).where(Ticker.symbol == symbol.upper())).scalar_one_or_none()
    if not ticker:
        raise HTTPException(404, "ticker not tracked")

    sig = latest_signal_for(db, ticker.id)
    q = quote_for(db, ticker.id)
    spark = recent_spark(db, ticker.id, n=60)

    article_ids = [
        a for (a,) in db.execute(
            select(Article.id)
            .join(ArticleTicker, ArticleTicker.article_id == Article.id)
            .where(ArticleTicker.ticker_id == ticker.id)
            .order_by(Article.published_at.desc())
            .limit(10)
        ).all()
    ]
    news_rows = []
    if article_ids:
        articles = db.execute(select(Article).where(Article.id.in_(article_ids))).scalars().all()
        articles.sort(key=lambda a: a.published_at, reverse=True)
        for a in articles:
            news_rows.append(news_payload(
                a, _latest_label(db, a.id), _ticker_symbols(db, a.id)
            ))

    return {
        "symbol": ticker.symbol,
        "name": ticker.name,
        "sector": ticker.sector,
        "is_active": bool(ticker.is_active),
        "signal": signal_payload(ticker, sig, q, spark),
        "news": news_rows,
    }
