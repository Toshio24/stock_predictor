"""add is_material + time_horizon to llm_analyses

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_analyses", sa.Column("is_material", sa.Boolean, nullable=True))
    op.add_column("llm_analyses", sa.Column("time_horizon", sa.String(20), nullable=True))
    op.create_index(
        "ix_llm_is_material", "llm_analyses", ["is_material"],
        postgresql_where=sa.text("is_material IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_llm_is_material", table_name="llm_analyses")
    op.drop_column("llm_analyses", "time_horizon")
    op.drop_column("llm_analyses", "is_material")
