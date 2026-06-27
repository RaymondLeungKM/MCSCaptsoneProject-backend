"""
P0 analytics foundation models.

These tables provide a shared, privacy-safe data layer for later graph,
benchmark, and admin analytics features.
"""
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class AnalyticsEventLog(Base):
    """Canonical append-only analytics event log with idempotency guard."""

    __tablename__ = "analytics_event_log"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_analytics_event_log_idempotency_key"),
    )

    id = Column(String, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)

    child_id = Column(String, ForeignKey("children.id", ondelete="SET NULL"), index=True)
    parent_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    mission_id = Column(String, ForeignKey("missions.id", ondelete="SET NULL"), index=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="SET NULL"), index=True)
    category_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), index=True)

    content_type = Column(String, index=True)
    content_id = Column(String, index=True)

    source = Column(String, nullable=False, default="system")
    idempotency_key = Column(String, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChildDayAnalytics(Base):
    """Per-child per-day aggregate for participation and engagement metrics."""

    __tablename__ = "child_day_analytics"
    __table_args__ = (
        UniqueConstraint("child_id", "activity_day", name="uq_child_day_analytics_child_day"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_day = Column(Date, nullable=False, index=True)
    age_band = Column(String, nullable=False, default="unknown", index=True)

    words_encountered = Column(Integer, nullable=False, default=0)
    words_mastered = Column(Integer, nullable=False, default=0)
    mission_assigned_count = Column(Integer, nullable=False, default=0)
    mission_completed_count = Column(Integer, nullable=False, default=0)
    session_minutes_total = Column(Integer, nullable=False, default=0)
    engagement_score_sum = Column(Float, nullable=False, default=0.0)
    engagement_events_count = Column(Integer, nullable=False, default=0)
    engagement_score_avg = Column(Float, nullable=False, default=0.0)

    active_days_7d = Column(Integer, nullable=False, default=0)
    active_days_28d = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MissionOutcomeAnalytics(Base):
    """Mission assignment/completion outcomes segmented for analytics."""

    __tablename__ = "mission_outcome_analytics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    activity_day = Column(Date, nullable=False, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    mission_id = Column(String, ForeignKey("missions.id", ondelete="SET NULL"), index=True)
    assignment_id = Column(String, ForeignKey("mission_assignments.id", ondelete="SET NULL"), index=True)

    source = Column(String, nullable=False, default="system", index=True)
    context = Column(String, nullable=True, index=True)
    age_band = Column(String, nullable=False, default="unknown", index=True)
    status = Column(String, nullable=False, index=True)
    completion_minutes = Column(Integer)

    is_cluster = Column(Boolean, nullable=False, default=False, index=True)
    cluster_id = Column(String, index=True)
    seed_word_id = Column(String, index=True)

    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ContentPerformanceAnalytics(Base):
    """Content-level performance aggregate segmented by child/day/content."""

    __tablename__ = "content_performance_analytics"
    __table_args__ = (
        UniqueConstraint(
            "child_id",
            "activity_day",
            "content_type",
            "content_id",
            name="uq_content_performance_child_day_content",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    activity_day = Column(Date, nullable=False, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    age_band = Column(String, nullable=False, default="unknown", index=True)

    content_type = Column(String, nullable=False, index=True)
    content_id = Column(String, nullable=False, index=True)
    category_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="SET NULL"), index=True)

    exposure_count = Column(Integer, nullable=False, default=0)
    completion_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    post_exposure_mastery_delta = Column(Float, nullable=False, default=0.0)
    retention_proxy_score = Column(Float, nullable=False, default=0.0)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())