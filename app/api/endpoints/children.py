"""
Children profile endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
import uuid

from app.db.session import get_db
from app.schemas.user import ChildCreate, ChildUpdate, ChildResponse, ChildProfileResponse
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()


@router.post("/", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    child_data: ChildCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new child profile"""
    child = Child(
        id=str(uuid.uuid4()),
        parent_id=current_user.id,
        name=child_data.name,
        age=child_data.age,
        avatar=child_data.avatar,
        daily_goal=child_data.daily_goal,
        learning_style=child_data.learning_style,
        attention_span=child_data.attention_span,
        preferred_time_of_day=child_data.preferred_time_of_day,
    )
    
    db.add(child)
    await db.commit()
    await db.refresh(child, ["interests"])
    
    return child


@router.get("/", response_model=List[ChildResponse])
async def get_children(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all children for current user"""
    result = await db.execute(
        select(Child)
        .options(selectinload(Child.interests))
        .where(Child.parent_id == current_user.id)
    )
    children = result.scalars().all()
    
    # Calculate today's progress for each child
    from app.models.daily_words import DailyWordTracking
    from datetime import datetime
    from sqlalchemy import func
    
    today = datetime.now().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    for child in children:
        today_count_result = await db.execute(
            select(func.count(func.distinct(DailyWordTracking.word_id)))
            .where(
                DailyWordTracking.child_id == child.id,
                DailyWordTracking.date >= start_of_day,
                DailyWordTracking.date <= end_of_day
            )
        )
        today_count = today_count_result.scalar() or 0
        
        if child.today_progress != today_count:
            child.today_progress = today_count
    
    await db.commit()
    
    return children


@router.get("/{child_id}", response_model=ChildProfileResponse)
async def get_child(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific child profile with extended stats"""
    result = await db.execute(
        select(Child)
        .options(selectinload(Child.interests))
        .where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Calculate today's actual progress from DailyWordTracking
    from app.models.daily_words import DailyWordTracking
    from datetime import datetime
    from sqlalchemy import func
    
    today = datetime.now().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    today_count_result = await db.execute(
        select(func.count(func.distinct(DailyWordTracking.word_id)))
        .where(
            DailyWordTracking.child_id == child_id,
            DailyWordTracking.date >= start_of_day,
            DailyWordTracking.date <= end_of_day
        )
    )
    today_count = today_count_result.scalar() or 0
    
    # Update child's today_progress if different
    if child.today_progress != today_count:
        child.today_progress = today_count
        await db.commit()
        await db.refresh(child)
    
    return child


@router.patch("/{child_id}", response_model=ChildResponse)
async def update_child(
    child_id: str,
    child_data: ChildUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update child profile"""
    result = await db.execute(
        select(Child)
        .options(selectinload(Child.interests))
        .where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Update fields
    update_data = child_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(child, field, value)
    
    await db.commit()
    await db.refresh(child, ["interests"])
    
    return child


@router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_child(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete child profile"""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    await db.delete(child)
    await db.commit()
    
    return None
