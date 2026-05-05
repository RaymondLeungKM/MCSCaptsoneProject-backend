"""
Category endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.db.session import get_db
from app.schemas.vocabulary import CategoryCreate, CategoryUpdate, CategoryResponse, WordResponse
from app.models.vocabulary import Category, Word
from app.models.user import User
from app.core.security import get_current_admin_user
from app.core.category_colors import get_category_color

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db)
):
    """Get all active categories for frontend/public use."""
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
    )
    categories = result.scalars().all()
    return categories


@router.get("/admin/all", response_model=List[CategoryResponse])
async def get_admin_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all categories, including hidden ones, for admin management."""
    result = await db.execute(
        select(Category).order_by(Category.is_active.desc(), Category.sort_order, Category.name)
    )
    categories = result.scalars().all()
    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific category"""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    return category


@router.get("/{category_id}/words", response_model=List[WordResponse])
async def get_category_words(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all words in a category"""
    result = await db.execute(
        select(Word).where(Word.category == category_id, Word.is_active == True)
    )
    words = result.scalars().all()
    return words


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create new category (admin only)"""
    # Get existing categories for color assignment and default ordering
    result = await db.execute(select(Category))
    existing_categories = result.scalars().all()
    existing_count = len(existing_categories)
    next_sort_order = (
        max((category.sort_order or 0) for category in existing_categories) + 1
        if existing_categories
        else 0
    )
    
    # Auto-assign color if not provided or if default value
    color = category_data.color
    if not color or color in ["bg-sky", "bg-slate-400"]:
        color = get_category_color(category_data.name, existing_count)

    sort_order = (
        category_data.sort_order
        if category_data.sort_order is not None
        else next_sort_order
    )
    
    category = Category(
        id=str(uuid.uuid4()),
        name=category_data.name,
        name_cantonese=category_data.name_cantonese,
        icon=category_data.icon,
        color=color,
        description=category_data.description,
        description_cantonese=category_data.description_cantonese,
        is_active=category_data.is_active,
        sort_order=sort_order,
    )
    
    db.add(category)
    await db.commit()
    await db.refresh(category)
    
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update category (admin only)"""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    update_data = category_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    
    await db.commit()
    await db.refresh(category)
    
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Soft-delete category (admin only)."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    word_result = await db.execute(
        select(Word.id)
        .where(Word.category == category_id, Word.is_active == True)
        .limit(1)
    )
    active_word_id = word_result.scalar_one_or_none()
    if active_word_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remove or reassign active vocabulary items before deleting this category"
        )

    if category.is_active:
        category.is_active = False
        await db.commit()

    return None
