"""add daily_bars hypertable

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_bars",
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bar_date", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(12, 4)),
        sa.Column("high", sa.Numeric(12, 4)),
        sa.Column("low", sa.Numeric(12, 4)),
        sa.Column("close", sa.Numeric(12, 4)),
        sa.Column("volume", sa.BigInteger),
    )
    op.create_index("ix_daily_bars_ticker_date", "daily_bars", ["ticker_id", sa.text("bar_date DESC")])
    # Hypertable for time-series queries
    op.execute(
        "SELECT create_hypertable('daily_bars', 'bar_date', if_not_exists => TRUE, migrate_data => TRUE)"
    )


def downgrade() -> None:
    op.drop_index("ix_daily_bars_ticker_date", table_name="daily_bars")
    op.drop_table("daily_bars")
