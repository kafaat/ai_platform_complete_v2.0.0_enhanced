"""AI recommendation runtime persistence

Revision ID: 0002_ai_recommendation_runtime
Revises: 0001_baseline
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_ai_recommendation_runtime"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_reviews",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("field_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("recommendation_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(length=64),
            sa.ForeignKey("recommendation_reviews.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("reviewer_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("modifications", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("recommendation_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("field_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("actual_yield", sa.Float(), nullable=True),
        sa.Column("predicted_yield", sa.Float(), nullable=True),
        sa.Column("actual_cost", sa.Float(), nullable=True),
        sa.Column("standard_cost", sa.Float(), nullable=True),
        sa.Column("actual_water", sa.Float(), nullable=True),
        sa.Column("standard_water", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_feedback")
    op.drop_table("review_decisions")
    op.drop_table("recommendation_reviews")
