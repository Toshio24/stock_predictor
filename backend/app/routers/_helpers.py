"""Shared helpers for turning ORM rows into the shapes the frontend mock used."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import (
    Article, ArticleTicker, CompositeSignal, LlmAnalysis, Quote, Ticker
)


def time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    s = int(delta.total_seconds())
    if s < 60: return f"{s}s ago"
    m = s // 60
    if m < 60: return f"{m}m ago"
    h = m // 60
    if h < 24: return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"


def latest_signal_for(db: Session, ticker_id: int) -> CompositeSignal | None:
    return db.execute(
        select(CompositeSignal)
        .where(CompositeSignal.ticker_id == ticker_id)
        .order_by(CompositeSignal.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def quote_for(db: Session, ticker_id: int) -> Quote | None:
    return db.execute(select(Quote).where(Quote.ticker_id == ticker_id)).scalar_one_or_none()


def recent_spark(db: Session, ticker_id: int, n: int = 24) -> list[float]:
    """Sentiment-score sparkline — uses last N LLM analyses, oldest→newest."""
    rows = db.execute(
        select(LlmAnalysis.sentiment_score)
        .where(LlmAnalysis.ticker_id == ticker_id)
        .order_by(LlmAnalysis.created_at.desc())
        .limit(n)
    ).all()
    return [float(s) for (s,) in reversed(rows) if s is not None]


def signal_payload(ticker: Ticker, signal: CompositeSignal | None, quote: Quote | None,
                   spark: list[float]) -> dict:
    """Shape matches data/mock.js signals on the frontend."""
    label = (signal.signal_label if signal else "neutral") or "neutral"
    score = signal.score if signal else 50
    confidence = signal.confidence if signal else 30
    rationale = signal.rationale if signal else "Awaiting signal — no classified news yet."
    updated_at = time_ago(signal.computed_at if signal else None)

    price = float(quote.price) if quote and quote.price else 0.0
    change = float(quote.change) if quote and quote.change is not None else 0.0

    return {
        "ticker": ticker.symbol,
        "name": ticker.name,
        "sector": ticker.sector,
        "signal": label,
        "price": price,
        "change": change,
        "score": int(score),
        "confidence": int(confidence),
        "spark": spark,
        "rationale": rationale,
        "updatedAt": updated_at,
    }


def news_payload(article: Article, sentiment_label: str | None,
                 tickers: Iterable[str]) -> dict:
    return {
        "id": article.id,
        "headline": article.headline,
        "source": article.source,
        "category": article.category or "general",
        "sentiment": (sentiment_label or "neutral"),
        "tickers": list(tickers),
        "summary": (article.summary or "")[:600],
        "url": article.source_url,
        "timeAgo": time_ago(article.published_at),
        "featured": False,
    }
