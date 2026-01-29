"""
Mission endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime

from app.db.session import get_db
from app.schemas.content import MissionResponse, MissionProgressResponse, MissionProgressUpdate
from app.models.content import Mission, MissionProgress
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/daily/{child_id}", response_model=List[MissionResponse])
async def get_daily_missions(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get today's missions for a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get daily missions (not offline)
    result = await db.execute(
        select(Mission).where(Mission.is_offline == False, Mission.is_active == True)
    )
    missions = result.scalars().all()
    
    return missions


@router.get("/offline/{child_id}", response_model=List[MissionResponse])
async def get_offline_missions(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get offline missions for a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get offline missions
    result = await db.execute(
        select(Mission).where(Mission.is_offline == True, Mission.is_active == True)
    )
    missions = result.scalars().all()
    
    return missions


@router.post("/{mission_id}/complete/{child_id}")
async def complete_mission(
    mission_id: str,
    child_id: str,
    progress_data: MissionProgressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark mission as complete"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
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
    
    progress.completed = progress_data.completed
    progress.parent_notes = progress_data.parent_notes
    
    if progress_data.completed:
        progress.completed_date = datetime.utcnow()
    
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
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    result = await db.execute(
        select(MissionProgress).where(MissionProgress.child_id == child_id)
    )
    progress_list = result.scalars().all()
    
    return progress_list
