"""
Mission endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy import select
from typing import List
from datetime import date, datetime, timedelta, timezone
import uuid

from app.db.session import get_db
from app.core.config import settings
from app.schemas.content import (
    AssignedMissionResponse,
    MissionCreate,
    MissionCompletionHistoryItem,
    ParentMicroMissionCreate,
    MissionProgressResponse,
    MissionProgressUpdate,
    MissionResponse,
    MissionSummaryResponse,
    MissionUpdate,
)
from app.models.content import (
    Mission,
    MissionContext,
    MissionAssignment,
    MissionAssignmentSource,
    MissionAssignmentStatus,
    MissionProgress,
    MissionStatus,
    MissionSurface,
)
from app.models.user import User, Child
from app.core.child_age import calculate_child_age
from app.core.security import get_current_active_user, get_current_admin_user
from app.services.analytics_foundation import (
    AnalyticsEventInput,
    AnalyticsEventType,
    write_analytics_event,
)
from app.services.cluster_mission_service import generate_cluster_mission_draft

router = APIRouter()

MAX_DAILY_ASSIGNMENTS = 3
MAX_OFFLINE_ASSIGNMENTS = 6
MISSION_COMPLETION_COOLDOWN_DAYS = 7
DEFAULT_MISSION_ASSIGNMENT_REPEAT_COOLDOWN_DAYS = (
    settings.DEFAULT_MISSION_ASSIGNMENT_REPEAT_COOLDOWN_DAYS
)
MISSION_DAILY_POINTS = 10
MISSION_OFFLINE_POINTS = 15
MISSION_WEEKLY_GOAL = 5
HKT = timezone(timedelta(hours=8), name="HKT")

MISSION_LEVELS = [
    {"level": 1, "title": "陪跑新手", "min_points": 0},
    {"level": 2, "title": "互動拍檔", "min_points": 50},
    {"level": 3, "title": "共學隊長", "min_points": 120},
    {"level": 4, "title": "語言探險家", "min_points": 220},
    {"level": 5, "title": "家庭共學達人", "min_points": 360},
]


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _current_hkt_date(now_utc: datetime | None = None) -> date:
    resolved_now = _ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
    return resolved_now.astimezone(HKT).date()


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _normalize_string_list(
    values: list[str],
    *,
    max_items: int,
    max_length: int,
) -> list[str]:
    normalized: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        if cleaned in normalized:
            continue
        normalized.append(cleaned)
        if len(normalized) >= max_items:
            break
    return normalized


async def _get_mission_by_id(mission_id: str, db: AsyncSession) -> Mission:
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found",
        )
    return mission


async def _ensure_unique_slug(
    slug: str,
    db: AsyncSession,
    *,
    exclude_mission_id: str | None = None,
) -> None:
    slug_query = select(Mission).where(Mission.slug == slug)
    if exclude_mission_id:
        slug_query = slug_query.where(Mission.id != exclude_mission_id)

    existing_result = await db.execute(slug_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mission slug already exists",
        )


def _apply_mission_lifecycle_defaults(
    mission: Mission,
    *,
    previous_status: MissionStatus | None = None,
) -> None:
    now = datetime.now(timezone.utc)

    if mission.status == MissionStatus.PUBLISHED:
        if mission.published_at is None:
            mission.published_at = now
        mission.archived_at = None
    elif mission.status == MissionStatus.ARCHIVED:
        if mission.archived_at is None:
            mission.archived_at = now
    elif previous_status == MissionStatus.ARCHIVED:
        mission.archived_at = None


@router.get("/admin/catalog", response_model=List[MissionResponse])
async def list_admin_missions(
    include_inactive: bool = True,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List mission catalog entries for admin management."""
    mission_query = select(Mission)
    if not include_inactive:
        mission_query = mission_query.where(Mission.is_active == True)

    result = await db.execute(
        mission_query.order_by(Mission.sort_order.asc(), Mission.created_at.desc())
    )
    return result.scalars().all()


@router.post("/admin/catalog", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_mission(
    mission_data: MissionCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a mission catalog entry."""
    await _ensure_unique_slug(mission_data.slug, db)

    mission = Mission(
        id=str(uuid.uuid4()),
        slug=mission_data.slug,
        title=mission_data.title,
        description=mission_data.description,
        context=mission_data.context,
        is_offline=mission_data.is_offline,
        status=mission_data.status,
        locale=mission_data.locale,
        age_min=mission_data.age_min,
        age_max=mission_data.age_max,
        difficulty=mission_data.difficulty,
        surface=mission_data.surface,
        sort_order=mission_data.sort_order,
        selection_tags=mission_data.selection_tags,
        catalog_metadata=mission_data.catalog_metadata,
        published_at=mission_data.published_at,
        archived_at=mission_data.archived_at,
        target_words=mission_data.target_words,
        conversation_prompts=mission_data.conversation_prompts,
    )
    mission.assignment_repeat_cooldown_days = mission_data.assignment_repeat_cooldown_days
    _apply_mission_lifecycle_defaults(mission)

    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.patch("/admin/catalog/{mission_id}", response_model=MissionResponse)
async def update_admin_mission(
    mission_id: str,
    mission_data: MissionUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a mission catalog entry."""
    mission = await _get_mission_by_id(mission_id, db)
    update_data = mission_data.dict(exclude_unset=True)

    if "slug" in update_data:
        await _ensure_unique_slug(update_data["slug"], db, exclude_mission_id=mission_id)

    previous_status = mission.status
    for field, value in update_data.items():
        setattr(mission, field, value)

    _apply_mission_lifecycle_defaults(mission, previous_status=previous_status)

    await db.commit()
    await db.refresh(mission)
    return mission


async def _ensure_child_belongs_to_user(
    child_id: str,
    current_user: User,
    db: AsyncSession,
) -> Child:
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found",
        )
    return child


async def _get_progress_map(
    child_id: str,
    db: AsyncSession,
) -> dict[str, MissionProgress]:
    result = await db.execute(
        select(MissionProgress).where(MissionProgress.child_id == child_id)
    )
    return {progress.mission_id: progress for progress in result.scalars().all()}


def _serialize_assigned_mission(
    mission: Mission,
    child_id: str,
    assignment_date: date,
    assignment: MissionAssignment | None = None,
    progress: MissionProgress | None = None,
) -> dict:
    if assignment:
        assignment_status = assignment.status
        completed_at = assignment.completed_at
        completion_notes = assignment.completion_notes
    else:
        assignment_status = MissionAssignmentStatus.ASSIGNED
        completed_at = None
        completion_notes = None

        if progress and progress.completed:
            assignment_status = MissionAssignmentStatus.COMPLETED
            completed_at = progress.completed_date
            completion_notes = progress.parent_notes

    assignment_payload = {
        "id": assignment.id if assignment else f"{mission.id}:{assignment_date.isoformat()}",
        "child_id": child_id,
        "mission_id": mission.id,
        "assignment_date": assignment.assignment_date if assignment else assignment_date,
        "source": assignment.source if assignment else MissionAssignmentSource.SEED,
        "status": assignment_status,
        "surface": assignment.surface if assignment else mission.surface,
        "priority": assignment.priority if assignment else mission.sort_order,
        "selection_reason": assignment.selection_reason if assignment else None,
        "selection_metadata": assignment.selection_metadata if assignment else None,
        "available_from": assignment.available_from if assignment else None,
        "expires_at": assignment.expires_at if assignment else None,
        "started_at": assignment.started_at if assignment else None,
        "completed_at": completed_at,
        "skipped_at": assignment.skipped_at if assignment else None,
        "completion_notes": completion_notes,
        "created_at": assignment.created_at if assignment else mission.created_at,
        "updated_at": assignment.updated_at if assignment else mission.updated_at,
    }

    return {
        "id": mission.id,
        "slug": mission.slug,
        "title": mission.title,
        "description": mission.description,
        "context": mission.context,
        "is_offline": mission.is_offline,
        "status": mission.status,
        "locale": mission.locale,
        "age_min": mission.age_min,
        "age_max": mission.age_max,
        "difficulty": mission.difficulty,
        "surface": mission.surface,
        "sort_order": mission.sort_order,
        "selection_tags": mission.selection_tags or [],
        "catalog_metadata": mission.catalog_metadata,
        "published_at": mission.published_at,
        "archived_at": mission.archived_at,
        "target_words": mission.target_words or [],
        "conversation_prompts": mission.conversation_prompts or [],
        "is_active": mission.is_active,
        "created_at": mission.created_at,
        "updated_at": mission.updated_at,
        "assignment": assignment_payload,
    }


def _select_missions_for_assignment(
    missions: list[Mission],
    *,
    limit: int,
) -> list[Mission]:
    if len(missions) <= limit:
        return missions

    selected: list[Mission] = []
    seen_contexts: set = set()

    for mission in missions:
        if mission.context in seen_contexts:
            continue
        selected.append(mission)
        seen_contexts.add(mission.context)
        if len(selected) == limit:
            return selected

    for mission in missions:
        if mission in selected:
            continue
        selected.append(mission)
        if len(selected) == limit:
            break

    return selected


def _dedupe_missions_by_id(missions: list[Mission]) -> list[Mission]:
    deduped: list[Mission] = []
    seen_ids: set[str] = set()

    for mission in missions:
        if mission.id in seen_ids:
            continue
        seen_ids.add(mission.id)
        deduped.append(mission)

    return deduped


def _is_generated_cluster_mission(mission: Mission) -> bool:
    metadata = mission.catalog_metadata or {}
    tags = mission.selection_tags or []
    if metadata.get("cluster_id"):
        return True
    return "concept_cluster" in tags and "graph_generated" in tags


def _exclude_generated_cluster_missions(missions: list[Mission]) -> list[Mission]:
    return [mission for mission in missions if not _is_generated_cluster_mission(mission)]


def _mission_created_at_sort_value(mission: Mission) -> datetime:
    if mission.created_at is None:
        return datetime.min
    if mission.created_at.tzinfo is not None:
        return mission.created_at.replace(tzinfo=None)
    return mission.created_at


def _mission_points(is_offline: bool) -> int:
    return MISSION_OFFLINE_POINTS if is_offline else MISSION_DAILY_POINTS


def _resolve_mission_level(points: int) -> tuple[dict, dict | None]:
    current_level = MISSION_LEVELS[0]

    for level in MISSION_LEVELS:
        if points >= level["min_points"]:
            current_level = level
        else:
            return current_level, level

    return current_level, None


def _weekly_goal_label(completed_this_week: int) -> str:
    if completed_this_week >= MISSION_WEEKLY_GOAL:
        return "本週共學目標已達成，繼續累積家庭星星吧。"

    remaining = MISSION_WEEKLY_GOAL - completed_this_week
    return f"再完成 {remaining} 個任務，即可達成本週共學目標。"


def _encouragement_message(
    *,
    streak_days: int,
    total_completed: int,
    points_to_next_level: int,
    next_level: dict | None,
) -> str:
    if total_completed == 0:
        return "完成第一個任務即可開始累積家庭星星，建立親子共學節奏。"

    if streak_days >= 7:
        return f"已連續陪孩子完成 {streak_days} 天任務，這種穩定陪伴最有助把詞語帶進日常生活。"

    if next_level and points_to_next_level > 0:
        return f"距離「{next_level['title']}」還差 {points_to_next_level} 顆家庭星星。"

    return "今天繼續完成一個任務，讓孩子把新詞語說進真實情境。"


def _build_mission_summary_payload(
    *,
    child_id: str,
    local_today: date,
    completed_rows: list[tuple[MissionAssignment, Mission]],
) -> dict:
    completed_dates = {
        assignment.assignment_date
        for assignment, _ in completed_rows
        if assignment.assignment_date is not None
    }

    streak_days = 0
    streak_cursor = local_today
    while streak_cursor in completed_dates:
        streak_days += 1
        streak_cursor -= timedelta(days=1)

    week_start = local_today - timedelta(days=local_today.weekday())
    completed_today = sum(
        1
        for assignment, _ in completed_rows
        if assignment.assignment_date == local_today
    )
    completed_this_week = sum(
        1
        for assignment, _ in completed_rows
        if week_start <= assignment.assignment_date <= local_today
    )
    family_points = sum(
        _mission_points(mission.is_offline)
        for _, mission in completed_rows
    )
    total_completed = len(completed_rows)

    current_level, next_level = _resolve_mission_level(family_points)
    next_level_points = (
        next_level["min_points"] if next_level else current_level["min_points"]
    )
    points_to_next_level = max(next_level_points - family_points, 0)

    recent_completions = [
        MissionCompletionHistoryItem(
            mission_id=mission.id,
            title=mission.title,
            context=_enum_value(mission.context),
            is_offline=mission.is_offline,
            surface=_enum_value(assignment.surface),
            assignment_date=assignment.assignment_date,
            completed_at=assignment.completed_at,
            completion_notes=assignment.completion_notes,
            target_words=mission.target_words or [],
            points_earned=_mission_points(mission.is_offline),
        )
        for assignment, mission in completed_rows[:6]
    ]

    return MissionSummaryResponse(
        child_id=child_id,
        local_today=local_today,
        completed_today=completed_today,
        completed_this_week=completed_this_week,
        weekly_goal=MISSION_WEEKLY_GOAL,
        streak_days=streak_days,
        total_completed=total_completed,
        family_points=family_points,
        level=current_level["level"],
        level_title=current_level["title"],
        next_level_points=next_level_points,
        points_to_next_level=points_to_next_level,
        next_reward_label=_weekly_goal_label(completed_this_week),
        encouragement=_encouragement_message(
            streak_days=streak_days,
            total_completed=total_completed,
            points_to_next_level=points_to_next_level,
            next_level=next_level,
        ),
        recent_completions=recent_completions,
    ).model_dump()


def _was_completed_recently(
    completed_at: datetime | None,
    *,
    assignment_date: date,
) -> bool:
    if completed_at is None:
        return False

    completed_local_date = _ensure_utc(completed_at).astimezone(HKT).date()
    return (
        assignment_date - completed_local_date
    ).days < MISSION_COMPLETION_COOLDOWN_DAYS


def _was_assigned_recently(
    last_assignment_date: date | None,
    *,
    assignment_date: date,
    repeat_cooldown_days: int = DEFAULT_MISSION_ASSIGNMENT_REPEAT_COOLDOWN_DAYS,
) -> bool:
    if last_assignment_date is None:
        return False

    return (
        assignment_date - last_assignment_date
    ).days < repeat_cooldown_days


def _resolve_assignment_repeat_cooldown_days(mission: Mission | None) -> int:
    if mission:
        mission_cooldown = getattr(mission, "assignment_repeat_cooldown_days", None)
        if mission_cooldown is not None:
            return int(mission_cooldown)

        mission_metadata = getattr(mission, "catalog_metadata", None) or {}
        metadata_cooldown = mission_metadata.get("assignment_repeat_cooldown_days")
        if metadata_cooldown is not None:
            return int(metadata_cooldown)
    return DEFAULT_MISSION_ASSIGNMENT_REPEAT_COOLDOWN_DAYS


def _filter_daily_rotation_candidates(
    missions: list[Mission],
    *,
    assignment_history: dict[str, tuple[date | None, datetime | None]],
    assignment_date: date,
) -> list[Mission]:
    return [
        mission
        for mission in missions
        if not _was_assigned_recently(
            assignment_history.get(mission.id, (None, None))[0],
            assignment_date=assignment_date,
            repeat_cooldown_days=_resolve_assignment_repeat_cooldown_days(mission),
        )
    ]


async def _get_assignment_history(
    *,
    child_id: str,
    mission_ids: list[str],
    assignment_date: date,
    db: AsyncSession,
) -> dict[str, tuple[date | None, datetime | None]]:
    if not mission_ids:
        return {}

    history_result = await db.execute(
        select(
            MissionAssignment.mission_id,
            sa.func.max(MissionAssignment.assignment_date).label(
                "last_assignment_date"
            ),
            sa.func.max(MissionAssignment.completed_at).label("last_completed_at"),
        )
        .where(
            MissionAssignment.child_id == child_id,
            MissionAssignment.mission_id.in_(mission_ids),
            MissionAssignment.assignment_date < assignment_date,
        )
        .group_by(MissionAssignment.mission_id)
    )

    return {
        row.mission_id: (row.last_assignment_date, row.last_completed_at)
        for row in history_result
    }


def _rank_candidate_missions(
    missions: list[Mission],
    *,
    assignment_history: dict[str, tuple[date | None, datetime | None]],
    assignment_date: date,
) -> list[Mission]:
    def mission_sort_key(mission: Mission) -> tuple:
        last_assignment_date, last_completed_at = assignment_history.get(
            mission.id,
            (None, None),
        )
        recently_completed = _was_completed_recently(
            last_completed_at,
            assignment_date=assignment_date,
        )

        return (
            recently_completed,
            last_assignment_date is not None,
            last_assignment_date or date.min,
            mission.sort_order if mission.sort_order is not None else 0,
            _mission_created_at_sort_value(mission),
            mission.id,
        )

    return sorted(missions, key=mission_sort_key)


async def _generate_assignments_for_date(
    *,
    child: Child,
    assignment_date: date,
    is_offline: bool,
    surfaces: list[MissionSurface],
    db: AsyncSession,
) -> None:
    child_age = calculate_child_age(
        stored_age=child.age,
        birth_year=child.birth_year,
        birth_month=child.birth_month,
        as_of=assignment_date,
    )

    catalog_result = await db.execute(
        select(Mission)
        .where(
            Mission.is_offline == is_offline,
            Mission.status == MissionStatus.PUBLISHED,
            Mission.is_active == True,
            Mission.surface.in_(surfaces),
            sa.or_(Mission.age_min.is_(None), Mission.age_min <= child_age),
            sa.or_(Mission.age_max.is_(None), Mission.age_max >= child_age),
        )
        .order_by(Mission.sort_order.asc(), Mission.created_at.asc())
    )
    candidate_missions = _exclude_generated_cluster_missions(
        catalog_result.scalars().all()
    )
    assignment_history = await _get_assignment_history(
        child_id=child.id,
        mission_ids=[mission.id for mission in candidate_missions],
        assignment_date=assignment_date,
        db=db,
    )
    ranked_missions = _rank_candidate_missions(
        candidate_missions,
        assignment_history=assignment_history,
        assignment_date=assignment_date,
    )
    eligible_missions = (
        _filter_daily_rotation_candidates(
            ranked_missions,
            assignment_history=assignment_history,
            assignment_date=assignment_date,
        )
        if not is_offline
        else ranked_missions
    )
    assignment_limit = MAX_OFFLINE_ASSIGNMENTS if is_offline else MAX_DAILY_ASSIGNMENTS
    selected_missions = _select_missions_for_assignment(
        eligible_missions,
        limit=assignment_limit,
    )

    if not is_offline and assignment_limit > 0:
        cluster_draft = await generate_cluster_mission_draft(
            db,
            child_id=child.id,
            assignment_date=assignment_date,
        )
        if cluster_draft:
            cluster_slug = (
                f"cluster-{child.id[:8]}-{assignment_date.strftime('%Y%m%d')}-{cluster_draft.seed_word_id[:8]}"
            )
            cluster_metadata = {
                "cluster_id": cluster_draft.cluster_id,
                "seed_word_id": cluster_draft.seed_word_id,
                "cluster_depth": cluster_draft.cluster_depth,
                "cluster_strategy": cluster_draft.cluster_strategy,
                "cluster_theme_label": cluster_draft.theme_label,
                "cluster_related_theme_labels": cluster_draft.related_theme_labels,
                "target_word_ids": cluster_draft.target_word_ids,
                "target_words_display": cluster_draft.target_words_display,
                "generated_for_child_id": child.id,
                "generated_local_date": assignment_date.isoformat(),
            }

            existing_cluster_result = await db.execute(
                select(Mission).where(Mission.slug == cluster_slug)
            )
            cluster_mission = existing_cluster_result.scalar_one_or_none()

            if cluster_mission:
                # Reuse deterministic cluster slug and refresh mission content so
                # retries remain idempotent and avoid unique-slug collisions.
                cluster_mission.title = cluster_draft.title
                cluster_mission.description = cluster_draft.description
                cluster_mission.context = MissionContext(cluster_draft.context)
                cluster_mission.target_words = cluster_draft.target_words_display
                cluster_mission.conversation_prompts = cluster_draft.conversation_prompts
                cluster_mission.selection_tags = ["concept_cluster", "graph_generated"]
                cluster_mission.is_offline = False
                cluster_mission.status = MissionStatus.PUBLISHED
                cluster_mission.locale = "zh-HK"
                cluster_mission.age_min = max(child_age - 1, 2)
                cluster_mission.age_max = child_age + 1
                cluster_mission.surface = MissionSurface.CHILD
                cluster_mission.sort_order = 0
                cluster_mission.is_active = True
                cluster_mission.catalog_metadata = cluster_metadata
            else:
                cluster_mission = Mission(
                    id=str(uuid.uuid4()),
                    slug=cluster_slug,
                    title=cluster_draft.title,
                    description=cluster_draft.description,
                    context=MissionContext(cluster_draft.context),
                    target_words=cluster_draft.target_words_display,
                    conversation_prompts=cluster_draft.conversation_prompts,
                    selection_tags=["concept_cluster", "graph_generated"],
                    is_offline=False,
                    status=MissionStatus.PUBLISHED,
                    locale="zh-HK",
                    age_min=max(child_age - 1, 2),
                    age_max=child_age + 1,
                    surface=MissionSurface.CHILD,
                    sort_order=0,
                    is_active=True,
                    catalog_metadata=cluster_metadata,
                )
                _apply_mission_lifecycle_defaults(cluster_mission)
                db.add(cluster_mission)

            remainder = _select_missions_for_assignment(
                eligible_missions,
                limit=max(assignment_limit - 1, 0),
            )
            selected_missions = _dedupe_missions_by_id(
                [cluster_mission] + remainder
            )[:assignment_limit]

    selected_missions = _dedupe_missions_by_id(selected_missions)[:assignment_limit]

    if not selected_missions:
        return

    created_assignments: list[tuple[MissionAssignment, Mission]] = []

    for index, mission in enumerate(selected_missions, start=1):
        last_assignment_date, last_completed_at = assignment_history.get(
            mission.id,
            (None, None),
        )
        mission_metadata = mission.catalog_metadata or {}
        is_cluster = bool(mission_metadata.get("cluster_id"))
        assignment = MissionAssignment(
            id=str(uuid.uuid4()),
            child_id=child.id,
            mission_id=mission.id,
            assignment_date=assignment_date,
            source=MissionAssignmentSource.SYSTEM,
            status=MissionAssignmentStatus.ASSIGNED,
            surface=mission.surface,
            priority=index,
            selection_reason=(
                "Graph concept cluster mission"
                if is_cluster
                else (
                    "Rotated from published offline mission catalog"
                    if is_offline
                    else "Rotated from published daily mission catalog"
                )
            ),
            selection_metadata={
                "catalog_sort_order": mission.sort_order,
                "context": mission.context.value,
                "is_offline": is_offline,
                "last_assignment_date": (
                    last_assignment_date.isoformat()
                    if last_assignment_date
                    else None
                ),
                "last_completed_at": (
                    last_completed_at.isoformat()
                    if last_completed_at
                    else None
                ),
                "last_assignment_date_was_recent": _was_assigned_recently(
                    last_assignment_date,
                    assignment_date=assignment_date,
                    repeat_cooldown_days=_resolve_assignment_repeat_cooldown_days(
                        mission
                    ),
                ),
                "assignment_repeat_cooldown_days": (
                    _resolve_assignment_repeat_cooldown_days(mission)
                    if not is_offline
                    else None
                ),
                "completion_cooldown_days": MISSION_COMPLETION_COOLDOWN_DAYS,
                "deferred_recent_completion": _was_completed_recently(
                    last_completed_at,
                    assignment_date=assignment_date,
                ),
                "is_cluster": is_cluster,
                "cluster_id": mission_metadata.get("cluster_id"),
                "seed_word_id": mission_metadata.get("seed_word_id"),
                "cluster_depth": mission_metadata.get("cluster_depth"),
                "cluster_strategy": mission_metadata.get("cluster_strategy"),
                "cluster_theme_label": mission_metadata.get("cluster_theme_label"),
                "cluster_related_theme_labels": mission_metadata.get("cluster_related_theme_labels"),
                "target_words_display": mission_metadata.get("target_words_display"),
            },
        )
        db.add(assignment)
        created_assignments.append((assignment, mission))

    await db.commit()

    for assignment, mission in created_assignments:
        await write_analytics_event(
            db,
            AnalyticsEventInput(
                event_type=AnalyticsEventType.MISSION_ASSIGNED,
                child_id=assignment.child_id,
                mission_id=assignment.mission_id,
                occurred_at=datetime.combine(
                    assignment.assignment_date,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
                source="api.missions._generate_assignments_for_date",
                idempotency_key=f"mission-assigned:{assignment.id}",
                payload={
                    "assignment_id": assignment.id,
                    "context": mission.context.value,
                    "is_offline": mission.is_offline,
                    "is_cluster": bool((assignment.selection_metadata or {}).get("is_cluster", False)),
                    "cluster_id": (assignment.selection_metadata or {}).get("cluster_id"),
                    "seed_word_id": (assignment.selection_metadata or {}).get("seed_word_id"),
                },
            ),
        )


async def _get_assigned_or_catalog_missions(
    *,
    child: Child,
    assignment_date: date,
    is_offline: bool,
    surfaces: list[MissionSurface],
    db: AsyncSession,
) -> list[dict]:
    assigned_result = await db.execute(
        select(MissionAssignment, Mission)
        .join(Mission, MissionAssignment.mission_id == Mission.id)
        .where(
            MissionAssignment.child_id == child.id,
            MissionAssignment.assignment_date == assignment_date,
            Mission.is_offline == is_offline,
            Mission.status == MissionStatus.PUBLISHED,
            Mission.is_active == True,
            Mission.surface.in_(surfaces),
        )
        .order_by(MissionAssignment.priority.asc(), Mission.sort_order.asc())
    )
    assigned_rows = assigned_result.all()
    progress_map = await _get_progress_map(child.id, db)

    if not assigned_rows:
        await _generate_assignments_for_date(
            child=child,
            assignment_date=assignment_date,
            is_offline=is_offline,
            surfaces=surfaces,
            db=db,
        )
        assigned_result = await db.execute(
            select(MissionAssignment, Mission)
            .join(Mission, MissionAssignment.mission_id == Mission.id)
            .where(
                MissionAssignment.child_id == child.id,
                MissionAssignment.assignment_date == assignment_date,
                Mission.is_offline == is_offline,
                Mission.status == MissionStatus.PUBLISHED,
                Mission.is_active == True,
                Mission.surface.in_(surfaces),
            )
            .order_by(MissionAssignment.priority.asc(), Mission.sort_order.asc())
        )
        assigned_rows = assigned_result.all()

    if assigned_rows:
        return [
            _serialize_assigned_mission(
                mission=mission,
                child_id=child.id,
                assignment_date=assignment_date,
                assignment=assignment,
                progress=progress_map.get(mission.id),
            )
            for assignment, mission in assigned_rows
        ]

    return []


@router.get("/daily/{child_id}", response_model=List[AssignedMissionResponse])
async def get_daily_missions(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get today's missions for a child"""
    child = await _ensure_child_belongs_to_user(child_id, current_user, db)

    return await _get_assigned_or_catalog_missions(
        child=child,
        assignment_date=_current_hkt_date(),
        is_offline=False,
        surfaces=[MissionSurface.CHILD, MissionSurface.BOTH],
        db=db,
    )


@router.get("/offline/{child_id}", response_model=List[AssignedMissionResponse])
async def get_offline_missions(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get offline missions for a child"""
    child = await _ensure_child_belongs_to_user(child_id, current_user, db)

    return await _get_assigned_or_catalog_missions(
        child=child,
        assignment_date=_current_hkt_date(),
        is_offline=True,
        surfaces=[MissionSurface.PARENT, MissionSurface.BOTH],
        db=db,
    )


@router.post(
    "/parent/{child_id}/micro",
    response_model=AssignedMissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_parent_micro_mission(
    child_id: str,
    payload: ParentMicroMissionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a short parent-authored mission and assign it for today's child mode."""
    child = await _ensure_child_belongs_to_user(child_id, current_user, db)
    assignment_date = _current_hkt_date()

    target_words = _normalize_string_list(
        payload.target_words,
        max_items=8,
        max_length=24,
    )
    prompts = _normalize_string_list(
        payload.conversation_prompts,
        max_items=4,
        max_length=120,
    )

    priority_result = await db.execute(
        select(sa.func.min(MissionAssignment.priority)).where(
            MissionAssignment.child_id == child.id,
            MissionAssignment.assignment_date == assignment_date,
        )
    )
    current_min_priority = priority_result.scalar_one_or_none()
    priority = max((current_min_priority if current_min_priority is not None else 1) - 1, 0)

    mission_id = str(uuid.uuid4())
    slug = f"parent-micro-{child.id[:8]}-{assignment_date.strftime('%Y%m%d')}-{mission_id[:8]}"

    mission = Mission(
        id=mission_id,
        slug=slug,
        title=payload.title.strip(),
        description=payload.description.strip(),
        context=payload.context,
        target_words=target_words,
        conversation_prompts=prompts,
        selection_tags=["parent_authored", "micro_mission"],
        is_offline=True,
        status=MissionStatus.PUBLISHED,
        locale="zh-HK",
        surface=MissionSurface.BOTH,
        sort_order=0,
        is_active=True,
        catalog_metadata={
            "author_type": "parent",
            "author_user_id": current_user.id,
            "child_id": child.id,
            "micro_mission": True,
            "created_local_date": assignment_date.isoformat(),
            "delivery": "child_mode_direct",
            "context": payload.context.value if isinstance(payload.context, MissionContext) else str(payload.context),
        },
    )
    _apply_mission_lifecycle_defaults(mission)
    db.add(mission)

    assignment = MissionAssignment(
        id=str(uuid.uuid4()),
        child_id=child.id,
        mission_id=mission.id,
        assignment_date=assignment_date,
        source=MissionAssignmentSource.PARENT,
        status=MissionAssignmentStatus.ASSIGNED,
        surface=MissionSurface.BOTH,
        priority=priority,
        selection_reason="Parent-authored micro-mission delivered to child mode",
        selection_metadata={
            "parent_authored": True,
            "micro_mission": True,
            "delivery": "child_mode_direct",
        },
    )
    db.add(assignment)

    await db.commit()
    await db.refresh(mission)
    await db.refresh(assignment)

    await write_analytics_event(
        db,
        AnalyticsEventInput(
            event_type=AnalyticsEventType.MISSION_ASSIGNED,
            child_id=assignment.child_id,
            parent_id=current_user.id,
            mission_id=assignment.mission_id,
            occurred_at=datetime.combine(
                assignment.assignment_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
            source="api.missions.create_parent_micro_mission",
            idempotency_key=f"mission-assigned:{assignment.id}",
            payload={
                "assignment_id": assignment.id,
                "context": mission.context.value,
                "is_offline": mission.is_offline,
                "source": "parent",
                "is_cluster": False,
            },
        ),
    )

    return _serialize_assigned_mission(
        mission=mission,
        child_id=child.id,
        assignment_date=assignment_date,
        assignment=assignment,
    )


@router.get("/{child_id}/summary", response_model=MissionSummaryResponse)
async def get_mission_summary(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get mission completion history and derived incentive summary for a child."""
    child = await _ensure_child_belongs_to_user(child_id, current_user, db)
    local_today = _current_hkt_date()

    completed_result = await db.execute(
        select(MissionAssignment, Mission)
        .join(Mission, MissionAssignment.mission_id == Mission.id)
        .where(
            MissionAssignment.child_id == child.id,
            MissionAssignment.status == MissionAssignmentStatus.COMPLETED,
            MissionAssignment.completed_at.is_not(None),
        )
        .order_by(
            MissionAssignment.assignment_date.desc(),
            MissionAssignment.completed_at.desc(),
            Mission.title.asc(),
        )
    )
    completed_rows = completed_result.all()

    return _build_mission_summary_payload(
        child_id=child.id,
        local_today=local_today,
        completed_rows=completed_rows,
    )


@router.post("/{mission_id}/complete/{child_id}", response_model=MissionProgressResponse)
async def complete_mission(
    mission_id: str,
    child_id: str,
    progress_data: MissionProgressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark mission as complete"""
    await _ensure_child_belongs_to_user(child_id, current_user, db)

    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found",
        )

    # Get or create mission progress
    result = await db.execute(
        select(MissionProgress).where(
            MissionProgress.child_id == child_id,
            MissionProgress.mission_id == mission_id
        )
    )
    progress = result.scalar_one_or_none()
    
    if not progress:
        progress = MissionProgress(
            child_id=child_id,
            mission_id=mission_id
        )
        db.add(progress)

    now = datetime.now(timezone.utc)
    progress.completed = progress_data.completed
    progress.parent_notes = progress_data.parent_notes
    progress.completed_date = now if progress_data.completed else None

    assignment_date = _current_hkt_date(now)
    assignment_result = await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.child_id == child_id,
            MissionAssignment.mission_id == mission_id,
            MissionAssignment.assignment_date == assignment_date,
        )
    )
    assignment = assignment_result.scalar_one_or_none()
    if not assignment:
        assignment = MissionAssignment(
            id=str(uuid.uuid4()),
            child_id=child_id,
            mission_id=mission_id,
            assignment_date=assignment_date,
            source=MissionAssignmentSource.SEED,
            surface=mission.surface,
            priority=mission.sort_order,
        )
        db.add(assignment)

    assignment.status = (
        MissionAssignmentStatus.COMPLETED
        if progress_data.completed
        else MissionAssignmentStatus.ASSIGNED
    )
    assignment.completed_at = now if progress_data.completed else None
    assignment.skipped_at = None
    assignment.completion_notes = progress_data.parent_notes

    if progress_data.completed:
        assignment.started_at = assignment.started_at or now
    
    await db.commit()
    await db.refresh(progress)

    event_type = (
        AnalyticsEventType.MISSION_COMPLETED
        if progress_data.completed
        else AnalyticsEventType.MISSION_ASSIGNED
    )
    key_prefix = "mission-completed" if progress_data.completed else "mission-assigned"
    await write_analytics_event(
        db,
        AnalyticsEventInput(
            event_type=event_type,
            child_id=child_id,
            parent_id=current_user.id,
            mission_id=mission_id,
            occurred_at=now,
            source="api.missions.complete_mission",
            idempotency_key=f"{key_prefix}:{assignment.id}:{int(progress_data.completed)}",
            payload={
                "assignment_id": assignment.id,
                "context": mission.context.value,
                "is_offline": mission.is_offline,
                "completion_minutes": None,
                "is_cluster": bool((assignment.selection_metadata or {}).get("is_cluster", False)),
                "cluster_id": (assignment.selection_metadata or {}).get("cluster_id"),
                "seed_word_id": (assignment.selection_metadata or {}).get("seed_word_id"),
            },
        ),
    )

    return progress
