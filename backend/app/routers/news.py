from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Article, ArticleTicker, LlmAnalysis, Ticker
from app.routers._helpers import news_payload

router = APIRouter()


def _latest_label(db: Session, article_id: int) -> str | None:
    row = db.execute(
        select(LlmAnalysis.sentiment_label)
        .where(LlmAnalysis.article_id == article_id)
        .order_by(LlmAnalysis.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


def _ticker_symbols(db: Session, article_id: int) -> list[str]:
    rows = db.execute(
        select(Ticker.symbol)
        .join(ArticleTicker, ArticleTicker.ticker_id == Ticker.id)
        .where(ArticleTicker.article_id == article_id)
    ).all()
    return [s for (s,) in rows]


@router.get("/news")
def list_news(
    limit: int = Query(40, ge=1, le=100),
    ticker: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    q = (
        select(Article)
        .order_by(Article.published_at.desc())
        .limit(limit)
    )
    if ticker:
        q = (
            select(Article)
            .join(ArticleTicker, ArticleTicker.article_id == Article.id)
            .join(Ticker, Ticker.id == ArticleTicker.ticker_id)
            .where(Ticker.symbol == ticker.upper())
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
    articles = db.execute(q).scalars().unique().all()
    out = []
    for a in articles:
        out.append(news_payload(
            a,
            _latest_label(db, a.id),
            _ticker_symbols(db, a.id),
        ))
    if out:
        out[0]["featured"] = True
    return out
