"""
User management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.db.session import get_db
from app.schemas.user import UserResponse, UserUpdate, ConsentUpdate
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile"""
    update_data = user_data.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.patch("/me/consent", response_model=UserResponse)
async def update_consent(
    consent_data: ConsentUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Record parent consent choices and propagate community sharing to all children"""
    current_user.consent_given = True
    current_user.consent_given_at = datetime.now(timezone.utc)
    current_user.consent_camera = consent_data.consent_camera
    current_user.consent_microphone = consent_data.consent_microphone
    current_user.consent_analytics = consent_data.consent_analytics

    # Propagate community sharing preference to all children
    children_result = await db.execute(
        select(Child).where(Child.parent_id == current_user.id)
    )
    for child in children_result.scalars().all():
        child.community_sharing_enabled = consent_data.community_sharing_enabled or False

    await db.commit()
    await db.refresh(current_user)

    return current_user
