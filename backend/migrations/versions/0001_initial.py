"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TimescaleDB extension (no-op if already present)
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    op.create_table(
        "tickers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(10), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("exchange", sa.String(20)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tickers_symbol", "tickers", ["symbol"], unique=True)

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("external_id", sa.String(255), unique=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("category", sa.String(50)),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("url_hash", sa.String(64), unique=True),
        sa.Column("is_classified", sa.Boolean, server_default=sa.text("false")),
    )
    op.create_index("ix_articles_published_desc", "articles", [sa.text("published_at DESC")])
    op.create_index("ix_articles_unclassified", "articles", ["is_classified"], postgresql_where=sa.text("is_classified = false"))

    op.create_table(
        "article_tickers",
        sa.Column("article_id", sa.Integer, sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean, server_default=sa.text("true")),
    )
    op.create_index("ix_article_tickers_ticker", "article_tickers", ["ticker_id"])

    op.create_table(
        "llm_analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("article_id", sa.Integer, sa.ForeignKey("articles.id", ondelete="CASCADE")),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE")),
        sa.Column("model_used", sa.String(80), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(5, 3)),
        sa.Column("sentiment_label", sa.String(20)),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("event_type", sa.String(50)),
        sa.Column("rationale", sa.Text),
        sa.Column("key_factors", sa.JSON),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_llm_ticker_time", "llm_analyses", ["ticker_id", sa.text("created_at DESC")])
    op.create_index("ix_llm_article", "llm_analyses", ["article_id"])

    op.create_table(
        "composite_signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("signal_label", sa.String(20)),
        sa.Column("score", sa.Integer),
        sa.Column("confidence", sa.Integer),
        sa.Column("sentiment_score", sa.Numeric(5, 3)),
        sa.Column("sample_size", sa.Integer),
        sa.Column("rationale", sa.Text),
    )
    op.create_index("ix_composite_ticker_time", "composite_signals", ["ticker_id", sa.text("computed_at DESC")])

    op.create_table(
        "quotes",
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("price", sa.Numeric(12, 4)),
        sa.Column("change", sa.Numeric(10, 4)),
        sa.Column("high", sa.Numeric(12, 4)),
        sa.Column("low", sa.Numeric(12, 4)),
        sa.Column("previous_close", sa.Numeric(12, 4)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Make composite_signals a hypertable for time-series scale
    op.execute(
        "SELECT create_hypertable('composite_signals', 'computed_at', if_not_exists => TRUE, migrate_data => TRUE)"
    )


def downgrade() -> None:
    op.drop_table("quotes")
    op.drop_index("ix_composite_ticker_time", table_name="composite_signals")
    op.drop_table("composite_signals")
    op.drop_index("ix_llm_article", table_name="llm_analyses")
    op.drop_index("ix_llm_ticker_time", table_name="llm_analyses")
    op.drop_table("llm_analyses")
    op.drop_index("ix_article_tickers_ticker", table_name="article_tickers")
    op.drop_table("article_tickers")
    op.drop_index("ix_articles_unclassified", table_name="articles")
    op.drop_index("ix_articles_published_desc", table_name="articles")
    op.drop_table("articles")
    op.drop_index("ix_tickers_symbol", table_name="tickers")
    op.drop_table("tickers")
