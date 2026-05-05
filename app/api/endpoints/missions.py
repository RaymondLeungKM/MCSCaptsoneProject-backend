"""
Mission endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy import select
from typing import List
from datetime import date, datetime
import uuid

from app.db.session import get_db
from app.schemas.content import (
    AssignedMissionResponse,
    MissionCreate,
    MissionProgressResponse,
    MissionProgressUpdate,
    MissionResponse,
    MissionUpdate,
)
from app.models.content import (
    Mission,
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

router = APIRouter()

MAX_DAILY_ASSIGNMENTS = 3
MAX_OFFLINE_ASSIGNMENTS = 6


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
    now = datetime.utcnow()

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
    assignment_status = (
        assignment.status if assignment else MissionAssignmentStatus.ASSIGNED
    )
    if progress and progress.completed:
        assignment_status = MissionAssignmentStatus.COMPLETED

    completed_at = assignment.completed_at if assignment else None
    if progress and progress.completed_date:
        completed_at = progress.completed_date

    completion_notes = assignment.completion_notes if assignment else None
    if progress and progress.parent_notes:
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
    candidate_missions = catalog_result.scalars().all()
    selected_missions = _select_missions_for_assignment(
        candidate_missions,
        limit=MAX_OFFLINE_ASSIGNMENTS if is_offline else MAX_DAILY_ASSIGNMENTS,
    )

    if not selected_missions:
        return

    for index, mission in enumerate(selected_missions, start=1):
        db.add(
            MissionAssignment(
                id=str(uuid.uuid4()),
                child_id=child.id,
                mission_id=mission.id,
                assignment_date=assignment_date,
                source=MissionAssignmentSource.SYSTEM,
                status=MissionAssignmentStatus.ASSIGNED,
                surface=mission.surface,
                priority=index,
                selection_reason=(
                    "Generated from published offline mission catalog"
                    if is_offline
                    else "Generated from published daily mission catalog"
                ),
                selection_metadata={
                    "catalog_sort_order": mission.sort_order,
                    "context": mission.context.value,
                    "is_offline": is_offline,
                },
            )
        )

    await db.commit()


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
        assignment_date=datetime.utcnow().date(),
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
        assignment_date=datetime.utcnow().date(),
        is_offline=True,
        surfaces=[MissionSurface.PARENT, MissionSurface.BOTH],
        db=db,
    )


@router.post("/{mission_id}/complete/{child_id}")
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

    now = datetime.utcnow()
    progress.completed = progress_data.completed
    progress.parent_notes = progress_data.parent_notes
    progress.completed_date = now if progress_data.completed else None

    assignment_date = now.date()
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
    
    return progress


@router.get("/{child_id}/progress", response_model=List[MissionProgressResponse])
async def get_mission_progress(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get child's mission completion history"""
    await _ensure_child_belongs_to_user(child_id, current_user, db)

    result = await db.execute(
        select(MissionProgress).where(MissionProgress.child_id == child_id)
    )
    progress_list = result.scalars().all()
    
    return progress_list
