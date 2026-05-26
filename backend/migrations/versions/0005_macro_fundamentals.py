"""add macro_indicators, fundamentals, earnings_events tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- macro_indicators: FRED series snapshots ---------------------------
    op.create_table(
        "macro_indicators",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.String(40), nullable=False),     # e.g. CPIAUCSL, FEDFUNDS
        sa.Column("label", sa.String(120)),
        sa.Column("value", sa.Numeric(14, 4)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("series_id", "observed_at", name="uq_macro_series_observed"),
    )
    op.create_index("ix_macro_series_observed", "macro_indicators", ["series_id", sa.text("observed_at DESC")])

    # --- fundamentals: snapshot of P/E, EPS, etc. per ticker ---------------
    op.create_table(
        "fundamentals",
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pe_ratio", sa.Numeric(12, 4)),
        sa.Column("eps_ttm", sa.Numeric(12, 4)),
        sa.Column("market_cap", sa.Numeric(20, 2)),
        sa.Column("dividend_yield", sa.Numeric(8, 4)),
        sa.Column("beta", sa.Numeric(8, 4)),
        sa.Column("revenue_ttm", sa.Numeric(20, 2)),
        sa.Column("profit_margin", sa.Numeric(8, 4)),
        sa.Column("debt_to_equity", sa.Numeric(8, 4)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # --- earnings_events: scheduled + historical earnings dates ------------
    op.create_table(
        "earnings_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period", sa.String(20)),         # e.g. "Q1 2026"
        sa.Column("eps_estimate", sa.Numeric(12, 4)),
        sa.Column("eps_actual", sa.Numeric(12, 4)),
        sa.Column("revenue_estimate", sa.Numeric(20, 2)),
        sa.Column("revenue_actual", sa.Numeric(20, 2)),
        sa.Column("hour", sa.String(10)),           # "bmo" / "amc" / ""
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("ticker_id", "event_date", name="uq_earnings_ticker_date"),
    )
    op.create_index("ix_earnings_ticker_date", "earnings_events", ["ticker_id", sa.text("event_date ASC")])


def downgrade() -> None:
    op.drop_index("ix_earnings_ticker_date", table_name="earnings_events")
    op.drop_table("earnings_events")
    op.drop_table("fundamentals")
    op.drop_index("ix_macro_series_observed", table_name="macro_indicators")
    op.drop_table("macro_indicators")
