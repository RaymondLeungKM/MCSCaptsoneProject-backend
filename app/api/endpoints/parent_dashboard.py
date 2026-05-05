"""
Parent Analytics API Endpoints
Dashboard, insights, reports, and parental controls
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, or_, case
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


def _get_preferred_time_label(child: Child) -> str:
    time_of_day = getattr(child.preferred_time_of_day, "value", child.preferred_time_of_day)
    return {
        "morning": "早上",
        "afternoon": "下午",
        "evening": "晚上",
    }.get(time_of_day, "固定時段")


def _get_learning_style_label(child: Child) -> str:
    learning_style = getattr(child.learning_style, "value", child.learning_style)
    return {
        "visual": "視覺提示",
        "auditory": "聽覺提示",
        "kinesthetic": "動作參與",
        "mixed": "多元活動",
    }.get(learning_style, "多元活動")


def _get_mode_label(mode: str) -> str:
    return {
        "visual": "視覺",
        "auditory": "聽覺",
        "kinesthetic": "動作",
    }.get(mode, mode)


def _get_category_practice_tip(category_name: str) -> str:
    normalized = category_name.strip()
    if normalized in {"動物", "Animals"}:
        return "可用玩偶、故事書或角色扮演，讓孩子邊看邊說出動物名稱。"
    if normalized in {"食物", "Food"}:
        return "可在用餐時做實物指認，讓孩子描述顏色、味道和用途。"
    if normalized in {"顏色", "Colors"}:
        return "可做顏色尋寶或物件配對，把詞彙放進家中的真實情境。"
    if normalized in {"大自然", "Nature"}:
        return "可到公園觀察實物，邊看邊說名稱和特徵，幫助記憶更穩定。"
    if normalized in {"交通工具", "Vehicles"}:
        return "可用玩具車或街景圖片做分類與命名，增加生活連結。"
    if normalized in {"家庭", "Family"}:
        return "可用家庭照片做人物稱呼和關係配對，增加口語輸出機會。"
    return "可用圖片、實物或動作配對，把這個主題放進日常情境中反覆練習。"


def _build_learning_insight(
    *,
    child_id: str,
    insight_type: str,
    priority: str,
    title: str,
    description: str,
    action_items: List[str],
    category: Optional[str] = None,
    data: Optional[dict] = None,
) -> LearningInsight:
    timestamp = datetime.utcnow().isoformat()
    return LearningInsight(
        id=str(uuid.uuid4()),
        child_id=child_id,
        insight_type=insight_type,
        priority=priority,
        category=category,
        title=title,
        description=description,
        action_items=action_items,
        data=data or {},
        generated_at=timestamp,
        created_at=timestamp,
    )


async def _generate_default_learning_insights(
    child: Child,
    db: AsyncSession,
) -> List[LearningInsight]:
    weekly_window_start = datetime.combine(
        date.today() - timedelta(days=6),
        datetime.min.time(),
    )

    learned_words_result = await db.execute(
        select(func.count(WordProgress.id))
        .where(
            and_(
                WordProgress.child_id == child.id,
                WordProgress.exposure_count >= 1,
            )
        )
    )
    learned_words = learned_words_result.scalar() or 0

    mastered_words_result = await db.execute(
        select(func.count(WordProgress.id))
        .where(
            and_(
                WordProgress.child_id == child.id,
                WordProgress.mastered == True,
            )
        )
    )
    mastered_words = mastered_words_result.scalar() or 0

    active_days_result = await db.execute(
        select(func.count(func.distinct(func.date(WordProgress.last_practiced))))
        .where(
            and_(
                WordProgress.child_id == child.id,
                WordProgress.last_practiced.is_not(None),
                WordProgress.last_practiced >= weekly_window_start,
            )
        )
    )
    active_days = active_days_result.scalar() or 0

    exposure_mode_result = await db.execute(
        select(
            func.coalesce(func.sum(WordProgress.visual_exposures), 0),
            func.coalesce(func.sum(WordProgress.auditory_exposures), 0),
            func.coalesce(func.sum(WordProgress.kinesthetic_exposures), 0),
        ).where(WordProgress.child_id == child.id)
    )
    visual_exposures, auditory_exposures, kinesthetic_exposures = (
        exposure_mode_result.one()
    )

    category_progress_result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.name_cantonese,
            func.count(Word.id).label("total_words"),
            func.count(WordProgress.id).label("learned_words"),
        )
        .select_from(Category)
        .join(
            Word,
            and_(
                Word.category == Category.id,
                Word.is_active == True,
            ),
        )
        .outerjoin(
            WordProgress,
            and_(
                WordProgress.word_id == Word.id,
                WordProgress.child_id == child.id,
                WordProgress.exposure_count >= 1,
            ),
        )
        .where(Category.is_active == True)
        .group_by(Category.id, Category.name, Category.name_cantonese)
    )

    category_progress = []
    for category_id, category_name, category_name_cantonese, total_words, learned_count in category_progress_result.all():
        progress_percentage = (
            learned_count / total_words * 100 if total_words else 0
        )
        category_progress.append(
            {
                "category_id": category_id,
                "category_name": category_name,
                "category_name_cantonese": category_name_cantonese or category_name,
                "total_words": total_words,
                "learned_words": learned_count,
                "progress_percentage": progress_percentage,
            }
        )

    category_progress.sort(key=lambda item: item["progress_percentage"])
    weakest_category = next(
        (item for item in category_progress if item["learned_words"] < item["total_words"]),
        category_progress[0] if category_progress else None,
    )

    insights: List[LearningInsight] = []

    if learned_words == 0:
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="recommendation",
                priority="high",
                title="先建立第一個每日學習節奏",
                description=(
                    f"{child.name} 目前還未累積詞彙學習紀錄，建議先從 1 至 2 個日常詞彙開始，"
                    "讓孩子先建立成功感。"
                ),
                action_items=[
                    f"優先安排在{_get_preferred_time_label(child)}做 5 至 10 分鐘短練習，先完成每日目標。",
                ],
                data={"source": "auto-bootstrap", "kind": "onboarding"},
            )
        )
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="recommendation",
                priority="medium",
                title="從生活情境開始最容易建立詞彙連結",
                description="先從吃飯、玩具、家庭成員等每天都會碰到的內容開始，比一次塞太多新詞更有效。",
                action_items=[
                    "可以指著身邊的實物說名稱，再請孩子跟讀或做對應動作。",
                ],
                data={"source": "auto-bootstrap", "kind": "context"},
            )
        )
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="recommendation",
                priority="medium",
                title="一開始就加入多感官提示",
                description=(
                    f"{child.name} 的學習偏好較適合配合{_get_learning_style_label(child)}，"
                    "同一個詞彙若能同時看、聽、做，會更容易記住。"
                ),
                action_items=[
                    "可把圖片、口頭提示和身體動作放在同一次練習中一起使用。",
                ],
                data={"source": "auto-bootstrap", "kind": "learning-style"},
            )
        )
        return insights

    if child.current_streak >= 3:
        title = f"已連續學習 {child.current_streak} 天，節奏開始穩定"
        description = (
            f"{child.name} 這段時間已建立連續學習習慣，現在是把已接觸詞彙轉成主動輸出的好時機。"
        )
        action_item = f"維持在{_get_preferred_time_label(child)}安排短練習，避免一次拉太長。"
    else:
        title = f"已接觸 {learned_words} 個詞彙，可開始加強穩定度"
        description = (
            f"目前已有 {mastered_words} 個詞彙達到較穩定掌握，持續小步前進會比集中衝刺更有效。"
        )
        action_item = "每天固定完成少量高頻複習，比偶爾做一次大量練習更容易留住記憶。"

    insights.append(
        _build_learning_insight(
            child_id=child.id,
            insight_type="milestone" if child.current_streak >= 3 else "strength",
            priority="high",
            title=title,
            description=description,
            action_items=[action_item],
            data={
                "source": "auto-bootstrap",
                "learned_words": learned_words,
                "mastered_words": mastered_words,
                "active_days": active_days,
            },
        )
    )

    if weakest_category:
        weakest_name = weakest_category["category_name_cantonese"]
        remaining_words = max(
            weakest_category["total_words"] - weakest_category["learned_words"],
            0,
        )
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="weakness",
                priority="high"
                if weakest_category["progress_percentage"] < 50
                else "medium",
                title=f"可優先加強「{weakest_name}」主題",
                description=(
                    f"目前此主題已接觸 {weakest_category['learned_words']} / {weakest_category['total_words']} 個詞彙，"
                    f"尚有 {remaining_words} 個詞彙可再加強。"
                ),
                action_items=[_get_category_practice_tip(weakest_name)],
                category=weakest_category["category_name"],
                data={
                    "source": "auto-bootstrap",
                    "progress_percentage": weakest_category["progress_percentage"],
                    "remaining_words": remaining_words,
                },
            )
        )

    exposure_totals = {
        "visual": visual_exposures,
        "auditory": auditory_exposures,
        "kinesthetic": kinesthetic_exposures,
    }
    total_exposures = sum(exposure_totals.values())
    dominant_mode = max(exposure_totals, key=exposure_totals.get)
    dominant_ratio = (
        exposure_totals[dominant_mode] / total_exposures if total_exposures else 0
    )

    if total_exposures == 0 or dominant_ratio >= 0.65:
        mode_label = _get_mode_label(dominant_mode)
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="recommendation",
                priority="medium",
                title="可再增加多感官學習提示",
                description=(
                    f"目前練習較偏向{mode_label}提示，若能加入圖片、聲音和動作的交替使用，"
                    "通常更有助於幼兒記住新詞。"
                ),
                action_items=[
                    "同一個詞彙可先看圖，再聽讀音，最後配合一個動作或生活情境練習。",
                ],
                data={
                    "source": "auto-bootstrap",
                    "dominant_mode": dominant_mode,
                    "dominant_ratio": dominant_ratio,
                },
            )
        )
    else:
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="strength",
                priority="medium",
                title="多感官接觸分布較平均",
                description=(
                    f"{child.name} 最近的練習同時包含圖片、聽覺和動作元素，這種搭配對穩定記憶有幫助。"
                ),
                action_items=[
                    "可把已熟悉的詞彙加入口語輸出或小故事，幫助從辨認走向主動使用。",
                ],
                data={"source": "auto-bootstrap", "total_exposures": total_exposures},
            )
        )

    return insights[:3]


async def _ensure_learning_insights_exist(
    child: Child,
    db: AsyncSession,
) -> None:
    existing_result = await db.execute(
        select(LearningInsight.id)
        .where(LearningInsight.child_id == child.id)
        .limit(1)
    )
    if existing_result.scalar_one_or_none():
        return

    generated_insights = await _generate_default_learning_insights(child, db)
    if not generated_insights:
        return

    db.add_all(generated_insights)
    await db.commit()


def _learning_insight_priority_order():
    return case(
        (LearningInsight.priority == "high", 0),
        (LearningInsight.priority == "medium", 1),
        (LearningInsight.priority == "low", 2),
        else_=3,
    )


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

    await _ensure_learning_insights_exist(child, db)
    
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
            _learning_insight_priority_order(),
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
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    await _ensure_learning_insights_exist(child, db)
    
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
            _learning_insight_priority_order(),
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
