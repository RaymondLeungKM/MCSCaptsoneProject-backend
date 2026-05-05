"""add active vocab approval fields

Revision ID: b7c8d9e0f1a2
Revises: bc4d5e6f7a81, c2d4e6f8a0b1
Create Date: 2026-05-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = ("bc4d5e6f7a81", "c2d4e6f8a0b1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "word_progress",
        sa.Column(
            "pending_active_vocab_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "word_progress",
        sa.Column("active_vocab_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "word_progress",
        "pending_active_vocab_approval",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("word_progress", "active_vocab_requested_at")
    op.drop_column("word_progress", "pending_active_vocab_approval")