"""add signal_outcomes table for forward-return tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signal_id", sa.Integer, sa.ForeignKey("composite_signals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_score", sa.Integer, nullable=False),
        sa.Column("signal_label", sa.String(20), nullable=False),
        sa.Column("signal_confidence", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Numeric(12, 4)),
        sa.Column("signaled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("return_1d", sa.Numeric(8, 4)),
        sa.Column("return_5d", sa.Numeric(8, 4)),
        sa.Column("return_21d", sa.Numeric(8, 4)),
        sa.Column("resolved_1d_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_5d_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_21d_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_signal_outcomes_signal", "signal_outcomes", ["signal_id"])
    op.create_index("ix_signal_outcomes_ticker", "signal_outcomes", ["ticker_id"])
    op.create_index("ix_signal_outcomes_signaled", "signal_outcomes", [sa.text("signaled_at DESC")])
    # partial index over rows still needing resolution (cheap polling)
    op.create_index(
        "ix_signal_outcomes_pending_1d", "signal_outcomes", ["signaled_at"],
        postgresql_where=sa.text("return_1d IS NULL"),
    )
    op.create_index(
        "ix_signal_outcomes_pending_5d", "signal_outcomes", ["signaled_at"],
        postgresql_where=sa.text("return_5d IS NULL"),
    )
    op.create_index(
        "ix_signal_outcomes_pending_21d", "signal_outcomes", ["signaled_at"],
        postgresql_where=sa.text("return_21d IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_signal_outcomes_pending_21d", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_pending_5d", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_pending_1d", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_signaled", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_ticker", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_signal", table_name="signal_outcomes")
    op.drop_table("signal_outcomes")
