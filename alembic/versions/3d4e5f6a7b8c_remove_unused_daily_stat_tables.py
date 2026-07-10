"""remove unused daily stat tables

Revision ID: 3d4e5f6a7b8c
Revises: 2c3d4e5f6a7b, f2c4e6a8b0d1
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3d4e5f6a7b8c"
down_revision = ("2c3d4e5f6a7b", "f2c4e6a8b0d1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("daily_learning_stats")
    op.drop_table("daily_stats")


def downgrade() -> None:
    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_minutes", sa.Integer(), nullable=True),
        sa.Column("words_encountered", sa.Integer(), nullable=True),
        sa.Column("words_mastered", sa.Integer(), nullable=True),
        sa.Column("activities_completed", sa.Integer(), nullable=True),
        sa.Column("xp_earned", sa.Integer(), nullable=True),
        sa.Column("session_count", sa.Integer(), nullable=True),
        sa.Column("average_engagement", sa.Float(), nullable=True),
        sa.Column("daily_goal_progress", sa.Integer(), nullable=True),
        sa.Column("goal_achieved", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_stats_date", "daily_stats", ["date"], unique=False)
    op.create_index("ix_daily_stats_id", "daily_stats", ["id"], unique=False)

    op.create_table(
        "daily_learning_stats",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("words_learned", sa.Integer(), nullable=True),
        sa.Column("words_reviewed", sa.Integer(), nullable=True),
        sa.Column("new_words_mastered", sa.Integer(), nullable=True),
        sa.Column("total_learning_time", sa.Integer(), nullable=True),
        sa.Column("active_learning_time", sa.Integer(), nullable=True),
        sa.Column("session_count", sa.Integer(), nullable=True),
        sa.Column("categories_studied", sa.JSON(), nullable=True),
        sa.Column("games_played", sa.Integer(), nullable=True),
        sa.Column("games_completed", sa.Integer(), nullable=True),
        sa.Column("stories_read", sa.Integer(), nullable=True),
        sa.Column("bedtime_stories_generated", sa.Integer(), nullable=True),
        sa.Column("xp_earned", sa.Integer(), nullable=True),
        sa.Column("average_accuracy", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_daily_learning_stats_child_id",
        "daily_learning_stats",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        "ix_daily_learning_stats_date",
        "daily_learning_stats",
        ["date"],
        unique=False,
    )
    op.create_index(
        "ix_daily_learning_stats_id",
        "daily_learning_stats",
        ["id"],
        unique=False,
    )