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


class SignalOutcome(Base):
    """Forward-return measurements for a single composite signal.

    Created when CompositeSignal is computed; the resolver worker fills in
    `realized_return_*` once the target dates pass. Joining outcomes against
    composite_signals is how we measure whether the system has predictive
    edge. No outcome row → signal hasn't matured yet."""
    __tablename__ = "signal_outcomes"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("composite_signals.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_score = Column(Integer, nullable=False)        # composite score at signal time (0-100)
    signal_label = Column(String(20), nullable=False)     # bullish | bearish | neutral
    signal_confidence = Column(Integer, nullable=False)   # confidence at signal time (0-100)
    entry_price = Column(Numeric(12, 4))                  # close-of-day price when signal fired
    signaled_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Forward returns — populated by the resolver worker as time passes.
    # Each is the simple percent change from entry_price to the close N
    # trading days later. NULL until resolved.
    return_1d = Column(Numeric(8, 4))
    return_5d = Column(Numeric(8, 4))
    return_21d = Column(Numeric(8, 4))

    # When each horizon resolved (so we can tell pending from resolved).
    resolved_1d_at = Column(DateTime(timezone=True))
    resolved_5d_at = Column(DateTime(timezone=True))
    resolved_21d_at = Column(DateTime(timezone=True))


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


class MacroIndicator(Base):
    """FRED macro series snapshot. Single row per (series_id, observed_at)."""
    __tablename__ = "macro_indicators"

    id = Column(Integer, primary_key=True)
    series_id = Column(String(40), nullable=False)
    label = Column(String(120))
    value = Column(Numeric(14, 4))
    observed_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("series_id", "observed_at", name="uq_macro_series_observed"),
    )


class Fundamentals(Base):
    """Per-ticker snapshot of valuation + financial-health metrics."""
    __tablename__ = "fundamentals"

    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    pe_ratio = Column(Numeric(12, 4))
    eps_ttm = Column(Numeric(12, 4))
    market_cap = Column(Numeric(20, 2))
    dividend_yield = Column(Numeric(8, 4))
    beta = Column(Numeric(8, 4))
    revenue_ttm = Column(Numeric(20, 2))
    profit_margin = Column(Numeric(8, 4))
    debt_to_equity = Column(Numeric(8, 4))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EarningsEvent(Base):
    """Scheduled or historical earnings date for a ticker."""
    __tablename__ = "earnings_events"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False)
    event_date = Column(DateTime(timezone=True), nullable=False)
    period = Column(String(20))
    eps_estimate = Column(Numeric(12, 4))
    eps_actual = Column(Numeric(12, 4))
    revenue_estimate = Column(Numeric(20, 2))
    revenue_actual = Column(Numeric(20, 2))
    hour = Column(String(10))
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ticker_id", "event_date", name="uq_earnings_ticker_date"),
    )


class MlModel(Base):
    """One row per training run. We keep history so the dashboard can show
    'model X trained 6h ago' and we can roll back if a new model is worse."""
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True)
    horizon = Column(String(10), nullable=False)              # "1d" / "5d" / "21d"
    model_type = Column(String(50), nullable=False)            # "hgbc" for now
    trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    n_train_samples = Column(Integer, nullable=False)
    n_test_samples = Column(Integer, nullable=False)
    accuracy = Column(Numeric(6, 4))
    roc_auc = Column(Numeric(6, 4))
    brier_score = Column(Numeric(6, 4))
    feature_importances = Column(JSON)
    artifact_path = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class MlPrediction(Base):
    """Calibrated probability of a positive forward return for a single
    composite signal. Filled in by the composite worker the moment a new
    signal is created; the realized_* columns are populated by the
    outcomes worker once the horizon resolves."""
    __tablename__ = "ml_predictions"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("composite_signals.id", ondelete="CASCADE"), nullable=False)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False)
    model_id_1d = Column(Integer, ForeignKey("ml_models.id", ondelete="SET NULL"))
    model_id_5d = Column(Integer, ForeignKey("ml_models.id", ondelete="SET NULL"))
    model_id_21d = Column(Integer, ForeignKey("ml_models.id", ondelete="SET NULL"))
    prob_up_1d = Column(Numeric(6, 4))
    prob_up_5d = Column(Numeric(6, 4))
    prob_up_21d = Column(Numeric(6, 4))
    predicted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    realized_1d = Column(Numeric(8, 4))
    realized_5d = Column(Numeric(8, 4))
    realized_21d = Column(Numeric(8, 4))


Index("ix_articles_published_desc", Article.published_at.desc())
Index("ix_composite_ticker_time", CompositeSignal.ticker_id, CompositeSignal.computed_at.desc())
Index("ix_llm_ticker_time", LlmAnalysis.ticker_id, LlmAnalysis.created_at.desc())
Index("ix_daily_bars_ticker_date", DailyBar.ticker_id, DailyBar.bar_date.desc())
Index("ix_macro_series_observed", MacroIndicator.series_id, MacroIndicator.observed_at.desc())
Index("ix_earnings_ticker_date", EarningsEvent.ticker_id, EarningsEvent.event_date.asc())
Index("ix_ml_models_horizon_active", MlModel.horizon, MlModel.is_active)
Index("ix_ml_predictions_signal", MlPrediction.signal_id)
Index("ix_ml_predictions_predicted", MlPrediction.predicted_at.desc())
