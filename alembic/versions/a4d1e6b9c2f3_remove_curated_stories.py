"""remove_curated_stories

Revision ID: a4d1e6b9c2f3
Revises: f1a2b3c4d5e6
Create Date: 2026-04-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a4d1e6b9c2f3"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_story_progress_id"), table_name="story_progress")
    op.drop_table("story_progress")
    op.drop_index(op.f("ix_stories_id"), table_name="stories")
    op.drop_table("stories")


def downgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("cover_image_url", sa.String(), nullable=True),
        sa.Column("duration", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("target_words", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "comprehension_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("difficulty", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stories_id"), "stories", ["id"], unique=False)

    op.create_table(
        "story_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("story_id", sa.String(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=True),
        sa.Column("repeat_count", sa.Integer(), nullable=True),
        sa.Column("last_read", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_completed", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_story_progress_id"),
        "story_progress",
        ["id"],
        unique=False,
    )