"""
Children profile endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from typing import List
import uuid
from datetime import date

from app.db.session import get_db
from app.schemas.user import ChildCreate, ChildUpdate, ChildResponse, ChildProfileResponse
from app.models.user import User, Child, ChildInterest
from app.models.vocabulary import Category
from app.core.security import get_current_active_user
from app.core.child_age import calculate_child_age, infer_birth_year_from_age
from app.services.child_metrics import sync_child_metrics

router = APIRouter()


def _normalize_interest_key(value: str) -> str:
    return value.strip().lower()


async def _resolve_interest_category_ids(
    db: AsyncSession,
    interests: List[str],
) -> List[str]:
    normalized_inputs = [_normalize_interest_key(item) for item in interests if item and item.strip()]
    if not normalized_inputs:
        return []

    unique_inputs = list(dict.fromkeys(normalized_inputs))
    result = await db.execute(select(Category))
    categories = result.scalars().all()

    category_by_id = {
        _normalize_interest_key(category.id): category.id for category in categories
    }
    category_by_name = {
        _normalize_interest_key(category.name): category.id
        for category in categories
        if category.name
    }

    resolved: List[str] = []
    for item in unique_inputs:
        category_id = category_by_id.get(item) or category_by_name.get(item)
        if category_id and category_id not in resolved:
            resolved.append(category_id)

    return resolved


async def _replace_child_interests(
    db: AsyncSession,
    child: Child,
    interests: List[str],
) -> None:
    resolved_category_ids = await _resolve_interest_category_ids(db, interests)

    await db.execute(delete(ChildInterest).where(ChildInterest.child_id == child.id))

    if resolved_category_ids:
        db.add_all(
            [
                ChildInterest(child_id=child.id, category_id=category_id)
                for category_id in resolved_category_ids
            ]
        )


async def _load_child_with_interests(
    db: AsyncSession,
    child_id: str,
    parent_id: str,
) -> Child | None:
    result = await db.execute(
        select(Child)
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
        .where(Child.id == child_id, Child.parent_id == parent_id)
    )
    return result.scalar_one_or_none()


def _apply_effective_age(child: Child, *, as_of: date | None = None) -> None:
    child.age = calculate_child_age(
        stored_age=child.age,
        birth_year=child.birth_year,
        birth_month=child.birth_month,
        as_of=as_of,
    )


@router.post("/", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    child_data: ChildCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new child profile"""
    birth_year = child_data.birth_year
    birth_month = child_data.birth_month
    if birth_year is None:
        birth_year, inferred_birth_month = infer_birth_year_from_age(child_data.age)
        if birth_month is None:
            birth_month = inferred_birth_month

    child = Child(
        id=str(uuid.uuid4()),
        parent_id=current_user.id,
        name=child_data.name,
        age=child_data.age,
        birth_year=birth_year,
        birth_month=birth_month,
        avatar=child_data.avatar,
        daily_goal=child_data.daily_goal,
        learning_style=child_data.learning_style,
        attention_span=child_data.attention_span,
        preferred_time_of_day=child_data.preferred_time_of_day,
    )

    db.add(child)
    await db.flush()

    if child_data.interests is not None:
        await _replace_child_interests(db, child, child_data.interests)

    await db.commit()
    child_with_interests = await _load_child_with_interests(db, child.id, current_user.id)

    if child_with_interests is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    _apply_effective_age(child_with_interests)

    return child_with_interests


@router.get("/", response_model=List[ChildResponse])
async def get_children(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all children for current user"""
    result = await db.execute(
        select(Child)
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
        .where(Child.parent_id == current_user.id)
    )
    children = result.scalars().all()

    today = date.today()
    has_changes = False

    for child in children:
        child_changed = await sync_child_metrics(db, child, as_of=today)
        has_changes = has_changes or child_changed

    if has_changes:
        await db.commit()

    for child in children:
        _apply_effective_age(child, as_of=today)
    
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
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
        .where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    today = date.today()

    if await sync_child_metrics(db, child, as_of=today):
        await db.commit()

    _apply_effective_age(child, as_of=today)
    
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
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
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

    if "age" in update_data and "birth_year" not in update_data:
        update_data["birth_year"], inferred_birth_month = infer_birth_year_from_age(
            update_data["age"]
        )
        if "birth_month" not in update_data:
            update_data["birth_month"] = inferred_birth_month

    for field, value in update_data.items():
        setattr(child, field, value)

    if interests is not None:
        await _replace_child_interests(db, child, interests)
    
    await db.commit()
    child_with_interests = await _load_child_with_interests(db, child.id, current_user.id)

    if child_with_interests is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    _apply_effective_age(child_with_interests)

    return child_with_interests


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
