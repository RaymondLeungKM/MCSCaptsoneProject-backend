"""add_review_queue_decisions

Stores candidate-level graph-informed review queue decisions for later
privacy-aware offline evaluation and policy comparisons.

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f7a
Create Date: 2026-07-10 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2c3d4e5f6a7b"
down_revision = "1b2c3d4e5f7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_queue_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "child_id",
            sa.String(),
            sa.ForeignKey("children.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "word_id",
            sa.String(),
            sa.ForeignKey("words.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("candidate_pool_rank", sa.Integer(), nullable=False),
        sa.Column("final_queue_rank", sa.Integer(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("queue_reason", sa.String(), nullable=False, server_default="balance"),
        sa.Column("feature_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_review_queue_decisions_child_id",
        "review_queue_decisions",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_queue_decisions_word_id",
        "review_queue_decisions",
        ["word_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_queue_decisions_policy_version",
        "review_queue_decisions",
        ["policy_version"],
        unique=False,
    )
    op.create_index(
        "ix_review_queue_decisions_generated_at",
        "review_queue_decisions",
        ["generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_review_queue_decisions_generated_at", table_name="review_queue_decisions")
    op.drop_index("ix_review_queue_decisions_policy_version", table_name="review_queue_decisions")
    op.drop_index("ix_review_queue_decisions_word_id", table_name="review_queue_decisions")
    op.drop_index("ix_review_queue_decisions_child_id", table_name="review_queue_decisions")
    op.drop_table("review_queue_decisions")
