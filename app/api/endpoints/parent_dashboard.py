"""
Parent Analytics API Endpoints
Dashboard, insights, reports, and parental controls
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, or_
from typing import List, Optional
from datetime import datetime, date, timedelta
import uuid

from app.db.session import get_db
from app.models.user import User, Child
from app.models.parent_analytics import (
    DailyLearningStats,
    LearningInsight,
    WeeklyReport,
    ParentalControl
)
from app.models.vocabulary import WordProgress
from app.models.analytics import LearningSession
from app.schemas.parent_analytics import (
    DailyLearningStatsResponse,
    LearningInsightResponse,
    LearningInsightCreateRequest,
    LearningInsightUpdateRequest,
    WeeklyReportResponse,
    ParentalControlResponse,
    ParentalControlUpdateRequest,
    DashboardSummaryResponse,
    CategoryProgress,
    AnalyticsChartsResponse,
    LearningTimeSeriesData
)
from app.core.security import get_current_user

router = APIRouter(prefix="/parent-dashboard", tags=["parent-dashboard"])


# =============================================================================
# DASHBOARD SUMMARY
# =============================================================================

@router.get("/{child_id}/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    child_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive dashboard summary for a child
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Get category progress
    # TODO: Implement category progress calculation
    category_progress = []
    
    # Get recent insights (last 5, unread first)
    insights_result = await db.execute(
        select(LearningInsight)
        .where(
            and_(
                LearningInsight.child_id == child_id,
                LearningInsight.is_dismissed == False
            )
        )
        .order_by(
            LearningInsight.is_read.asc(),
            desc(LearningInsight.generated_at)
        )
        .limit(5)
    )
    insights = insights_result.scalars().all()
    
    # Get latest weekly report
    report_result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.child_id == child_id)
        .order_by(desc(WeeklyReport.week_start_date))
        .limit(1)
    )
    latest_report = report_result.scalar_one_or_none()
    
    # Get parental control settings
    control_result = await db.execute(
        select(ParentalControl).where(ParentalControl.child_id == child_id)
    )
    parental_control = control_result.scalar_one_or_none()
    
    # Calculate weekly stats (last 7 days)
    seven_days_ago = date.today() - timedelta(days=7)
    weekly_stats_result = await db.execute(
        select(
            func.sum(DailyLearningStats.words_learned),
            func.sum(DailyLearningStats.total_learning_time),
            func.sum(DailyLearningStats.session_count),
            func.sum(DailyLearningStats.xp_earned)
        )
        .where(
            and_(
                DailyLearningStats.child_id == child_id,
                DailyLearningStats.date >= seven_days_ago
            )
        )
    )
    weekly_data = weekly_stats_result.first()
    
    return DashboardSummaryResponse(
        child_id=child.id,
        child_name=child.name,
        total_words_learned=child.words_learned,
        current_streak=child.current_streak,
        level=child.level,
        xp=child.xp,
        weekly_learning_time=weekly_data[1] or 0,
        weekly_sessions=weekly_data[2] or 0,
        weekly_words_learned=weekly_data[0] or 0,
        weekly_xp_earned=weekly_data[3] or 0,
        category_progress=category_progress,
        recent_insights=[LearningInsightResponse.from_orm(i) for i in insights],
        latest_report=WeeklyReportResponse.from_orm(latest_report) if latest_report else None,
        parental_control=ParentalControlResponse.from_orm(parental_control) if parental_control else None
    )


@router.get("/{child_id}/charts", response_model=AnalyticsChartsResponse)
async def get_analytics_charts(
    child_id: str,
    period: str = Query("week", regex="^(week|month|all)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get data for analytics charts
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Calculate date range
    today = date.today()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    else:  # all
        start_date = date(2020, 1, 1)  # Far in the past
    
    # Get daily stats for time series
    stats_result = await db.execute(
        select(DailyLearningStats)
        .where(
            and_(
                DailyLearningStats.child_id == child_id,
                DailyLearningStats.date >= start_date
            )
        )
        .order_by(DailyLearningStats.date)
    )
    daily_stats = stats_result.scalars().all()
    
    # Build time series data
    dates = [str(stat.date) for stat in daily_stats]
    words_learned = [stat.words_learned for stat in daily_stats]
    learning_time = [stat.total_learning_time for stat in daily_stats]
    xp_earned = [stat.xp_earned for stat in daily_stats]
    accuracy = [stat.average_accuracy for stat in daily_stats]
    
    # Aggregate category breakdown
    category_breakdown = {}
    for stat in daily_stats:
        for category_id, count in stat.categories_studied.items():
            category_breakdown[category_id] = category_breakdown.get(category_id, 0) + count
    
    # Learning style distribution (placeholder)
    learning_style_distribution = {
        "games": sum(s.games_played for s in daily_stats),
        "stories": sum(s.stories_read for s in daily_stats),
        "practice": sum(s.session_count for s in daily_stats)
    }
    
    # Calculate best time of day (placeholder)
    best_time_of_day = child.preferred_time_of_day.value
    
    # Calculate average session length
    total_time = sum(learning_time)
    total_sessions = sum(s.session_count for s in daily_stats)
    avg_session_length = int(total_time / total_sessions) if total_sessions > 0 else 0
    
    return AnalyticsChartsResponse(
        child_id=child_id,
        period=period,
        time_series=LearningTimeSeriesData(
            dates=dates,
            words_learned=words_learned,
            learning_time=learning_time,
            xp_earned=xp_earned,
            accuracy=accuracy
        ),
        category_breakdown=category_breakdown,
        learning_style_distribution=learning_style_distribution,
        best_time_of_day=best_time_of_day,
        average_session_length=avg_session_length
    )


# =============================================================================
# LEARNING INSIGHTS
# =============================================================================

@router.get("/{child_id}/insights", response_model=List[LearningInsightResponse])
async def get_learning_insights(
    child_id: str,
    include_read: bool = Query(False),
    include_dismissed: bool = Query(False),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get learning insights for a child
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Build query
    conditions = [LearningInsight.child_id == child_id]
    if not include_read:
        conditions.append(LearningInsight.is_read == False)
    if not include_dismissed:
        conditions.append(LearningInsight.is_dismissed == False)
    
    insights_result = await db.execute(
        select(LearningInsight)
        .where(and_(*conditions))
        .order_by(
            LearningInsight.priority.desc(),
            desc(LearningInsight.generated_at)
        )
        .limit(limit)
    )
    insights = insights_result.scalars().all()
    
    return [LearningInsightResponse.from_orm(insight) for insight in insights]


@router.post("/{child_id}/insights", response_model=LearningInsightResponse)
async def create_learning_insight(
    child_id: str,
    request: LearningInsightCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new learning insight (admin/system use)
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    insight = LearningInsight(
        id=str(uuid.uuid4()),
        child_id=child_id,
        insight_type=request.insight_type,
        priority=request.priority,
        category=request.category,
        title=request.title,
        description=request.description,
        action_items=request.action_items,
        data=request.data,
        valid_until=request.valid_until
    )
    
    db.add(insight)
    await db.commit()
    await db.refresh(insight)
    
    return LearningInsightResponse.from_orm(insight)


@router.patch("/{child_id}/insights/{insight_id}", response_model=LearningInsightResponse)
async def update_learning_insight(
    child_id: str,
    insight_id: str,
    request: LearningInsightUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update insight status (mark as read/dismissed)
    """
    # Verify child belongs to parent
    child_result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not child_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Get insight
    insight_result = await db.execute(
        select(LearningInsight).where(
            and_(
                LearningInsight.id == insight_id,
                LearningInsight.child_id == child_id
            )
        )
    )
    insight = insight_result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    
    # Update fields
    if request.is_read is not None:
        insight.is_read = request.is_read
    if request.is_dismissed is not None:
        insight.is_dismissed = request.is_dismissed
    
    await db.commit()
    await db.refresh(insight)
    
    return LearningInsightResponse.from_orm(insight)


# =============================================================================
# WEEKLY REPORTS
# =============================================================================

@router.get("/{child_id}/reports", response_model=List[WeeklyReportResponse])
async def get_weekly_reports(
    child_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get weekly reports for a child
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    reports_result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.child_id == child_id)
        .order_by(desc(WeeklyReport.week_start_date))
        .limit(limit)
    )
    reports = reports_result.scalars().all()
    
    return [WeeklyReportResponse.from_orm(report) for report in reports]


# =============================================================================
# PARENTAL CONTROLS
# =============================================================================

@router.get("/{child_id}/controls", response_model=ParentalControlResponse)
async def get_parental_controls(
    child_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get parental control settings for a child
    """
    # Verify child belongs to parent
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Get or create parental control
    control_result = await db.execute(
        select(ParentalControl).where(ParentalControl.child_id == child_id)
    )
    control = control_result.scalar_one_or_none()
    
    if not control:
        # Create default parental control
        control = ParentalControl(
            id=str(uuid.uuid4()),
            child_id=child_id
        )
        db.add(control)
        await db.commit()
        await db.refresh(control)
    
    return ParentalControlResponse.from_orm(control)


@router.put("/{child_id}/controls", response_model=ParentalControlResponse)
async def update_parental_controls(
    child_id: str,
    request: ParentalControlUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update parental control settings
    """
    # Verify child belongs to parent
    child_result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    if not child_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Get or create parental control
    control_result = await db.execute(
        select(ParentalControl).where(ParentalControl.child_id == child_id)
    )
    control = control_result.scalar_one_or_none()
    
    if not control:
        control = ParentalControl(
            id=str(uuid.uuid4()),
            child_id=child_id
        )
        db.add(control)
    
    # Update fields
    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(control, field, value)
    
    control.updated_at = datetime.utcnow().isoformat()
    
    await db.commit()
    await db.refresh(control)
    
    return ParentalControlResponse.from_orm(control)
