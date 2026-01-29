"""
Analytics endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timedelta

from app.db.session import get_db
from app.schemas.analytics import DailyStatsResponse, ChildAchievementResponse
from app.models.analytics import DailyStats, ChildAchievement, Achievement
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/{child_id}/daily", response_model=List[DailyStatsResponse])
async def get_daily_stats(
    child_id: str,
    days: int = 7,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get daily statistics for a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get stats for last N days
    start_date = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(DailyStats).where(
            DailyStats.child_id == child_id,
            DailyStats.date >= start_date
        ).order_by(DailyStats.date.desc())
    )
    stats = result.scalars().all()
    
    return stats


@router.get("/{child_id}/achievements", response_model=List[ChildAchievementResponse])
async def get_child_achievements(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all achievements earned by a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get child's achievements with achievement details
    result = await db.execute(
        select(ChildAchievement, Achievement)
        .join(Achievement, ChildAchievement.achievement_id == Achievement.id)
        .where(ChildAchievement.child_id == child_id)
    )
    
    achievements = []
    for child_achievement, achievement in result:
        achievements.append({
            "achievement_id": achievement.id,
            "achievement_name": achievement.name,
            "achievement_icon": achievement.icon,
            "earned_at": child_achievement.earned_at,
            "viewed": child_achievement.viewed
        })
    
    return achievements
