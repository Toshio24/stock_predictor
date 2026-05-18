from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Numeric, Boolean,
    ForeignKey, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Ticker(Base):
    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))
    industry = Column(String(100))
    exchange = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quotes = relationship("Quote", back_populates="ticker", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), unique=True, index=True)   # finnhub article id
    source = Column(String(100), nullable=False)
    source_url = Column(Text)
    headline = Column(Text, nullable=False)
    summary = Column(Text)
    image_url = Column(Text)
    category = Column(String(50))                                # general | company
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    url_hash = Column(String(64), unique=True, index=True)       # dedup
    is_classified = Column(Boolean, default=False, index=True)

    tickers = relationship("ArticleTicker", back_populates="article", cascade="all, delete-orphan")
    analyses = relationship("LlmAnalysis", back_populates="article", cascade="all, delete-orphan")


class ArticleTicker(Base):
    __tablename__ = "article_tickers"

    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    is_primary = Column(Boolean, default=True)

    article = relationship("Article", back_populates="tickers")
    ticker = relationship("Ticker")


class LlmAnalysis(Base):
    __tablename__ = "llm_analyses"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), index=True)
    model_used = Column(String(80), nullable=False)
    sentiment_score = Column(Numeric(5, 3))      # -1.000 .. +1.000
    sentiment_label = Column(String(20))         # bullish | bearish | neutral
    confidence = Column(Numeric(4, 3))           # 0.000 .. 1.000
    event_type = Column(String(50))
    is_material = Column(Boolean, nullable=True, index=True)  # null = legacy row, treat as material
    time_horizon = Column(String(20), nullable=True)
    rationale = Column(Text)
    key_factors = Column(JSON)
    latency_ms = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Numeric(10, 6))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    article = relationship("Article", back_populates="analyses")
    ticker = relationship("Ticker")


class CompositeSignal(Base):
    __tablename__ = "composite_signals"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), index=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    signal_label = Column(String(20))            # bullish | bearish | neutral
    score = Column(Integer)                      # 0..100 (frontend-friendly)
    confidence = Column(Integer)                 # 0..100
    sentiment_score = Column(Numeric(5, 3))      # underlying -1..+1
    sample_size = Column(Integer)                # articles considered
    rationale = Column(Text)

    ticker = relationship("Ticker")


class Quote(Base):
    __tablename__ = "quotes"

    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    price = Column(Numeric(12, 4))
    change = Column(Numeric(10, 4))              # percent
    high = Column(Numeric(12, 4))
    low = Column(Numeric(12, 4))
    previous_close = Column(Numeric(12, 4))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ticker = relationship("Ticker", back_populates="quotes")


class DailyBar(Base):
    """Daily OHLCV bar, one row per (ticker, date). TimescaleDB hypertable
    on `bar_date`. Pulled from Yahoo's chart API; no API key required."""
    __tablename__ = "daily_bars"

    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    bar_date = Column(DateTime(timezone=True), primary_key=True)
    open = Column(Numeric(12, 4))
    high = Column(Numeric(12, 4))
    low = Column(Numeric(12, 4))
    close = Column(Numeric(12, 4))
    volume = Column(BigInteger)


Index("ix_articles_published_desc", Article.published_at.desc())
Index("ix_composite_ticker_time", CompositeSignal.ticker_id, CompositeSignal.computed_at.desc())
Index("ix_llm_ticker_time", LlmAnalysis.ticker_id, LlmAnalysis.created_at.desc())
Index("ix_daily_bars_ticker_date", DailyBar.ticker_id, DailyBar.bar_date.desc())
