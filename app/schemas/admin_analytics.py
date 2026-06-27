"""Schemas for P4 admin analytics endpoints."""

from datetime import date
from pydantic import BaseModel


class ParticipationTrendPoint(BaseModel):
    day: date
    dau: int
    wau: int
    avg_active_days_7d: float
    return_rate_7d: float


class ParticipationSummary(BaseModel):
    start_day: date
    end_day: date
    window_days: int
    total_active_children: int
    average_dau: float
    average_wau: float
    average_return_rate_7d: float


class ParticipationTrendsResponse(BaseModel):
    summary: ParticipationSummary
    points: list[ParticipationTrendPoint]


class FunnelMetrics(BaseModel):
    assigned: int
    started: int
    completed: int
    skipped: int
    expired: int
    start_rate: float
    completion_rate: float
    completion_from_started_rate: float


class FunnelSegment(BaseModel):
    key: str
    label: str
    metrics: FunnelMetrics


class MissionFunnelResponse(BaseModel):
    start_day: date
    end_day: date
    age_band: str | None
    context: str | None
    source: str | None
    overall: FunnelMetrics
    by_context: list[FunnelSegment]
    by_source: list[FunnelSegment]
    by_age_band: list[FunnelSegment]


class EngagementTrendPoint(BaseModel):
    day: date
    avg_session_minutes: float
    avg_engagement_score: float
    active_children: int


class EngagementDistribution(BaseModel):
    low: int
    medium: int
    high: int


class EngagementSummary(BaseModel):
    start_day: date
    end_day: date
    window_days: int
    average_session_minutes: float
    average_engagement_score: float
    average_active_days_28d: float
    high_engagement_ratio: float


class EngagementRawInputs(BaseModel):
    session_events_count: int
    average_interactions_per_minute: float
    average_interactions_per_session: float
    average_activities_per_session: float
    average_words_encountered_per_session: float
    average_words_used_actively_per_session: float
    average_active_word_usage_ratio: float
    average_usage_minutes_per_day: float
    average_usage_minutes_per_week: float
    average_words_learned_per_day: float
    mission_completion_rate: float
    mission_median_completion_minutes: float
    average_game_minutes_per_day: float
    average_due_revision_cards_per_active_child: float
    overdue_revision_ratio: float
    average_photo_captures_per_day_proxy: float
    story_reads_per_week: float
    story_completion_rate: float
    shared_photo_posts_per_week: float
    average_reactions_per_shared_photo: float
    private_challenges_initiated_per_week: float
    public_challenge_participations_per_week: float


class EngagementTrendsResponse(BaseModel):
    summary: EngagementSummary
    raw_inputs: EngagementRawInputs
    distribution: EngagementDistribution
    points: list[EngagementTrendPoint]


class ContentPerformanceRow(BaseModel):
    content_type: str
    content_id: str
    category_id: str | None
    exposure_count: int
    completion_count: int
    success_count: int
    completion_rate: float
    success_rate: float
    avg_mastery_delta: float
    avg_retention_proxy_score: float
    effectiveness_score: float
    confidence_signal: str


class ContentPerformanceSummary(BaseModel):
    start_day: date
    end_day: date
    window_days: int
    evaluated_items: int
    average_effectiveness_score: float


class ContentPerformanceResponse(BaseModel):
    summary: ContentPerformanceSummary
    top_content: list[ContentPerformanceRow]
    underperforming_content: list[ContentPerformanceRow]
