"""add_p0_analytics_foundation_tables

Revision ID: e2f3a4b5c6d7
Revises: d1b2c3e4f5a6
Create Date: 2026-06-21 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e2f3a4b5c6d7"
down_revision = "d1b2c3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_event_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("child_id", sa.String(), nullable=True),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("mission_id", sa.String(), nullable=True),
        sa.Column("word_id", sa.String(), nullable=True),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("content_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="system"),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_analytics_event_log_idempotency_key"),
    )
    op.create_index(op.f("ix_analytics_event_log_id"), "analytics_event_log", ["id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_event_type"), "analytics_event_log", ["event_type"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_occurred_at"), "analytics_event_log", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_child_id"), "analytics_event_log", ["child_id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_parent_id"), "analytics_event_log", ["parent_id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_mission_id"), "analytics_event_log", ["mission_id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_word_id"), "analytics_event_log", ["word_id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_category_id"), "analytics_event_log", ["category_id"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_content_type"), "analytics_event_log", ["content_type"], unique=False)
    op.create_index(op.f("ix_analytics_event_log_content_id"), "analytics_event_log", ["content_id"], unique=False)

    op.create_table(
        "child_day_analytics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("activity_day", sa.Date(), nullable=False),
        sa.Column("age_band", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("words_encountered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("words_mastered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mission_assigned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mission_completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_minutes_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_score_sum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement_events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_score_avg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active_days_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_days_28d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_id", "activity_day", name="uq_child_day_analytics_child_day"),
    )
    op.create_index(op.f("ix_child_day_analytics_id"), "child_day_analytics", ["id"], unique=False)
    op.create_index(op.f("ix_child_day_analytics_child_id"), "child_day_analytics", ["child_id"], unique=False)
    op.create_index(op.f("ix_child_day_analytics_activity_day"), "child_day_analytics", ["activity_day"], unique=False)
    op.create_index(op.f("ix_child_day_analytics_age_band"), "child_day_analytics", ["age_band"], unique=False)

    op.create_table(
        "mission_outcome_analytics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_day", sa.Date(), nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("mission_id", sa.String(), nullable=True),
        sa.Column("assignment_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="system"),
        sa.Column("context", sa.String(), nullable=True),
        sa.Column("age_band", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("completion_minutes", sa.Integer(), nullable=True),
        sa.Column("is_cluster", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cluster_id", sa.String(), nullable=True),
        sa.Column("seed_word_id", sa.String(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["assignment_id"], ["mission_assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mission_outcome_analytics_id"), "mission_outcome_analytics", ["id"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_activity_day"), "mission_outcome_analytics", ["activity_day"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_child_id"), "mission_outcome_analytics", ["child_id"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_mission_id"), "mission_outcome_analytics", ["mission_id"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_assignment_id"), "mission_outcome_analytics", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_source"), "mission_outcome_analytics", ["source"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_context"), "mission_outcome_analytics", ["context"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_age_band"), "mission_outcome_analytics", ["age_band"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_status"), "mission_outcome_analytics", ["status"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_is_cluster"), "mission_outcome_analytics", ["is_cluster"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_cluster_id"), "mission_outcome_analytics", ["cluster_id"], unique=False)
    op.create_index(op.f("ix_mission_outcome_analytics_seed_word_id"), "mission_outcome_analytics", ["seed_word_id"], unique=False)

    op.create_table(
        "content_performance_analytics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_day", sa.Date(), nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("age_band", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("word_id", sa.String(), nullable=True),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("post_exposure_mastery_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retention_proxy_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "child_id",
            "activity_day",
            "content_type",
            "content_id",
            name="uq_content_performance_child_day_content",
        ),
    )
    op.create_index(op.f("ix_content_performance_analytics_id"), "content_performance_analytics", ["id"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_activity_day"), "content_performance_analytics", ["activity_day"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_child_id"), "content_performance_analytics", ["child_id"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_age_band"), "content_performance_analytics", ["age_band"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_content_type"), "content_performance_analytics", ["content_type"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_content_id"), "content_performance_analytics", ["content_id"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_category_id"), "content_performance_analytics", ["category_id"], unique=False)
    op.create_index(op.f("ix_content_performance_analytics_word_id"), "content_performance_analytics", ["word_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_content_performance_analytics_word_id"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_category_id"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_content_id"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_content_type"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_age_band"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_child_id"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_activity_day"), table_name="content_performance_analytics")
    op.drop_index(op.f("ix_content_performance_analytics_id"), table_name="content_performance_analytics")
    op.drop_table("content_performance_analytics")

    op.drop_index(op.f("ix_mission_outcome_analytics_seed_word_id"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_cluster_id"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_is_cluster"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_status"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_age_band"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_context"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_source"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_assignment_id"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_mission_id"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_child_id"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_activity_day"), table_name="mission_outcome_analytics")
    op.drop_index(op.f("ix_mission_outcome_analytics_id"), table_name="mission_outcome_analytics")
    op.drop_table("mission_outcome_analytics")

    op.drop_index(op.f("ix_child_day_analytics_age_band"), table_name="child_day_analytics")
    op.drop_index(op.f("ix_child_day_analytics_activity_day"), table_name="child_day_analytics")
    op.drop_index(op.f("ix_child_day_analytics_child_id"), table_name="child_day_analytics")
    op.drop_index(op.f("ix_child_day_analytics_id"), table_name="child_day_analytics")
    op.drop_table("child_day_analytics")

    op.drop_index(op.f("ix_analytics_event_log_content_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_content_type"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_category_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_word_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_mission_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_parent_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_child_id"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_occurred_at"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_event_type"), table_name="analytics_event_log")
    op.drop_index(op.f("ix_analytics_event_log_id"), table_name="analytics_event_log")
    op.drop_table("analytics_event_log")