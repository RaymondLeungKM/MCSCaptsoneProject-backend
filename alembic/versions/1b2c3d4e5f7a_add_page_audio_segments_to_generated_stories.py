"""add page audio segments to generated stories

Revision ID: 1b2c3d4e5f7a
Revises: 1a2b3c4d5e7f
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1b2c3d4e5f7a"
down_revision = "1a2b3c4d5e7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "generated_stories" not in inspector.get_table_names():
        return

    generated_story_columns = {
        column["name"] for column in inspector.get_columns("generated_stories")
    }
    if "page_audio_segments" not in generated_story_columns:
        op.add_column(
            "generated_stories",
            sa.Column(
                "page_audio_segments",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "generated_stories" not in inspector.get_table_names():
        return

    generated_story_columns = {
        column["name"] for column in inspector.get_columns("generated_stories")
    }
    if "page_audio_segments" in generated_story_columns:
        op.drop_column("generated_stories", "page_audio_segments")