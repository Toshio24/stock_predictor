"""add ml_models + ml_predictions tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-18

  ml_models       — metadata about each trained model (one row per training run)
  ml_predictions  — one row per composite signal: the model's predicted
                    probability of a profitable forward return per horizon,
                    plus the realized outcome once known.
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_models",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("horizon", sa.String(10), nullable=False),       # "1d" / "5d" / "21d"
        sa.Column("model_type", sa.String(50), nullable=False),    # "hgbc"
        sa.Column("trained_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("n_train_samples", sa.Integer, nullable=False),
        sa.Column("n_test_samples", sa.Integer, nullable=False),
        sa.Column("accuracy", sa.Numeric(6, 4)),                   # holdout accuracy
        sa.Column("roc_auc", sa.Numeric(6, 4)),
        sa.Column("brier_score", sa.Numeric(6, 4)),
        sa.Column("feature_importances", sa.JSON),                 # {feature: importance}
        sa.Column("artifact_path", sa.String(255), nullable=False), # disk path to the joblib file
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
    )
    op.create_index("ix_ml_models_horizon_active", "ml_models", ["horizon", "is_active"])

    op.create_table(
        "ml_predictions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signal_id", sa.Integer, sa.ForeignKey("composite_signals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker_id", sa.Integer, sa.ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id_1d", sa.Integer, sa.ForeignKey("ml_models.id", ondelete="SET NULL")),
        sa.Column("model_id_5d", sa.Integer, sa.ForeignKey("ml_models.id", ondelete="SET NULL")),
        sa.Column("model_id_21d", sa.Integer, sa.ForeignKey("ml_models.id", ondelete="SET NULL")),
        sa.Column("prob_up_1d", sa.Numeric(6, 4)),                 # 0..1, P(return_1d > 0)
        sa.Column("prob_up_5d", sa.Numeric(6, 4)),
        sa.Column("prob_up_21d", sa.Numeric(6, 4)),
        sa.Column("predicted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Realized outcomes copied here when SignalOutcome resolves — denormalised
        # so the performance dashboard can compute hit rate in one query.
        sa.Column("realized_1d", sa.Numeric(8, 4)),
        sa.Column("realized_5d", sa.Numeric(8, 4)),
        sa.Column("realized_21d", sa.Numeric(8, 4)),
    )
    op.create_index("ix_ml_predictions_signal", "ml_predictions", ["signal_id"])
    op.create_index("ix_ml_predictions_ticker", "ml_predictions", ["ticker_id"])
    op.create_index("ix_ml_predictions_predicted", "ml_predictions", [sa.text("predicted_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_ml_predictions_predicted", table_name="ml_predictions")
    op.drop_index("ix_ml_predictions_ticker", table_name="ml_predictions")
    op.drop_index("ix_ml_predictions_signal", table_name="ml_predictions")
    op.drop_table("ml_predictions")
    op.drop_index("ix_ml_models_horizon_active", table_name="ml_models")
    op.drop_table("ml_models")
