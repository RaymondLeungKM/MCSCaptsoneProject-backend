"""
Parent Analytics API Endpoints
Dashboard, insights, reports, and parental controls
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, or_, case
from typing import List, Optional
from datetime import datetime, date, time, timedelta, timezone
import uuid

from app.db.session import get_db
from app.models.user import User, Child
from app.models.parent_analytics import (
    LearningInsight,
    WeeklyReport,
    ParentalControl
)
from app.models.analytics_foundation import ChildDayAnalytics, ContentPerformanceAnalytics
from app.models.vocabulary import WordProgress, Word, Category
from app.models.analytics import LearningSession
from app.models.daily_words import DailyWordTracking
from app.schemas.parent_analytics import (
    LearningInsightResponse,
    LearningInsightCreateRequest,
    LearningInsightUpdateRequest,
    WeeklyReportResponse,
    ParentalControlResponse,
    ParentalControlUpdateRequest,
    DashboardSummaryResponse,
    CategoryProgress,
    AnalyticsChartsResponse,
    LearningTimeSeriesData,
    WeeklyDeltaMetric,
    WeeklyDeltaResponse,
    BenchmarkCard,
    BenchmarkSuppression,
    CategoryBenchmarkCard,
    ParentBenchmarksResponse,
)
from app.core.security import get_current_user
from app.services.child_metrics import sync_child_metrics
from app.services.analytics_foundation import resolve_age_band
from app.services.privacy_gate import (
    DEFAULT_MINIMUM_COHORT_THRESHOLD,
    evaluate_privacy_gate,
    suppression_payload,
)

router = APIRouter(prefix="/parent-dashboard", tags=["parent-dashboard"])

MAX_SESSION_MINUTES = 90
HKT = timezone(timedelta(hours=8), name="HKT")


def _local_today() -> date:
    return datetime.now(HKT).date()


def _local_day_bounds(local_day: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(local_day, time.min, tzinfo=HKT)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _local_date_window(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    start_at, _ = _local_day_bounds(start_day)
    end_at, _ = _local_day_bounds(end_day + timedelta(days=1))
    return start_at, end_at


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


def _build_category_mastery_progress(
    *,
    category_id: str,
    category_name: str,
    category_name_cantonese: Optional[str],
    total_words: int,
    mastered_words: int,
    recent_activity: int = 0,
) -> CategoryProgress:
    mastered_count = max(mastered_words or 0, 0)
    total_count = max(total_words or 0, 0)

    return CategoryProgress(
        category_id=category_id,
        category_name=category_name,
        category_name_cantonese=category_name_cantonese or category_name,
        words_learned=mastered_count,
        total_words=total_count,
        progress_percentage=(mastered_count / total_count * 100) if total_count > 0 else 0,
        recent_activity=recent_activity,
    )


def _is_my_collection_category_name(
    category_name: str | None,
    category_name_cantonese: str | None,
) -> bool:
    normalized_name = (category_name or "").strip().lower()
    normalized_cantonese = (category_name_cantonese or "").strip()
    return normalized_name == "my collection" or normalized_cantonese in {
        "我的",
        "我的收藏",
    }


async def _get_child_owned_collection_progress_counts(
    child_id: str,
    db: AsyncSession,
) -> tuple[int, int]:
    total_words_result = await db.execute(
        select(func.count(Word.id)).where(
            Word.is_active == True,
            Word.created_by_child_id == child_id,
        )
    )
    total_words = total_words_result.scalar_one() or 0

    if total_words == 0:
        return 0, 0

    mastered_words_result = await db.execute(
        select(func.count(WordProgress.id))
        .select_from(Word)
        .join(
            WordProgress,
            and_(
                WordProgress.word_id == Word.id,
                WordProgress.child_id == child_id,
                WordProgress.mastered.is_(True),
            ),
        )
        .where(
            Word.is_active == True,
            Word.created_by_child_id == child_id,
        )
    )
    mastered_words = mastered_words_result.scalar_one() or 0
    return total_words, mastered_words


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


def _is_auto_generated_learning_insight(insight: LearningInsight) -> bool:
    return isinstance(insight.data, dict) and insight.data.get("source") == "auto-bootstrap"


def _get_auto_generated_learning_insight_key(
    insight: LearningInsight,
) -> Optional[str]:
    data = insight.data if isinstance(insight.data, dict) else {}

    explicit_key = data.get("insight_key")
    if isinstance(explicit_key, str) and explicit_key.strip():
        return explicit_key

    kind = data.get("kind")
    if kind == "onboarding":
        return "onboarding-rhythm"
    if kind == "context":
        return "onboarding-context"
    if kind == "learning-style":
        return "onboarding-learning-style"

    if any(metric in data for metric in ("learned_words", "mastered_words", "active_days")):
        return "weekly-momentum"

    if "progress_percentage" in data or "remaining_words" in data:
        category_key = insight.category or data.get("category_name") or "general"
        return f"category-focus:{category_key}"

    if "dominant_mode" in data or "total_exposures" in data:
        return "multi-sensory-balance"

    return None


def _replace_learning_insight_content(
    existing: LearningInsight,
    candidate: LearningInsight,
) -> bool:
    payload_changed = any(
        (
            existing.insight_type != candidate.insight_type,
            existing.priority != candidate.priority,
            existing.category != candidate.category,
            existing.title != candidate.title,
            existing.description != candidate.description,
            existing.action_items != candidate.action_items,
            existing.data != candidate.data,
            existing.valid_until != candidate.valid_until,
        )
    )

    if not payload_changed:
        return False

    existing.insight_type = candidate.insight_type
    existing.priority = candidate.priority
    existing.category = candidate.category
    existing.title = candidate.title
    existing.description = candidate.description
    existing.action_items = candidate.action_items
    existing.data = candidate.data
    existing.valid_until = candidate.valid_until
    existing.generated_at = candidate.generated_at

    if not existing.is_dismissed:
        existing.is_read = False

    return True


def _normalize_tracking_day(value):
    if isinstance(value, datetime):
        return _ensure_utc(value).astimezone(HKT).date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return _normalize_tracking_day(
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            )
    return value


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rounded_duration_minutes(start_time: datetime, end_time: datetime) -> int:
    total_seconds = max((end_time - start_time).total_seconds(), 0)
    if total_seconds <= 0:
        return 0
    return max(1, int((total_seconds + 59) // 60))


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda interval: interval[0])
    merged: list[tuple[datetime, datetime]] = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        previous_start, previous_end = merged[-1]
        if current_start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, current_end))
            continue

        merged.append((current_start, current_end))

    return merged


def _total_interval_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    return sum(
        max((end_time - start_time).total_seconds(), 0.0)
        for start_time, end_time in _merge_intervals(intervals)
    )


def _rounded_minutes_from_total_seconds(
    total_seconds: float,
    *,
    has_words: bool = False,
) -> int:
    if total_seconds <= 0:
        return 0

    rounded_minutes = int((total_seconds + 30) // 60)
    if rounded_minutes > 0:
        return rounded_minutes

    if has_words:
        return 1

    return 0


def _percentile_band(values: list[float], child_value: float) -> str:
    if not values:
        return "P0-P25"

    sorted_values = sorted(values)
    position = sum(1 for value in sorted_values if value <= child_value) / len(sorted_values)

    if position < 0.25:
        return "P0-P25"
    if position < 0.5:
        return "P25-P50"
    if position < 0.75:
        return "P50-P75"
    return "P75-P100"


def _benchmark_band(child_value: float, cohort_value: float) -> str:
    if cohort_value <= 0:
        return "on_track"

    ratio = child_value / cohort_value
    if ratio >= 1.2:
        return "ahead"
    if ratio >= 0.9:
        return "on_track"
    return "needs_support"


def _benchmark_tip(metric: str, band: str) -> str:
    tips = {
        "pace": {
            "ahead": "孩子目前進度較快，可把新詞語放進故事與對話，增加主動輸出。",
            "on_track": "孩子進度與同齡組相若，維持每日短練習最有幫助。",
            "needs_support": "建議把任務切成更短回合，並多做舊詞重溫再接新詞。",
        },
        "engagement": {
            "ahead": "孩子投入時間穩定，可加入更多情境任務提升語用能力。",
            "on_track": "目前投入度穩定，保持固定時段學習即可。",
            "needs_support": "可以先揀你嘅小朋友鍾意嘅主題開始，每次做 5–10 分鐘，慢慢建立習慣。",
        },
    }
    return tips.get(metric, {}).get(band, "維持穩定節奏，逐步增加真實情境練習。")


def _trend_label(first_half_value: float, second_half_value: float) -> str:
    if second_half_value > first_half_value * 1.1:
        return "up"
    if second_half_value < first_half_value * 0.9:
        return "down"
    return "flat"


async def _get_recent_tracking_activity(
    child_id: str,
    db: AsyncSession,
    start_date: date,
    end_date: Optional[date] = None,
) -> tuple[int, set[date], dict]:
    resolved_end_date = end_date or _local_today()
    start_at, end_at = _local_date_window(start_date, resolved_end_date)

    tracking_result = await db.execute(
        select(
            DailyWordTracking.date,
            DailyWordTracking.word_id,
            Word.category.label("category_id"),
        )
        .join(Word, DailyWordTracking.word_id == Word.id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_at,
                DailyWordTracking.date < end_at,
            )
        )
    )

    unique_words = set()
    active_days = set()
    category_words = {}

    for tracked_day, word_id, category_id in tracking_result.all():
        resolved_day = _normalize_tracking_day(tracked_day)
        if resolved_day is None:
            continue

        unique_words.add(word_id)
        active_days.add(resolved_day)

        if category_id is None:
            continue

        if category_id not in category_words:
            category_words[category_id] = set()

        category_words[category_id].add(word_id)

    return (
        len(unique_words),
        active_days,
        {
            category_id: len(word_ids)
            for category_id, word_ids in category_words.items()
        },
    )


def _resolved_session_window(
    session: LearningSession,
    *,
    now_utc: datetime,
) -> tuple[datetime, datetime] | None:
    if not session.start_time:
        return None

    if session.duration_minutes is not None and session.duration_minutes > MAX_SESSION_MINUTES:
        return None

    session_start = _ensure_utc(session.start_time)
    raw_session_end = session.end_time or now_utc
    session_end = min(
        _ensure_utc(raw_session_end),
        session_start + timedelta(minutes=MAX_SESSION_MINUTES),
    )

    if session_end <= session_start:
        return None

    return session_start, session_end


def _split_session_intervals_by_day(
    session: LearningSession,
    *,
    now_utc: datetime,
) -> dict[date, list[tuple[datetime, datetime]]]:
    resolved_window = _resolved_session_window(session, now_utc=now_utc)
    if resolved_window is None:
        return {}

    session_start, session_end = resolved_window
    intervals_by_day: dict[date, list[tuple[datetime, datetime]]] = {}
    cursor = session_start

    while cursor < session_end:
        local_cursor = cursor.astimezone(HKT)
        next_local_day_start = datetime.combine(
            local_cursor.date() + timedelta(days=1),
            time.min,
            tzinfo=HKT,
        ).astimezone(timezone.utc)
        segment_end = min(session_end, next_local_day_start)
        intervals_by_day.setdefault(local_cursor.date(), []).append(
            (cursor, segment_end)
        )
        cursor = segment_end

    return intervals_by_day


def _summarize_sessions_by_day(
    sessions: list[LearningSession],
    *,
    start_day: date,
    end_day: date,
    now_utc: Optional[datetime] = None,
) -> dict[date, dict[str, float | int]]:
    resolved_now = now_utc or datetime.now(timezone.utc)
    day_buckets = {
        start_day + timedelta(days=offset): {
            "intervals": [],
            "session_count": 0,
        }
        for offset in range((end_day - start_day).days + 1)
    }
    session_windows: list[tuple[datetime, datetime]] = []

    for session in sessions:
        resolved_window = _resolved_session_window(session, now_utc=resolved_now)
        if resolved_window is None:
            continue

        session_windows.append(resolved_window)

        for tracked_day, intervals in _split_session_intervals_by_day(
            session,
            now_utc=resolved_now,
        ).items():
            if tracked_day not in day_buckets:
                continue

            day_buckets[tracked_day]["intervals"].extend(intervals)

    for session_start, _ in _merge_intervals(session_windows):
        session_day = _normalize_tracking_day(session_start)
        if session_day not in day_buckets:
            continue

        day_buckets[session_day]["session_count"] += 1

    return {
        tracked_day: {
            "total_seconds": _total_interval_seconds(bucket["intervals"]),
            "session_count": bucket["session_count"],
        }
        for tracked_day, bucket in day_buckets.items()
    }


def _get_session_duration_minutes(session: LearningSession) -> int:
    resolved_window = _resolved_session_window(
        session,
        now_utc=datetime.now(timezone.utc),
    )
    if resolved_window is None:
        return 0

    session_start, session_end = resolved_window
    return _rounded_duration_minutes(session_start, session_end)


async def _build_live_weekly_report(
    child: Child,
    db: AsyncSession,
    week_start_date: Optional[date] = None,
) -> WeeklyReportResponse:
    today = _local_today()
    week_start = week_start_date or (today - timedelta(days=today.weekday()))
    week_end = week_start + timedelta(days=6)

    total_words_learned, tracking_days, category_activity = (
        await _get_recent_tracking_activity(
            child.id,
            db,
            week_start,
            week_end,
        )
    )

    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = week_start - timedelta(days=1)
    previous_words_learned, _, _ = await _get_recent_tracking_activity(
        child.id,
        db,
        previous_week_start,
        previous_week_end,
    )
    start_at, end_at = _local_date_window(week_start, week_end)

    sessions_result = await db.execute(
        select(LearningSession).where(
            and_(
                LearningSession.child_id == child.id,
                LearningSession.start_time < end_at,
                or_(
                    LearningSession.end_time.is_(None),
                    LearningSession.end_time > start_at,
                ),
            )
        )
    )
    sessions = sessions_result.scalars().all()
    session_daily_stats = _summarize_sessions_by_day(
        sessions,
        start_day=week_start,
        end_day=week_end,
    )
    total_learning_time = 0
    total_sessions = 0
    session_active_days = set()

    for tracked_day, day_stats in session_daily_stats.items():
        total_seconds = float(day_stats["total_seconds"])
        rounded_minutes = _rounded_minutes_from_total_seconds(
            total_seconds,
            has_words=tracked_day in tracking_days,
        )

        if rounded_minutes > 0:
            session_active_days.add(tracked_day)

        if rounded_minutes > 0 or tracked_day in tracking_days:
            total_sessions += int(day_stats["session_count"])

        total_learning_time += rounded_minutes

    days_active = len(tracking_days | session_active_days)

    category_names: dict[str, str] = {}
    if category_activity:
        categories_result = await db.execute(
            select(Category.id, Category.name, Category.name_cantonese).where(
                Category.id.in_(list(category_activity.keys()))
            )
        )
        category_names = {
            category_id: name_cantonese or name
            for category_id, name, name_cantonese in categories_result.all()
        }

    top_categories = [
        {
            "category": category_names.get(category_id, category_id),
            "words": word_count,
        }
        for category_id, word_count in sorted(
            category_activity.items(),
            key=lambda item: (-item[1], category_names.get(item[0], item[0])),
        )[:3]
    ]

    strengths: List[str] = []
    if top_categories:
        strengths.append(f"本週最常接觸「{top_categories[0]['category']}」主題")
    if days_active >= 4:
        strengths.append(f"本週有 {days_active} 天保持學習節奏")
    elif days_active > 0:
        strengths.append(f"本週已累積 {days_active} 天學習紀錄")
    if total_learning_time >= 20:
        strengths.append("已累積穩定的短時段練習")
    if not strengths and total_words_learned > 0:
        strengths.append(f"本週已接觸 {total_words_learned} 個不同詞彙")

    recommendations: List[str] = []
    if total_words_learned == 0:
        recommendations.append(
            f"可先在{_get_preferred_time_label(child)}安排一次 5 至 10 分鐘短練習，重新啟動節奏。"
        )
    else:
        if days_active < 4:
            recommendations.append(
                "可把練習分散到更多日子，每次 5 至 10 分鐘即可。"
            )
        if top_categories:
            recommendations.append(
                _get_category_practice_tip(top_categories[0]["category"])
            )
        if total_sessions < 3:
            recommendations.append(
                "可多安排 1 至 2 次短練習，幫助孩子更穩定地回想詞彙。"
            )

    areas_to_improve: List[str] = []
    if total_words_learned > 0 and days_active < 3:
        areas_to_improve.append("本週固定練習日數仍可再提升")
    if total_words_learned > 0 and total_sessions < 2:
        areas_to_improve.append("本週互動練習次數仍可再增加")

    if previous_words_learned > 0:
        growth_percentage = round(
            ((total_words_learned - previous_words_learned) / previous_words_learned) * 100,
            1,
        )
    elif total_words_learned > 0:
        growth_percentage = 100.0
    else:
        growth_percentage = 0.0

    return WeeklyReportResponse(
        id=f"live-{child.id}-{week_start.isoformat()}",
        child_id=child.id,
        week_start_date=week_start,
        week_end_date=week_end,
        total_words_learned=total_words_learned,
        total_learning_time=total_learning_time,
        total_sessions=total_sessions,
        days_active=days_active,
        milestones_reached=[],
        new_badges_earned=[],
        top_categories=top_categories,
        strengths=strengths[:3],
        areas_to_improve=areas_to_improve[:3],
        recommendations=recommendations[:3],
        growth_percentage=growth_percentage,
        is_sent=False,
        sent_at=None,
    )


def _build_weekly_delta_metric(
    current_value: int,
    previous_value: int,
) -> WeeklyDeltaMetric:
    return WeeklyDeltaMetric(
        current=current_value,
        previous=previous_value,
        delta=current_value - previous_value,
    )


def _build_weekly_delta_summary(
    current_report: WeeklyReportResponse,
    previous_report: WeeklyReportResponse,
) -> WeeklyDeltaResponse:
    current_xp = current_report.total_words_learned * 10
    previous_xp = previous_report.total_words_learned * 10

    return WeeklyDeltaResponse(
        current_week_start_date=current_report.week_start_date,
        current_week_end_date=current_report.week_end_date,
        previous_week_start_date=previous_report.week_start_date,
        previous_week_end_date=previous_report.week_end_date,
        words_learned=_build_weekly_delta_metric(
            current_report.total_words_learned,
            previous_report.total_words_learned,
        ),
        learning_time=_build_weekly_delta_metric(
            current_report.total_learning_time,
            previous_report.total_learning_time,
        ),
        sessions=_build_weekly_delta_metric(
            current_report.total_sessions,
            previous_report.total_sessions,
        ),
        xp_earned=_build_weekly_delta_metric(current_xp, previous_xp),
        active_days=_build_weekly_delta_metric(
            current_report.days_active,
            previous_report.days_active,
        ),
    )


async def _generate_default_learning_insights(
    child: Child,
    db: AsyncSession,
) -> List[LearningInsight]:
    weekly_window_start = _local_today() - timedelta(days=6)

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

    _, active_days, _ = await _get_recent_tracking_activity(
        child.id,
        db,
        weekly_window_start,
    )
    active_days_count = len(active_days)

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
            func.count(WordProgress.id).filter(
                WordProgress.mastered.is_(True)
            ).label("mastered_words"),
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
            ),
        )
        .where(Category.is_active == True)
        .group_by(Category.id, Category.name, Category.name_cantonese)
    )

    category_progress = []
    for (
        category_id,
        category_name,
        category_name_cantonese,
        total_words,
        mastered_count,
    ) in category_progress_result.all():
        category_progress.append(
            _build_category_mastery_progress(
                category_id=category_id,
                category_name=category_name,
                category_name_cantonese=category_name_cantonese,
                total_words=total_words,
                mastered_words=mastered_count,
            )
        )

    category_progress.sort(key=lambda item: item.progress_percentage)
    weakest_category = next(
        (item for item in category_progress if item.words_learned < item.total_words),
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
                data={
                    "source": "auto-bootstrap",
                    "kind": "onboarding",
                    "insight_key": "onboarding-rhythm",
                },
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
                data={
                    "source": "auto-bootstrap",
                    "kind": "context",
                    "insight_key": "onboarding-context",
                },
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
                data={
                    "source": "auto-bootstrap",
                    "kind": "learning-style",
                    "insight_key": "onboarding-learning-style",
                },
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
                "insight_key": "weekly-momentum",
                "learned_words": learned_words,
                "mastered_words": mastered_words,
                "active_days": active_days_count,
            },
        )
    )

    if weakest_category:
        weakest_name = weakest_category.category_name_cantonese
        remaining_words = max(
            weakest_category.total_words - weakest_category.words_learned,
            0,
        )
        insights.append(
            _build_learning_insight(
                child_id=child.id,
                insight_type="weakness",
                priority="high"
                if weakest_category.progress_percentage < 50
                else "medium",
                title=f"可優先加強「{weakest_name}」主題",
                description=(
                    f"目前此主題已掌握 {weakest_category.words_learned} / {weakest_category.total_words} 個詞彙，"
                    f"尚有 {remaining_words} 個詞彙可再加強。"
                ),
                action_items=[_get_category_practice_tip(weakest_name)],
                category=weakest_category.category_name,
                data={
                    "source": "auto-bootstrap",
                    "insight_key": f"category-focus:{weakest_category.category_name}",
                    "category_name": weakest_category.category_name,
                    "progress_percentage": weakest_category.progress_percentage,
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
                    "insight_key": "multi-sensory-balance",
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
                data={
                    "source": "auto-bootstrap",
                    "insight_key": "multi-sensory-balance",
                    "total_exposures": total_exposures,
                },
            )
        )

    return insights[:3]


async def _sync_learning_insights(
    child: Child,
    db: AsyncSession,
) -> None:
    existing_result = await db.execute(
        select(LearningInsight).where(LearningInsight.child_id == child.id)
    )
    existing_insights = existing_result.scalars().all()

    auto_generated_by_key: dict[str, LearningInsight] = {}
    stale_auto_generated: list[LearningInsight] = []

    for insight in existing_insights:
        if not _is_auto_generated_learning_insight(insight):
            continue

        insight_key = _get_auto_generated_learning_insight_key(insight)
        if insight_key is None:
            stale_auto_generated.append(insight)
            continue

        auto_generated_by_key[insight_key] = insight

    generated_insights = await _generate_default_learning_insights(child, db)
    changed = False

    for candidate in generated_insights:
        insight_key = _get_auto_generated_learning_insight_key(candidate)
        if insight_key is None:
            continue

        existing = auto_generated_by_key.pop(insight_key, None)
        if existing is None:
            db.add(candidate)
            changed = True
            continue

        if _replace_learning_insight_content(existing, candidate):
            changed = True

    for stale_insight in [*stale_auto_generated, *auto_generated_by_key.values()]:
        await db.delete(stale_insight)
        changed = True

    if changed:
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

    today = _local_today()
    if await sync_child_metrics(db, child, as_of=today):
        await db.commit()
        await db.refresh(child)

    await _sync_learning_insights(child, db)

    seven_days_ago = today - timedelta(days=6)
    _, _, recent_category_activity = await _get_recent_tracking_activity(
        child_id,
        db,
        seven_days_ago,
    )
    
    # Get category progress - calculate from WordProgress records
    
    category_progress_result = await db.execute(
        select(
            Word.category,
            func.count(WordProgress.id).filter(
                WordProgress.mastered.is_(True)
            ).label('mastered_words')
        )
        .join(Word, WordProgress.word_id == Word.id)
        .where(
            and_(
                WordProgress.child_id == child_id,
                Word.is_active == True,
            )
        )
        .group_by(Word.category)
    )
    category_counts = category_progress_result.all()
    
    # Get total words per category
    category_progress = []
    for cat_id, mastered_count in category_counts:
        category_result = await db.execute(
            select(Category, func.count(Word.id))
            .join(Word, Category.id == Word.category)
            .where(Category.id == cat_id, Word.is_active == True)
            .group_by(Category.id)
        )
        cat_data = category_result.first()
        if cat_data:
            category, total_words = cat_data
            recent_activity = recent_category_activity.get(cat_id, 0)
            mastered_for_category = mastered_count

            if _is_my_collection_category_name(
                category.name,
                category.name_cantonese,
            ):
                total_words, mastered_for_category = (
                    await _get_child_owned_collection_progress_counts(
                        child_id,
                        db,
                    )
                )
                if total_words == 0:
                    continue

            category_progress.append(
                _build_category_mastery_progress(
                    category_id=category.id,
                    category_name=category.name,
                    category_name_cantonese=category.name_cantonese,
                    total_words=total_words,
                    mastered_words=mastered_for_category,
                    recent_activity=recent_activity,
                )
            )
    
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
    
    latest_report = await _build_live_weekly_report(child, db)
    previous_report = await _build_live_weekly_report(
        child,
        db,
        latest_report.week_start_date - timedelta(days=7),
    )
    weekly_delta = _build_weekly_delta_summary(latest_report, previous_report)
    
    # Get parental control settings
    control_result = await db.execute(
        select(ParentalControl).where(ParentalControl.child_id == child_id)
    )
    parental_control = control_result.scalar_one_or_none()
    
    # Calculate XP earned (10 XP per word for new words, 5 XP for reviews)
    # For simplicity, count all words practiced in the last 7 days
    weekly_xp = latest_report.total_words_learned * 10
    weekly_learning_time = latest_report.total_learning_time
    
    return DashboardSummaryResponse(
        child_id=child.id,
        child_name=child.name,
        total_words_learned=child.words_learned,
        current_streak=child.current_streak,
        level=child.level,
        xp=child.xp,
        weekly_learning_time=weekly_learning_time,
        weekly_sessions=latest_report.total_sessions,
        weekly_words_learned=latest_report.total_words_learned,
        weekly_xp_earned=weekly_xp,
        weekly_delta=weekly_delta,
        category_progress=category_progress,
        recent_insights=[LearningInsightResponse.from_orm(i) for i in insights],
        latest_report=latest_report,
        parental_control=ParentalControlResponse.from_orm(parental_control) if parental_control else None
    )


@router.get("/{child_id}/benchmarks", response_model=ParentBenchmarksResponse)
async def get_parent_benchmarks(
    child_id: str,
    range_days: int = Query(28, ge=7, le=90),
    minimum_cohort_threshold: int = Query(
        DEFAULT_MINIMUM_COHORT_THRESHOLD,
        ge=1,
        le=100,
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Child).where(and_(Child.id == child_id, Child.parent_id == current_user.id))
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    today = _local_today()
    start_day = today - timedelta(days=range_days - 1)
    child_age_band = resolve_age_band(child.age)

    child_rows_result = await db.execute(
        select(ChildDayAnalytics).where(
            ChildDayAnalytics.child_id == child_id,
            ChildDayAnalytics.activity_day >= start_day,
            ChildDayAnalytics.activity_day <= today,
        )
    )
    child_rows = child_rows_result.scalars().all()

    cohort_rows_result = await db.execute(
        select(ChildDayAnalytics).where(
            ChildDayAnalytics.age_band == child_age_band,
            ChildDayAnalytics.activity_day >= start_day,
            ChildDayAnalytics.activity_day <= today,
        )
    )
    cohort_rows = cohort_rows_result.scalars().all()

    cohort_by_child: dict[str, dict[str, float]] = {}
    for row in cohort_rows:
        state = cohort_by_child.setdefault(
            row.child_id,
            {
                "words_mastered": 0.0,
                "session_minutes": 0.0,
                "active_days": 0.0,
            },
        )
        state["words_mastered"] += row.words_mastered or 0
        state["session_minutes"] += row.session_minutes_total or 0
        state["active_days"] += 1

    cohort_size = len(cohort_by_child)
    gate = evaluate_privacy_gate(
        user=current_user,
        cohort_size=cohort_size,
        minimum_cohort_threshold=minimum_cohort_threshold,
    )
    suppression = BenchmarkSuppression(**suppression_payload(gate))

    if not gate.allowed:
        return ParentBenchmarksResponse(
            child_id=child.id,
            age_band=child_age_band,
            range_days=range_days,
            pace_benchmark=None,
            engagement_benchmark=None,
            category_benchmarks=[],
            suppression=suppression,
        )

    child_words_mastered = sum((row.words_mastered or 0) for row in child_rows)
    child_session_minutes = sum((row.session_minutes_total or 0) for row in child_rows)
    child_active_days = max(len(child_rows), 1)
    child_pace = child_words_mastered / child_active_days
    child_engagement = child_session_minutes / child_active_days

    cohort_pace_values = [
        stats["words_mastered"] / max(stats["active_days"], 1)
        for stats in cohort_by_child.values()
    ]
    cohort_engagement_values = [
        stats["session_minutes"] / max(stats["active_days"], 1)
        for stats in cohort_by_child.values()
    ]
    cohort_pace = sum(cohort_pace_values) / max(len(cohort_pace_values), 1)
    cohort_engagement = sum(cohort_engagement_values) / max(len(cohort_engagement_values), 1)

    midpoint = start_day + timedelta(days=max(range_days // 2, 1))
    first_half_rows = [row for row in child_rows if row.activity_day < midpoint]
    second_half_rows = [row for row in child_rows if row.activity_day >= midpoint]

    first_half_pace = (
        sum((row.words_mastered or 0) for row in first_half_rows)
        / max(len(first_half_rows), 1)
    )
    second_half_pace = (
        sum((row.words_mastered or 0) for row in second_half_rows)
        / max(len(second_half_rows), 1)
    )
    first_half_engagement = (
        sum((row.session_minutes_total or 0) for row in first_half_rows)
        / max(len(first_half_rows), 1)
    )
    second_half_engagement = (
        sum((row.session_minutes_total or 0) for row in second_half_rows)
        / max(len(second_half_rows), 1)
    )

    pace_band = _benchmark_band(child_pace, cohort_pace)
    engagement_band = _benchmark_band(child_engagement, cohort_engagement)

    pace_benchmark = BenchmarkCard(
        band=pace_band,
        percentile_band=_percentile_band(cohort_pace_values, child_pace),
        trend=_trend_label(first_half_pace, second_half_pace),
        child_value=round(child_pace, 2),
        cohort_value=round(cohort_pace, 2),
        tips=_benchmark_tip("pace", pace_band),
    )
    engagement_benchmark = BenchmarkCard(
        band=engagement_band,
        percentile_band=_percentile_band(cohort_engagement_values, child_engagement),
        trend=_trend_label(first_half_engagement, second_half_engagement),
        child_value=round(child_engagement, 2),
        cohort_value=round(cohort_engagement, 2),
        tips=_benchmark_tip("engagement", engagement_band),
    )

    child_category_rows_result = await db.execute(
        select(
            Word.category,
            func.count(WordProgress.id).label("total_count"),
            func.count(WordProgress.id).filter(WordProgress.mastered.is_(True)).label("mastered_count"),
        )
        .join(Word, WordProgress.word_id == Word.id)
        .where(WordProgress.child_id == child.id, Word.is_active == True)
        .group_by(Word.category)
    )
    child_category_rows = child_category_rows_result.all()

    cohort_peer_ids = [
        cohort_child_id
        for cohort_child_id in cohort_by_child.keys()
        if cohort_child_id != child.id
    ]
    cohort_category_ratios: dict[str, list[float]] = {}
    if cohort_peer_ids:
        cohort_category_rows_result = await db.execute(
            select(
                WordProgress.child_id,
                Word.category,
                func.count(WordProgress.id).label("total_count"),
                func.count(WordProgress.id).filter(WordProgress.mastered.is_(True)).label("mastered_count"),
            )
            .join(Word, WordProgress.word_id == Word.id)
            .where(
                WordProgress.child_id.in_(cohort_peer_ids),
                Word.is_active == True,
            )
            .group_by(WordProgress.child_id, Word.category)
        )

        for peer_row in cohort_category_rows_result.all():
            total_count = peer_row.total_count or 0
            if total_count <= 0:
                continue

            peer_ratio = (peer_row.mastered_count or 0) / total_count
            cohort_category_ratios.setdefault(peer_row.category, []).append(peer_ratio)

    category_name_rows = await db.execute(
        select(Category.id, Category.name_cantonese, Category.name).where(
            Category.id.in_([row.category for row in child_category_rows])
        )
    )
    category_name_map = {
        row.id: (row.name_cantonese or row.name or row.id)
        for row in category_name_rows
    }

    category_benchmarks: list[CategoryBenchmarkCard] = []
    for row in sorted(
        child_category_rows,
        key=lambda item: (item.mastered_count or 0) / max(item.total_count or 1, 1),
        reverse=True,
    )[:3]:
        child_ratio = (row.mastered_count or 0) / max(row.total_count or 1, 1)
        cohort_ratio_values = cohort_category_ratios.get(row.category, [])
        if not cohort_ratio_values:
            continue

        cohort_ratio = sum(cohort_ratio_values) / len(cohort_ratio_values)
        band = _benchmark_band(child_ratio, cohort_ratio)
        category_benchmarks.append(
            CategoryBenchmarkCard(
                category_id=row.category,
                category_name=category_name_map.get(row.category, row.category),
                band=band,
                percentile_band=_percentile_band(cohort_ratio_values, child_ratio),
                trend="flat",
                child_value=round(child_ratio * 100, 1),
                cohort_value=round(cohort_ratio * 100, 1),
                tips=(
                    "可在生活情境加入更多主動開口練習。"
                    if band == "ahead"
                    else "可透過圖片+動作+對話三步驟提升掌握。"
                ),
            )
        )

    return ParentBenchmarksResponse(
        child_id=child.id,
        age_band=child_age_band,
        range_days=range_days,
        pace_benchmark=pace_benchmark,
        engagement_benchmark=engagement_benchmark,
        category_benchmarks=category_benchmarks,
        suppression=suppression,
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
    today = _local_today()
    if period == "week":
        start_date = today - timedelta(days=6)  # 6 days ago + today = 7 days
        num_days = 7
    elif period == "month":
        start_date = today - timedelta(days=30)
        num_days = 30
    else:  # all
        start_date = date(2020, 1, 1)  # Far in the past
        num_days = (today - start_date).days
    start_at, end_at = _local_date_window(start_date, today)
    
    # Use DailyWordTracking table to get accurate word learning dates
    # This table tracks when words were first learned each day
    daily_tracking_result = await db.execute(
        select(DailyWordTracking, Word)
        .join(Word, DailyWordTracking.word_id == Word.id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_at,
                DailyWordTracking.date < end_at,
            )
        )
    )
    tracking_records = daily_tracking_result.all()
    
    # Group by date and category
    date_stats = {}
    category_breakdown = {}
    
    for tracking, word in tracking_records:
        if tracking.date:
            learned_date = _normalize_tracking_day(tracking.date)
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

    _, _, recent_category_activity = await _get_recent_tracking_activity(
        child_id,
        db,
        _local_today() - timedelta(days=6),
    )

    sessions_result = await db.execute(
        select(LearningSession).where(
            and_(
                LearningSession.child_id == child_id,
                LearningSession.start_time < end_at,
                or_(
                    LearningSession.end_time.is_(None),
                    LearningSession.end_time > start_at,
                ),
            )
        )
    )
    session_daily_stats = _summarize_sessions_by_day(
        sessions_result.scalars().all(),
        start_day=start_date,
        end_day=today,
    )
    
    # Create time series arrays - generate a date for each day in range
    dates = []
    words_learned = []
    learning_time = []
    xp_earned = []
    
    current_date = start_date
    while current_date <= today:
        dates.append(str(current_date))
        
        day_stats = date_stats.get(current_date, {'words_learned': set(), 'xp': 0})
        words_count = len(day_stats['words_learned'])
        
        words_learned.append(words_count)
        learning_time.append(
            _rounded_minutes_from_total_seconds(
                float(
                    session_daily_stats.get(current_date, {}).get(
                        "total_seconds",
                        0.0,
                    )
                ),
                has_words=words_count > 0,
            )
        )
        xp_earned.append(words_count * 10)  # 10 XP per word
        
        current_date += timedelta(days=1)

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
            recent_activity = recent_category_activity.get(category.id, 0)
            
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
    total_sessions = 0
    for tracked_day, day_stats in session_daily_stats.items():
        rounded_minutes = _rounded_minutes_from_total_seconds(
            float(day_stats["total_seconds"]),
            has_words=bool(date_stats.get(tracked_day, {}).get("words_learned")),
        )
        if rounded_minutes > 0 or bool(date_stats.get(tracked_day, {}).get("words_learned")):
            total_sessions += int(day_stats["session_count"])
    average_session_length = int(total_time / total_sessions) if total_sessions > 0 else 0
    
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
    
    # Query a narrow window around the requested day, then reuse the same
    # datetime -> day normalization the charts endpoint relies on.
    window_start, window_end = _local_day_bounds(target_date)

    tracking_result = await db.execute(
        select(DailyWordTracking, Word, Category)
        .join(Word, DailyWordTracking.word_id == Word.id)
        .outerjoin(Category, Word.category == Category.id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= window_start,
                DailyWordTracking.date < window_end
            )
        )
        .order_by(DailyWordTracking.created_at.desc())
    )
    records = [
        (tracking, word, category)
        for tracking, word, category in tracking_result.all()
        if _normalize_tracking_day(tracking.date) == target_date
    ]
    
    # Format response
    words_data = []
    seen_word_ids = set()
    for tracking, word, category in records:
        if tracking.word_id in seen_word_ids:
            continue
        seen_word_ids.add(tracking.word_id)

        words_data.append({
            "id": word.id,
            "word": word.word,
            "word_cantonese": word.word_cantonese,
            "jyutping": word.jyutping,
            "image_url": word.image_url,
            "category": category.name if category else (word.category or ""),
            "category_cantonese": category.name_cantonese if category else None,
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

    today = _local_today()
    if await sync_child_metrics(db, child, as_of=today):
        await db.commit()
        await db.refresh(child)

    await _sync_learning_insights(child, db)
    
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
            LearningInsight.is_read.asc(),
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
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    live_report = await _build_live_weekly_report(child, db)
    
    reports_result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.child_id == child_id)
        .order_by(desc(WeeklyReport.week_start_date))
        .limit(limit)
    )
    reports = reports_result.scalars().all()

    historical_reports = [
        WeeklyReportResponse.from_orm(report)
        for report in reports
        if report.week_start_date != live_report.week_start_date
    ]

    return [live_report, *historical_reports][:limit]


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
