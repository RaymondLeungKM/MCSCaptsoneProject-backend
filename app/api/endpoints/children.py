"""
Children profile endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import selectinload
from typing import List
import uuid

from app.db.session import get_db
from app.schemas.user import ChildCreate, ChildUpdate, ChildResponse, ChildProfileResponse
from app.models.user import User, Child, ChildInterest
from app.models.vocabulary import Category
from app.core.security import get_current_active_user

router = APIRouter()


async def _resolve_interest_category_ids(
    db: AsyncSession,
    interests: List[str],
) -> List[str]:
    normalized = [interest.strip() for interest in interests if interest and interest.strip()]
    if not normalized:
        return []

    result = await db.execute(
        select(Category).where(
            or_(
                Category.id.in_(normalized),
                Category.name.in_(normalized),
                Category.name_cantonese.in_(normalized),
            )
        )
    )
    categories = result.scalars().all()

    category_lookup: dict[str, str] = {}
    for category in categories:
        category_lookup[category.id] = category.id
        category_lookup[category.name] = category.id
        if category.name_cantonese:
            category_lookup[category.name_cantonese] = category.id

    resolved_ids: List[str] = []
    seen: set[str] = set()
    for interest in normalized:
        category_id = category_lookup.get(interest)
        if category_id and category_id not in seen:
            seen.add(category_id)
            resolved_ids.append(category_id)

    return resolved_ids


async def _replace_child_interests(
    db: AsyncSession,
    child_id: str,
    interests: List[str],
) -> None:
    await db.execute(delete(ChildInterest).where(ChildInterest.child_id == child_id))

    for category_id in await _resolve_interest_category_ids(db, interests):
        db.add(ChildInterest(child_id=child_id, category_id=category_id))


async def _serialize_child_response(
    db: AsyncSession,
    child: Child,
) -> ChildResponse:
    category_ids = [interest.category_id for interest in child.interests if interest.category_id]
    interest_names: List[str] = []

    if category_ids:
        result = await db.execute(select(Category).where(Category.id.in_(category_ids)))
        categories = {category.id: category.name for category in result.scalars().all()}
        interest_names = [categories[category_id] for category_id in category_ids if category_id in categories]

    return ChildResponse(
        id=child.id,
        parent_id=child.parent_id,
        name=child.name,
        age=child.age,
        avatar=child.avatar,
        daily_goal=child.daily_goal,
        learning_style=child.learning_style,
        language_preference=child.language_preference,
        attention_span=child.attention_span,
        preferred_time_of_day=child.preferred_time_of_day,
        level=child.level,
        xp=child.xp,
        words_learned=child.words_learned,
        current_streak=child.current_streak,
        today_progress=child.today_progress,
        created_at=child.created_at,
        last_active=child.last_active,
        interests=interest_names,
    )


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
        language_preference=child_data.language_preference,
        attention_span=child_data.attention_span,
        preferred_time_of_day=child_data.preferred_time_of_day,
    )
    
    db.add(child)
    await db.flush()

    await _replace_child_interests(db, child.id, child_data.interests or [])

    await db.commit()
    await db.refresh(child, ["interests"])
    
    return await _serialize_child_response(db, child)


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

    return [await _serialize_child_response(db, child) for child in children]


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
    
    return ChildProfileResponse(
        **(await _serialize_child_response(db, child)).model_dump()
    )


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
    interests = update_data.pop("interests", None)
    for field, value in update_data.items():
        setattr(child, field, value)

    if interests is not None:
        await _replace_child_interests(db, child.id, interests)
    
    await db.commit()
    await db.refresh(child, ["interests"])
    
    return await _serialize_child_response(db, child)


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
