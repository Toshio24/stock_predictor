from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Article, ArticleTicker, LlmAnalysis, Ticker
from app.routers._helpers import (
    latest_signal_for, news_payload, quote_for, recent_spark, signal_payload,
)
from app.routers.news import _latest_label, _ticker_symbols

router = APIRouter()


@router.get("/tickers")
def list_tickers(db: Session = Depends(get_db)) -> list[dict]:
    tickers = db.execute(select(Ticker).where(Ticker.is_active.is_(True))).scalars().all()
    return [
        {"symbol": t.symbol, "name": t.name, "sector": t.sector, "exchange": t.exchange}
        for t in tickers
    ]


@router.get("/ticker/{symbol}")
def ticker_detail(symbol: str, db: Session = Depends(get_db)) -> dict:
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
        "signal": signal_payload(ticker, sig, q, spark),
        "news": news_rows,
    }
