"""add_word_embeddings_table

Adds cached semantic embeddings for vocabulary words so new-word enrichment
can retrieve semantically similar existing vocabulary before AI link selection.

Revision ID: 1a2b3c4d5e7f
Revises: e2f3a4b5c6d7
Create Date: 2026-06-27 13:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1a2b3c4d5e7f"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "word_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "word_id",
            sa.String(),
            sa.ForeignKey("words.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="openrouter"),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("word_id", name="uq_word_embedding_word_id"),
    )
    op.create_index("ix_word_embeddings_word_id", "word_embeddings", ["word_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_word_embeddings_word_id", table_name="word_embeddings")
    op.drop_table("word_embeddings")