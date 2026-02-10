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
from app.models.vocabulary import WordProgress, Word, Category
from app.models.analytics import LearningSession
from app.models.daily_words import DailyWordTracking
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
    
    # Calculate actual words learned from WordProgress table
    words_learned_result = await db.execute(
        select(func.count(WordProgress.id))
        .where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.exposure_count >= 1  # At least one exposure
            )
        )
    )
    actual_words_learned = words_learned_result.scalar() or 0
    
    # Update child's words_learned if different
    if child.words_learned != actual_words_learned:
        child.words_learned = actual_words_learned
        await db.commit()
        await db.refresh(child)
    
    # Get category progress - calculate from WordProgress records
    
    category_progress_result = await db.execute(
        select(
            Word.category,
            func.count(WordProgress.id).label('words_learned')
        )
        .join(Word, WordProgress.word_id == Word.id)
        .where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.exposure_count >= 1
            )
        )
        .group_by(Word.category)
    )
    category_counts = category_progress_result.all()
    
    # Get total words per category
    category_progress = []
    for cat_id, learned_count in category_counts:
        category_result = await db.execute(
            select(Category, func.count(Word.id))
            .join(Word, Category.id == Word.category)
            .where(Category.id == cat_id)
            .group_by(Category.id)
        )
        cat_data = category_result.first()
        if cat_data:
            category, total_words = cat_data
            
            # Calculate recent activity (last 7 days)
            seven_days_ago_cat = date.today() - timedelta(days=6)  # 6 days ago + today = 7 days
            seven_days_ago_cat_dt = datetime.combine(seven_days_ago_cat, datetime.min.time())
            recent_result = await db.execute(
                select(func.count(WordProgress.id))
                .join(Word, WordProgress.word_id == Word.id)
                .where(
                    and_(
                        WordProgress.child_id == child_id,
                        Word.category == cat_id,
                        WordProgress.last_practiced >= seven_days_ago_cat_dt
                    )
                )
            )
            recent_activity = recent_result.scalar() or 0
            
            category_progress.append(CategoryProgress(
                category_id=category.id,
                category_name=category.name,
                category_name_cantonese=category.name_cantonese or category.name,
                words_learned=learned_count,
                total_words=total_words,
                progress_percentage=(learned_count / total_words * 100) if total_words > 0 else 0,
                recent_activity=recent_activity
            ))
    
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
    
    # Calculate weekly stats dynamically from WordProgress (last 7 days including today)
    seven_days_ago = date.today() - timedelta(days=6)  # 6 days ago + today = 7 days
    # Convert to datetime for proper comparison with DateTime field
    seven_days_ago_dt = datetime.combine(seven_days_ago, datetime.min.time())
    
    # Count words practiced in the last 7 days
    weekly_progress_result = await db.execute(
        select(func.count(WordProgress.id.distinct()))
        .where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.last_practiced >= seven_days_ago_dt
            )
        )
    )
    weekly_words_count = weekly_progress_result.scalar() or 0
    
    # Count unique learning sessions (approximated by unique dates with activity)
    weekly_sessions_result = await db.execute(
        select(func.count(func.distinct(func.date(WordProgress.last_practiced))))
        .where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.last_practiced >= seven_days_ago_dt
            )
        )
    )
    weekly_sessions = weekly_sessions_result.scalar() or 0
    
    # Calculate XP earned (10 XP per word for new words, 5 XP for reviews)
    # For simplicity, count all words practiced in the last 7 days
    weekly_xp = weekly_words_count * 10  # Approximate
    
    # Learning time - we don't track this precisely yet, so estimate based on engagement
    # Approximate 2 minutes per word
    weekly_learning_time = weekly_words_count * 2
    
    return DashboardSummaryResponse(
        child_id=child.id,
        child_name=child.name,
        total_words_learned=child.words_learned,
        current_streak=child.current_streak,
        level=child.level,
        xp=child.xp,
        weekly_learning_time=weekly_learning_time,
        weekly_sessions=weekly_sessions,
        weekly_words_learned=weekly_words_count,
        weekly_xp_earned=weekly_xp,
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
        start_date = today - timedelta(days=6)  # 6 days ago + today = 7 days
        num_days = 7
    elif period == "month":
        start_date = today - timedelta(days=30)
        num_days = 30
    else:  # all
        start_date = date(2020, 1, 1)  # Far in the past
        num_days = (today - start_date).days
    
    # Convert start_date to datetime for proper comparison with DateTime field
    start_date_dt = datetime.combine(start_date, datetime.min.time())
    
    # Use DailyWordTracking table to get accurate word learning dates
    # This table tracks when words were first learned each day
    daily_tracking_result = await db.execute(
        select(DailyWordTracking, Word)
        .join(Word, DailyWordTracking.word_id == Word.id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_date_dt
            )
        )
    )
    tracking_records = daily_tracking_result.all()
    
    # Group by date and category
    date_stats = {}
    category_breakdown = {}
    
    for tracking, word in tracking_records:
        if tracking.date:
            learned_date = tracking.date.date()
            if learned_date >= start_date and learned_date <= today:
                # Initialize date entry if needed
                if learned_date not in date_stats:
                    date_stats[learned_date] = {
                        'words_learned': set(),  # Use set to avoid duplicates
                        'xp': 0
                    }
                
                # Add word to this date (set prevents duplicates)
                date_stats[learned_date]['words_learned'].add(tracking.word_id)
                
                # Aggregate categories
                if word.category not in category_breakdown:
                    category_breakdown[word.category] = set()
                category_breakdown[word.category].add(tracking.word_id)
    
    # Create time series arrays - generate a date for each day in range
    dates = []
    words_learned = []
    xp_earned = []
    
    current_date = start_date
    while current_date <= today:
        dates.append(str(current_date))
        
        day_stats = date_stats.get(current_date, {'words_learned': set(), 'xp': 0})
        words_count = len(day_stats['words_learned'])
        
        words_learned.append(words_count)
        xp_earned.append(words_count * 10)  # 10 XP per word
        
        current_date += timedelta(days=1)
    
    # Placeholder arrays (we don't track these precisely yet)
    learning_time = [words * 2 for words in words_learned]  # Approximate 2 min per word
    accuracy = [95.0 if words > 0 else 0.0 for words in words_learned]  # Approximate
    
    # Get category info and format progress data
    category_progress = []
    category_breakdown_for_response = {}
    
    if category_breakdown:
        categories_result = await db.execute(
            select(Category).where(Category.id.in_(list(category_breakdown.keys())))
        )
        categories = categories_result.scalars().all()
        
        for category in categories:
            # Calculate total words in category
            total_words_result = await db.execute(
                select(func.count(Word.id)).where(Word.category == category.id)
            )
            total_words = total_words_result.scalar() or 0
            
            # Count unique words learned in this category
            words_learned_count = len(category_breakdown[category.id])
            
            # Add to response dict (use cantonese name if available, fallback to English)
            category_breakdown_for_response[category.name_cantonese or category.name] = words_learned_count
            
            # Calculate recent activity (last 7 days) - count words practiced recently
            seven_days_ago_chart = date.today() - timedelta(days=6)  # 6 days ago + today = 7 days
            seven_days_ago_chart_dt = datetime.combine(seven_days_ago_chart, datetime.min.time())
            recent_result = await db.execute(
                select(func.count(WordProgress.id.distinct()))
                .join(Word, WordProgress.word_id == Word.id)
                .where(
                    and_(
                        WordProgress.child_id == child_id,
                        Word.category == category.id,
                        WordProgress.last_practiced >= seven_days_ago_chart_dt
                    )
                )
            )
            recent_activity = recent_result.scalar() or 0
            
            category_progress.append(CategoryProgress(
                category_id=category.id,
                category_name=category.name,
                category_name_cantonese=category.name_cantonese or category.name,
                words_learned=words_learned_count,
                total_words=total_words,
                progress_percentage=(words_learned_count / total_words * 100) if total_words > 0 else 0,
                recent_activity=recent_activity
            ))
    
    # Learning style distribution (placeholder - we don't track these separately yet)
    # Approximate based on word activity
    total_words_in_period = sum(words_learned)
    learning_style_distribution = {
        "games": 0,  # Would need separate tracking
        "stories": 0,  # Would need separate tracking
        "practice": len([w for w in words_learned if w > 0])  # Days with activity
    }
    
    # Calculate best time of day
    best_time_of_day = child.preferred_time_of_day.value if child.preferred_time_of_day else "morning"
    
    # Calculate average session length
    total_time = sum(learning_time)
    days_with_activity = len([w for w in words_learned if w > 0])
    average_session_length = int(total_time / days_with_activity) if days_with_activity > 0 else 0
    
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
        category_breakdown=category_breakdown_for_response,
        learning_style_distribution=learning_style_distribution,
        best_time_of_day=best_time_of_day,
        average_session_length=average_session_length
    )


@router.get("/{child_id}/words-by-date")
async def get_words_by_date(
    child_id: str,
    date_str: str = Query(..., description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all words learned by a child on a specific date
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
    
    # Parse date
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Get words from DailyWordTracking for this date
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    tracking_result = await db.execute(
        select(DailyWordTracking, Word, Category)
        .join(Word, DailyWordTracking.word_id == Word.id)
        .join(Category, Word.category == Category.id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_of_day,
                DailyWordTracking.date <= end_of_day
            )
        )
        .order_by(DailyWordTracking.created_at.desc())
    )
    records = tracking_result.all()
    
    # Format response
    words_data = []
    for tracking, word, category in records:
        words_data.append({
            "id": word.id,
            "word": word.word,
            "word_cantonese": word.word_cantonese,
            "jyutping": word.jyutping,
            "image_url": word.image_url,
            "category": category.name,
            "category_cantonese": category.name_cantonese,
            "definition": word.definition,
            "definition_cantonese": word.definition_cantonese,
            "exposure_count": tracking.exposure_count,
            "used_actively": tracking.used_actively,
            "mastery_confidence": tracking.mastery_confidence,
            "created_at": tracking.created_at.isoformat() if tracking.created_at else None
        })
    
    return {
        "date": date_str,
        "child_id": child_id,
        "words_count": len(words_data),
        "words": words_data
    }


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
