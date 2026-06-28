"""
Schemas for P0 analytics foundation diagnostics.
"""
from datetime import date
from pydantic import BaseModel


class FoundationRowCounts(BaseModel):
    analytics_event_log: int
    child_day_analytics: int
    mission_outcome_analytics: int
    content_performance_analytics: int


class FoundationCoverage(BaseModel):
    total_children: int
    children_with_aggregate_rows: int
    coverage_ratio: float


class EventTypeCount(BaseModel):
    event_type: str
    count: int


class DailyEventCount(BaseModel):
    day: date
    count: int


class SuppressionInfo(BaseModel):
    is_suppressed: bool
    reason: str | None
    minimum_cohort_threshold: int


class CohortPrivacyDiagnostic(BaseModel):
    age_band: str
    cohort_size: int
    allowed: bool
    suppression: SuppressionInfo


class AnalyticsFoundationHealthResponse(BaseModel):
    window_days: int
    start_day: date
    end_day: date
    row_counts: FoundationRowCounts
    coverage: FoundationCoverage
    daily_event_counts: list[DailyEventCount]
    event_type_counts: list[EventTypeCount]
    cohort_diagnostics: list[CohortPrivacyDiagnostic]