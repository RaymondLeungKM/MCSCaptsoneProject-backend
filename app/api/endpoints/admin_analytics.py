"""Admin analytics diagnostics and P4 analytics endpoints."""

from datetime import date, datetime, timedelta, timezone
from datetime import time
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin_user
from app.db.session import get_db
from app.models.analytics_foundation import (
    AnalyticsEventLog,
    ChildDayAnalytics,
    ContentPerformanceAnalytics,
    MissionOutcomeAnalytics,
)
from app.models.analytics import GameSession, LearningSession
from app.models.word_personalization import SpacedRepetitionCard
from app.models.community import (
    ChallengeParticipation,
    CommunityPost,
    FriendChallenge,
)
from app.models.content import StoryProgress
from app.models.user import Child, User
from app.models.vocabulary import Word
from app.schemas.admin_analytics import (
    ContentPerformanceResponse,
    ContentPerformanceRow,
    ContentPerformanceSummary,
    EngagementDistribution,
    EngagementRawInputs,
    EngagementSummary,
    EngagementTrendPoint,
    EngagementTrendsResponse,
    FunnelMetrics,
    FunnelSegment,
    MissionFunnelResponse,
    ParticipationSummary,
    ParticipationTrendPoint,
    ParticipationTrendsResponse,
)
from app.schemas.analytics_foundation import (
    AnalyticsFoundationHealthResponse,
    CohortPrivacyDiagnostic,
    DailyEventCount,
    EventTypeCount,
    FoundationCoverage,
    FoundationRowCounts,
)
from app.services.analytics_foundation import resolve_age_band
from app.services.privacy_gate import evaluate_privacy_gate, suppression_payload


router = APIRouter()

DEFAULT_RANGE_DAYS = 28
MAX_RANGE_DAYS = 180
DEFAULT_TOP_N = 5


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        select(func.to_regclass(text(f"'{table_name}'")))
    )
    return result.scalar_one() is not None


def _resolve_date_range(
    from_day: date | None,
    to_day: date | None,
    *,
    default_days: int = DEFAULT_RANGE_DAYS,
) -> tuple[date, date]:
    end_day = to_day or datetime.now(timezone.utc).date()
    start_day = from_day or (end_day - timedelta(days=default_days - 1))

    if start_day > end_day:
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")

    range_days = (end_day - start_day).days + 1
    if range_days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Date range must be <= {MAX_RANGE_DAYS} days",
        )

    return start_day, end_day


def _active_child_day_filter():
    return (
        (ChildDayAnalytics.words_encountered > 0)
        | (ChildDayAnalytics.words_mastered > 0)
        | (ChildDayAnalytics.mission_assigned_count > 0)
        | (ChildDayAnalytics.session_minutes_total > 0)
    )


def _build_funnel_metrics(counts: dict[str, int]) -> FunnelMetrics:
    assigned = counts.get("assigned", 0)
    started = counts.get("started", 0)
    completed = counts.get("completed", 0)
    skipped = counts.get("skipped", 0)
    expired = counts.get("expired", 0)

    start_rate = round(started / assigned, 4) if assigned > 0 else 0.0
    completion_rate = round(completed / assigned, 4) if assigned > 0 else 0.0
    completion_from_started_rate = (
        round(completed / started, 4) if started > 0 else 0.0
    )

    return FunnelMetrics(
        assigned=assigned,
        started=started,
        completed=completed,
        skipped=skipped,
        expired=expired,
        start_rate=start_rate,
        completion_rate=completion_rate,
        completion_from_started_rate=completion_from_started_rate,
    )


def _confidence_signal(exposure_count: int) -> str:
    if exposure_count >= 30:
        return "high"
    if exposure_count >= 10:
        return "medium"
    return "low"


def _effectiveness_score(
    completion_rate: float,
    success_rate: float,
    retention_score: float,
) -> float:
    bounded_retention = min(max(retention_score, 0.0), 1.0)
    return round(
        0.45 * completion_rate + 0.35 * success_rate + 0.20 * bounded_retention,
        4,
    )


@router.get(
    "/foundation/health",
    response_model=AnalyticsFoundationHealthResponse,
    summary="Get analytics foundation health diagnostics",
)
async def get_analytics_foundation_health(
    days: int = Query(default=28, ge=1, le=180),
    minimum_cohort_threshold: int = Query(default=25, ge=1, le=500),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    end_day = datetime.now(timezone.utc).date()
    start_day = end_day - timedelta(days=days - 1)
    start_at = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    event_count_result = await db.execute(
        select(func.count(AnalyticsEventLog.id)).where(
            AnalyticsEventLog.occurred_at >= start_at
        )
    )
    child_day_count_result = await db.execute(
        select(func.count(ChildDayAnalytics.id)).where(
            ChildDayAnalytics.activity_day >= start_day
        )
    )
    mission_outcome_count_result = await db.execute(
        select(func.count(MissionOutcomeAnalytics.id)).where(
            MissionOutcomeAnalytics.activity_day >= start_day
        )
    )
    content_perf_count_result = await db.execute(
        select(func.count(ContentPerformanceAnalytics.id)).where(
            ContentPerformanceAnalytics.activity_day >= start_day
        )
    )

    row_counts = FoundationRowCounts(
        analytics_event_log=event_count_result.scalar_one() or 0,
        child_day_analytics=child_day_count_result.scalar_one() or 0,
        mission_outcome_analytics=mission_outcome_count_result.scalar_one() or 0,
        content_performance_analytics=content_perf_count_result.scalar_one() or 0,
    )

    total_children_result = await db.execute(select(func.count(Child.id)))
    total_children = total_children_result.scalar_one() or 0

    coverage_result = await db.execute(
        select(func.count(func.distinct(ChildDayAnalytics.child_id))).where(
            ChildDayAnalytics.activity_day >= start_day
        )
    )
    children_with_aggregate_rows = coverage_result.scalar_one() or 0
    coverage_ratio = (
        round(children_with_aggregate_rows / total_children, 4)
        if total_children > 0
        else 0.0
    )

    coverage = FoundationCoverage(
        total_children=total_children,
        children_with_aggregate_rows=children_with_aggregate_rows,
        coverage_ratio=coverage_ratio,
    )

    event_type_counts_result = await db.execute(
        select(
            AnalyticsEventLog.event_type,
            func.count(AnalyticsEventLog.id).label("count"),
        )
        .where(AnalyticsEventLog.occurred_at >= start_at)
        .group_by(AnalyticsEventLog.event_type)
        .order_by(func.count(AnalyticsEventLog.id).desc(), AnalyticsEventLog.event_type.asc())
    )
    event_type_counts = [
        EventTypeCount(event_type=row.event_type, count=row.count)
        for row in event_type_counts_result
    ]

    daily_event_counts_result = await db.execute(
        select(AnalyticsEventLog.occurred_at)
        .where(AnalyticsEventLog.occurred_at >= start_at)
        .order_by(AnalyticsEventLog.occurred_at.asc())
    )

    per_day_counts: dict[date, int] = {
        start_day + timedelta(days=offset): 0 for offset in range(days)
    }
    for occurred_at in daily_event_counts_result.scalars().all():
        if occurred_at is None:
            continue
        if occurred_at.tzinfo is None:
            occurred_day = occurred_at.replace(tzinfo=timezone.utc).date()
        else:
            occurred_day = occurred_at.astimezone(timezone.utc).date()
        if occurred_day in per_day_counts:
            per_day_counts[occurred_day] += 1

    daily_event_counts = [
        DailyEventCount(day=tracked_day, count=count)
        for tracked_day, count in sorted(per_day_counts.items(), key=lambda x: x[0])
    ]

    ages_result = await db.execute(select(Child.age))
    age_counts: dict[str, int] = {}
    for child_age in ages_result.scalars().all():
        band = resolve_age_band(child_age)
        age_counts[band] = age_counts.get(band, 0) + 1

    ordered_bands = ["3-4", "5-6", "7+", "unknown"]
    cohort_diagnostics: list[CohortPrivacyDiagnostic] = []
    for band in ordered_bands:
        size = age_counts.get(band, 0)
        gate = evaluate_privacy_gate(
            user=current_user,
            cohort_size=size,
            minimum_cohort_threshold=minimum_cohort_threshold,
        )
        suppression = suppression_payload(gate)
        cohort_diagnostics.append(
            CohortPrivacyDiagnostic(
                age_band=band,
                cohort_size=size,
                allowed=gate.allowed,
                suppression=suppression,
            )
        )

    return AnalyticsFoundationHealthResponse(
        window_days=days,
        start_day=start_day,
        end_day=end_day,
        row_counts=row_counts,
        coverage=coverage,
        daily_event_counts=daily_event_counts,
        event_type_counts=event_type_counts,
        cohort_diagnostics=cohort_diagnostics,
    )


@router.get(
    "/participation",
    response_model=ParticipationTrendsResponse,
    summary="Get participation trends (DAU/WAU/return rate)",
)
async def get_participation_trends(
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    age_band: str | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    start_day, end_day = _resolve_date_range(from_day, to_day)
    lookback_start = start_day - timedelta(days=6)

    filters = [
        ChildDayAnalytics.activity_day >= lookback_start,
        ChildDayAnalytics.activity_day <= end_day,
        _active_child_day_filter(),
    ]
    if age_band:
        filters.append(ChildDayAnalytics.age_band == age_band)

    rows_result = await db.execute(
        select(
            ChildDayAnalytics.activity_day,
            ChildDayAnalytics.child_id,
            ChildDayAnalytics.active_days_7d,
        ).where(*filters)
    )

    active_children_by_day: dict[date, set[str]] = {}
    avg_active_days_7d_by_day: dict[date, list[int]] = {}
    for activity_day, child_id, active_days_7d in rows_result.all():
        active_children_by_day.setdefault(activity_day, set()).add(child_id)
        avg_active_days_7d_by_day.setdefault(activity_day, []).append(active_days_7d or 0)

    points: list[ParticipationTrendPoint] = []
    tracked_days = (end_day - start_day).days + 1
    for offset in range(tracked_days):
        day = start_day + timedelta(days=offset)
        dau_set = active_children_by_day.get(day, set())

        rolling_sets = [
            active_children_by_day.get(day - timedelta(days=i), set())
            for i in range(7)
        ]
        wau_set = set().union(*rolling_sets) if rolling_sets else set()

        prior_sets = [
            active_children_by_day.get(day - timedelta(days=i), set())
            for i in range(1, 8)
        ]
        prior_active = set().union(*prior_sets) if prior_sets else set()
        returning_children = dau_set.intersection(prior_active)
        return_rate = round(len(returning_children) / len(dau_set), 4) if dau_set else 0.0

        active_days_list = avg_active_days_7d_by_day.get(day, [])
        avg_active_days_7d = (
            round(sum(active_days_list) / len(active_days_list), 2)
            if active_days_list
            else 0.0
        )

        points.append(
            ParticipationTrendPoint(
                day=day,
                dau=len(dau_set),
                wau=len(wau_set),
                avg_active_days_7d=avg_active_days_7d,
                return_rate_7d=return_rate,
            )
        )

    in_window_children = set()
    for point in points:
        in_window_children.update(active_children_by_day.get(point.day, set()))

    summary = ParticipationSummary(
        start_day=start_day,
        end_day=end_day,
        window_days=tracked_days,
        total_active_children=len(in_window_children),
        average_dau=round(sum(point.dau for point in points) / max(len(points), 1), 2),
        average_wau=round(sum(point.wau for point in points) / max(len(points), 1), 2),
        average_return_rate_7d=round(
            sum(point.return_rate_7d for point in points) / max(len(points), 1),
            4,
        ),
    )

    return ParticipationTrendsResponse(summary=summary, points=points)


@router.get(
    "/missions/funnel",
    response_model=MissionFunnelResponse,
    summary="Get mission funnel metrics segmented by context/source/age-band",
)
async def get_mission_funnel(
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    age_band: str | None = Query(default=None),
    context: str | None = Query(default=None),
    source: str | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    start_day, end_day = _resolve_date_range(from_day, to_day)

    filters = [
        MissionOutcomeAnalytics.activity_day >= start_day,
        MissionOutcomeAnalytics.activity_day <= end_day,
    ]
    if age_band:
        filters.append(MissionOutcomeAnalytics.age_band == age_band)
    if context:
        filters.append(MissionOutcomeAnalytics.context == context)
    if source:
        filters.append(MissionOutcomeAnalytics.source == source)

    grouped_result = await db.execute(
        select(
            MissionOutcomeAnalytics.status,
            MissionOutcomeAnalytics.context,
            MissionOutcomeAnalytics.source,
            MissionOutcomeAnalytics.age_band,
            func.count(MissionOutcomeAnalytics.id).label("count"),
        )
        .where(*filters)
        .group_by(
            MissionOutcomeAnalytics.status,
            MissionOutcomeAnalytics.context,
            MissionOutcomeAnalytics.source,
            MissionOutcomeAnalytics.age_band,
        )
    )

    valid_statuses = {"assigned", "started", "completed", "skipped", "expired"}

    overall_counts = {status: 0 for status in valid_statuses}
    by_context_counts: dict[str, dict[str, int]] = {}
    by_source_counts: dict[str, dict[str, int]] = {}
    by_age_band_counts: dict[str, dict[str, int]] = {}

    for status, row_context, row_source, row_age_band, count in grouped_result.all():
        if status not in valid_statuses:
            continue

        overall_counts[status] += count

        context_key = row_context or "unknown"
        source_key = row_source or "unknown"
        age_key = row_age_band or "unknown"

        by_context_counts.setdefault(
            context_key,
            {key: 0 for key in valid_statuses},
        )[status] += count
        by_source_counts.setdefault(
            source_key,
            {key: 0 for key in valid_statuses},
        )[status] += count
        by_age_band_counts.setdefault(
            age_key,
            {key: 0 for key in valid_statuses},
        )[status] += count

    by_context = [
        FunnelSegment(key=key, label=key, metrics=_build_funnel_metrics(counts))
        for key, counts in sorted(by_context_counts.items(), key=lambda item: item[0])
    ]
    by_source = [
        FunnelSegment(key=key, label=key, metrics=_build_funnel_metrics(counts))
        for key, counts in sorted(by_source_counts.items(), key=lambda item: item[0])
    ]
    by_age_band = [
        FunnelSegment(key=key, label=key, metrics=_build_funnel_metrics(counts))
        for key, counts in sorted(by_age_band_counts.items(), key=lambda item: item[0])
    ]

    return MissionFunnelResponse(
        start_day=start_day,
        end_day=end_day,
        age_band=age_band,
        context=context,
        source=source,
        overall=_build_funnel_metrics(overall_counts),
        by_context=by_context,
        by_source=by_source,
        by_age_band=by_age_band,
    )


@router.get(
    "/engagement",
    response_model=EngagementTrendsResponse,
    summary="Get engagement trends and summary cards",
)
async def get_engagement_trends(
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    age_band: str | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    start_day, end_day = _resolve_date_range(from_day, to_day)

    filters = [
        ChildDayAnalytics.activity_day >= start_day,
        ChildDayAnalytics.activity_day <= end_day,
        _active_child_day_filter(),
    ]
    if age_band:
        filters.append(ChildDayAnalytics.age_band == age_band)

    per_day_result = await db.execute(
        select(
            ChildDayAnalytics.activity_day,
            func.avg(ChildDayAnalytics.session_minutes_total).label(
                "avg_session_minutes"
            ),
            func.avg(ChildDayAnalytics.engagement_score_avg).label(
                "avg_engagement_score"
            ),
            func.count(func.distinct(ChildDayAnalytics.child_id)).label("active_children"),
        )
        .where(*filters)
        .group_by(ChildDayAnalytics.activity_day)
        .order_by(ChildDayAnalytics.activity_day.asc())
    )

    points = [
        EngagementTrendPoint(
            day=row.activity_day,
            avg_session_minutes=round(float(row.avg_session_minutes or 0.0), 2),
            avg_engagement_score=round(float(row.avg_engagement_score or 0.0), 4),
            active_children=row.active_children or 0,
        )
        for row in per_day_result
    ]

    eligible_child_ids_result = await db.execute(
        select(func.distinct(ChildDayAnalytics.child_id)).where(*filters)
    )
    eligible_child_ids = [
        child_id
        for child_id in eligible_child_ids_result.scalars().all()
        if child_id
    ]

    eligible_parent_ids: list[str] = []
    if age_band and eligible_child_ids:
        eligible_parent_ids_result = await db.execute(
            select(func.distinct(Child.parent_id)).where(Child.id.in_(eligible_child_ids))
        )
        eligible_parent_ids = [
            parent_id
            for parent_id in eligible_parent_ids_result.scalars().all()
            if parent_id
        ]

    range_start = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=timezone.utc)

    session_filters = [
        LearningSession.end_time.is_not(None),
        LearningSession.end_time >= range_start,
        LearningSession.end_time < range_end,
    ]
    if age_band:
        if eligible_child_ids:
            session_filters.append(LearningSession.child_id.in_(eligible_child_ids))
        else:
            session_filters.append(LearningSession.child_id == "__none__")

    raw_inputs_result = await db.execute(
        select(
            LearningSession.start_time,
            LearningSession.end_time,
            LearningSession.duration_minutes,
            LearningSession.interactions_count,
            LearningSession.activities_completed,
            LearningSession.words_encountered,
            LearningSession.words_used_actively,
        ).where(*session_filters)
    )

    session_events_count = 0
    interactions_per_minute_sum = 0.0
    interactions_per_session_sum = 0.0
    activities_per_session_sum = 0.0
    words_encountered_per_session_sum = 0.0
    words_used_actively_per_session_sum = 0.0
    active_word_usage_ratio_sum = 0.0
    for (
        start_time,
        end_time,
        duration_minutes,
        interactions_count,
        activities_completed,
        words_encountered,
        words_used_actively,
    ) in raw_inputs_result.all():
        safe_duration = int(duration_minutes or 0)
        if safe_duration <= 0 and start_time and end_time:
            start_utc = (
                start_time.replace(tzinfo=timezone.utc)
                if start_time.tzinfo is None
                else start_time.astimezone(timezone.utc)
            )
            end_utc = (
                end_time.replace(tzinfo=timezone.utc)
                if end_time.tzinfo is None
                else end_time.astimezone(timezone.utc)
            )
            safe_duration = max(1, int(max((end_utc - start_utc).total_seconds(), 0) // 60))

        safe_interactions = max(int(interactions_count or 0), 0)
        safe_activities = len(activities_completed or [])
        safe_words_encountered = len(words_encountered or [])
        safe_words_used = len(words_used_actively or [])

        session_events_count += 1
        interactions_per_session_sum += safe_interactions
        interactions_per_minute_sum += safe_interactions / max(safe_duration, 1)
        activities_per_session_sum += safe_activities
        words_encountered_per_session_sum += safe_words_encountered
        words_used_actively_per_session_sum += safe_words_used
        active_word_usage_ratio_sum += safe_words_used / max(
            safe_words_encountered,
            1,
        )

    distribution_result = await db.execute(
        select(ChildDayAnalytics.engagement_score_avg).where(*filters)
    )
    low = 0
    medium = 0
    high = 0
    for score in distribution_result.scalars().all():
        normalized = float(score or 0.0)
        if normalized < 0.4:
            low += 1
        elif normalized < 0.7:
            medium += 1
        else:
            high += 1

    avg_active_days_28_result = await db.execute(
        select(func.avg(ChildDayAnalytics.active_days_28d)).where(*filters)
    )
    avg_active_days_28d = round(
        float(avg_active_days_28_result.scalar_one() or 0.0),
        2,
    )

    total_distribution = low + medium + high
    window_days = (end_day - start_day).days + 1

    day_totals_result = await db.execute(
        select(
            func.sum(ChildDayAnalytics.session_minutes_total).label("session_minutes_total"),
            func.sum(ChildDayAnalytics.words_mastered).label("words_mastered_total"),
        ).where(*filters)
    )
    day_totals = day_totals_result.one()
    total_session_minutes = float(day_totals.session_minutes_total or 0.0)
    total_words_mastered = float(day_totals.words_mastered_total or 0.0)

    mission_filters = [
        MissionOutcomeAnalytics.activity_day >= start_day,
        MissionOutcomeAnalytics.activity_day <= end_day,
    ]
    if age_band:
        mission_filters.append(MissionOutcomeAnalytics.age_band == age_band)

    mission_counts_result = await db.execute(
        select(
            MissionOutcomeAnalytics.status,
            func.count(MissionOutcomeAnalytics.id).label("count"),
        )
        .where(*mission_filters)
        .group_by(MissionOutcomeAnalytics.status)
    )
    mission_status_counts = {
        str(row.status): int(row.count or 0)
        for row in mission_counts_result.all()
        if row.status
    }
    assigned_count = mission_status_counts.get("assigned", 0)
    completed_count = mission_status_counts.get("completed", 0)
    mission_completion_rate = (
        round(completed_count / assigned_count, 4)
        if assigned_count > 0
        else 0.0
    )

    mission_completion_minutes_result = await db.execute(
        select(MissionOutcomeAnalytics.completion_minutes)
        .where(
            *mission_filters,
            MissionOutcomeAnalytics.status == "completed",
            MissionOutcomeAnalytics.completion_minutes.is_not(None),
        )
    )
    completion_minutes_values = [
        int(minutes)
        for minutes in mission_completion_minutes_result.scalars().all()
        if minutes is not None
    ]
    mission_median_completion_minutes = round(
        float(median(completion_minutes_values)) if completion_minutes_values else 0.0,
        2,
    )

    game_filters = [
        GameSession.created_at >= range_start,
        GameSession.created_at < range_end,
    ]
    if age_band:
        if eligible_child_ids:
            game_filters.append(GameSession.child_id.in_(eligible_child_ids))
        else:
            game_filters.append(GameSession.child_id == "__none__")

    game_duration_result = await db.execute(
        select(func.sum(GameSession.duration_seconds)).where(*game_filters)
    )
    total_game_seconds = float(game_duration_result.scalar_one() or 0.0)

    revision_total_filters = [SpacedRepetitionCard.is_new.is_(False)]
    revision_due_filters = [
        SpacedRepetitionCard.is_new.is_(False),
        SpacedRepetitionCard.next_review <= datetime.now(timezone.utc),
    ]
    if age_band:
        if eligible_child_ids:
            revision_total_filters.append(SpacedRepetitionCard.child_id.in_(eligible_child_ids))
            revision_due_filters.append(SpacedRepetitionCard.child_id.in_(eligible_child_ids))
        else:
            revision_total_filters.append(SpacedRepetitionCard.child_id == "__none__")
            revision_due_filters.append(SpacedRepetitionCard.child_id == "__none__")

    reviewable_cards_result = await db.execute(
        select(func.count(SpacedRepetitionCard.id)).where(*revision_total_filters)
    )
    due_cards_result = await db.execute(
        select(func.count(SpacedRepetitionCard.id)).where(*revision_due_filters)
    )
    reviewable_cards_count = int(reviewable_cards_result.scalar_one() or 0)
    due_revision_cards = int(due_cards_result.scalar_one() or 0)
    active_child_count = len(eligible_child_ids)
    overdue_revision_ratio = (
        round(due_revision_cards / reviewable_cards_count, 4)
        if reviewable_cards_count > 0
        else 0.0
    )
    average_due_revision_cards_per_active_child = (
        round(due_revision_cards / active_child_count, 2)
        if active_child_count > 0
        else 0.0
    )

    photo_filters = [
        Word.created_by_child_id.is_not(None),
        Word.created_at >= range_start,
        Word.created_at < range_end,
    ]
    if age_band:
        if eligible_child_ids:
            photo_filters.append(Word.created_by_child_id.in_(eligible_child_ids))
        else:
            photo_filters.append(Word.created_by_child_id == "__none__")

    photo_count_result = await db.execute(
        select(func.count(Word.id)).where(*photo_filters)
    )
    photo_capture_count = int(photo_count_result.scalar_one() or 0)

    story_read_count = 0
    story_completed_count = 0
    story_completion_rate = 0.0
    if await _table_exists(db, "story_progress"):
        story_filters = [
            StoryProgress.last_read.is_not(None),
            StoryProgress.last_read >= range_start,
            StoryProgress.last_read < range_end,
        ]
        if age_band:
            if eligible_child_ids:
                story_filters.append(StoryProgress.child_id.in_(eligible_child_ids))
            else:
                story_filters.append(StoryProgress.child_id == "__none__")

        story_reads_result = await db.execute(
            select(
                func.count(StoryProgress.id).label("read_count"),
                func.sum(
                    case((StoryProgress.completed.is_(True), 1), else_=0)
                ).label("completed_count"),
            ).where(*story_filters)
        )
        story_reads_row = story_reads_result.one()
        story_read_count = int(story_reads_row.read_count or 0)
        story_completed_count = int(story_reads_row.completed_count or 0)
        story_completion_rate = (
            round(story_completed_count / story_read_count, 4)
            if story_read_count > 0
            else 0.0
        )

    shared_photo_post_count = 0
    average_reactions_per_shared_photo = 0.0
    if await _table_exists(db, "community_posts"):
        social_filters = [
            CommunityPost.created_at >= range_start,
            CommunityPost.created_at < range_end,
        ]
        if age_band:
            if eligible_child_ids:
                social_filters.append(CommunityPost.child_id.in_(eligible_child_ids))
            else:
                social_filters.append(CommunityPost.child_id == "__none__")

        social_result = await db.execute(
            select(
                func.count(CommunityPost.id).label("post_count"),
                func.avg(CommunityPost.reaction_count).label("avg_reactions"),
            ).where(*social_filters)
        )
        social_row = social_result.one()
        shared_photo_post_count = int(social_row.post_count or 0)
        average_reactions_per_shared_photo = float(social_row.avg_reactions or 0.0)

    public_challenge_participation_count = 0
    if await _table_exists(db, "challenge_participations"):
        public_challenge_filters = [
            ChallengeParticipation.created_at >= range_start,
            ChallengeParticipation.created_at < range_end,
        ]
        if age_band:
            if eligible_child_ids:
                public_challenge_filters.append(
                    ChallengeParticipation.child_id.in_(eligible_child_ids)
                )
            else:
                public_challenge_filters.append(ChallengeParticipation.child_id == "__none__")

        public_challenge_result = await db.execute(
            select(func.count(ChallengeParticipation.id)).where(*public_challenge_filters)
        )
        public_challenge_participation_count = int(
            public_challenge_result.scalar_one() or 0
        )

    private_challenge_created_count = 0
    if await _table_exists(db, "friend_challenges"):
        private_challenge_filters = [
            FriendChallenge.created_at >= range_start,
            FriendChallenge.created_at < range_end,
        ]
        if age_band:
            if eligible_parent_ids:
                private_challenge_filters.append(
                    FriendChallenge.creator_id.in_(eligible_parent_ids)
                )
            else:
                private_challenge_filters.append(FriendChallenge.creator_id == "__none__")

        private_challenge_result = await db.execute(
            select(func.count(FriendChallenge.id)).where(*private_challenge_filters)
        )
        private_challenge_created_count = int(
            private_challenge_result.scalar_one() or 0
        )

    summary = EngagementSummary(
        start_day=start_day,
        end_day=end_day,
        window_days=window_days,
        average_session_minutes=round(
            sum(point.avg_session_minutes for point in points) / max(len(points), 1),
            2,
        ),
        average_engagement_score=round(
            sum(point.avg_engagement_score for point in points) / max(len(points), 1),
            4,
        ),
        average_active_days_28d=avg_active_days_28d,
        high_engagement_ratio=(
            round(high / total_distribution, 4) if total_distribution > 0 else 0.0
        ),
    )

    raw_inputs = EngagementRawInputs(
        session_events_count=session_events_count,
        average_interactions_per_minute=round(
            interactions_per_minute_sum / max(session_events_count, 1),
            2,
        ),
        average_interactions_per_session=round(
            interactions_per_session_sum / max(session_events_count, 1),
            2,
        ),
        average_activities_per_session=round(
            activities_per_session_sum / max(session_events_count, 1),
            2,
        ),
        average_words_encountered_per_session=round(
            words_encountered_per_session_sum / max(session_events_count, 1),
            2,
        ),
        average_words_used_actively_per_session=round(
            words_used_actively_per_session_sum / max(session_events_count, 1),
            2,
        ),
        average_active_word_usage_ratio=round(
            active_word_usage_ratio_sum / max(session_events_count, 1),
            4,
        ),
        average_usage_minutes_per_day=round(
            total_session_minutes / max(window_days, 1),
            2,
        ),
        average_usage_minutes_per_week=round(
            (total_session_minutes / max(window_days, 1)) * 7,
            2,
        ),
        average_words_learned_per_day=round(
            total_words_mastered / max(window_days, 1),
            2,
        ),
        mission_completion_rate=mission_completion_rate,
        mission_median_completion_minutes=mission_median_completion_minutes,
        average_game_minutes_per_day=round(
            (total_game_seconds / 60) / max(window_days, 1),
            2,
        ),
        average_due_revision_cards_per_active_child=average_due_revision_cards_per_active_child,
        overdue_revision_ratio=overdue_revision_ratio,
        average_photo_captures_per_day_proxy=round(
            photo_capture_count / max(window_days, 1),
            2,
        ),
        story_reads_per_week=round(
            (story_read_count / max(window_days, 1)) * 7,
            2,
        ),
        story_completion_rate=story_completion_rate,
        shared_photo_posts_per_week=round(
            (shared_photo_post_count / max(window_days, 1)) * 7,
            2,
        ),
        average_reactions_per_shared_photo=round(
            average_reactions_per_shared_photo,
            2,
        ),
        private_challenges_initiated_per_week=round(
            (private_challenge_created_count / max(window_days, 1)) * 7,
            2,
        ),
        public_challenge_participations_per_week=round(
            (public_challenge_participation_count / max(window_days, 1)) * 7,
            2,
        ),
    )

    return EngagementTrendsResponse(
        summary=summary,
        raw_inputs=raw_inputs,
        distribution=EngagementDistribution(low=low, medium=medium, high=high),
        points=points,
    )


@router.get(
    "/content-performance",
    response_model=ContentPerformanceResponse,
    summary="Get content performance insights",
)
async def get_content_performance(
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    age_band: str | None = Query(default=None),
    category: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    top_n: int = Query(default=DEFAULT_TOP_N, ge=1, le=20),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    start_day, end_day = _resolve_date_range(from_day, to_day)

    filters = [
        ContentPerformanceAnalytics.activity_day >= start_day,
        ContentPerformanceAnalytics.activity_day <= end_day,
    ]
    if age_band:
        filters.append(ContentPerformanceAnalytics.age_band == age_band)
    if category:
        filters.append(ContentPerformanceAnalytics.category_id == category)
    if content_type:
        filters.append(ContentPerformanceAnalytics.content_type == content_type)

    grouped_result = await db.execute(
        select(
            ContentPerformanceAnalytics.content_type,
            ContentPerformanceAnalytics.content_id,
            ContentPerformanceAnalytics.category_id,
            func.sum(ContentPerformanceAnalytics.exposure_count).label("exposure_count"),
            func.sum(ContentPerformanceAnalytics.completion_count).label("completion_count"),
            func.sum(ContentPerformanceAnalytics.success_count).label("success_count"),
            func.avg(ContentPerformanceAnalytics.post_exposure_mastery_delta).label(
                "avg_mastery_delta"
            ),
            func.avg(ContentPerformanceAnalytics.retention_proxy_score).label(
                "avg_retention_proxy_score"
            ),
        )
        .where(*filters)
        .group_by(
            ContentPerformanceAnalytics.content_type,
            ContentPerformanceAnalytics.content_id,
            ContentPerformanceAnalytics.category_id,
        )
    )

    rows: list[ContentPerformanceRow] = []
    for row in grouped_result.all():
        exposure_count = int(row.exposure_count or 0)
        completion_count = int(row.completion_count or 0)
        success_count = int(row.success_count or 0)

        completion_rate = (
            round(completion_count / exposure_count, 4)
            if exposure_count > 0
            else 0.0
        )
        success_rate = (
            round(success_count / completion_count, 4)
            if completion_count > 0
            else 0.0
        )
        avg_mastery_delta = round(float(row.avg_mastery_delta or 0.0), 4)
        avg_retention_proxy_score = round(
            float(row.avg_retention_proxy_score or 0.0),
            4,
        )
        effectiveness_score = _effectiveness_score(
            completion_rate,
            success_rate,
            avg_retention_proxy_score,
        )

        rows.append(
            ContentPerformanceRow(
                content_type=row.content_type,
                content_id=row.content_id,
                category_id=row.category_id,
                exposure_count=exposure_count,
                completion_count=completion_count,
                success_count=success_count,
                completion_rate=completion_rate,
                success_rate=success_rate,
                avg_mastery_delta=avg_mastery_delta,
                avg_retention_proxy_score=avg_retention_proxy_score,
                effectiveness_score=effectiveness_score,
                confidence_signal=_confidence_signal(exposure_count),
            )
        )

    sorted_rows = sorted(
        rows,
        key=lambda item: (item.effectiveness_score, item.exposure_count),
    )
    top_content = list(reversed(sorted_rows[-top_n:]))
    underperforming_content = sorted_rows[:top_n]

    average_effectiveness_score = round(
        sum(item.effectiveness_score for item in rows) / max(len(rows), 1),
        4,
    )

    summary = ContentPerformanceSummary(
        start_day=start_day,
        end_day=end_day,
        window_days=(end_day - start_day).days + 1,
        evaluated_items=len(rows),
        average_effectiveness_score=average_effectiveness_score,
    )

    return ContentPerformanceResponse(
        summary=summary,
        top_content=top_content,
        underperforming_content=underperforming_content,
    )