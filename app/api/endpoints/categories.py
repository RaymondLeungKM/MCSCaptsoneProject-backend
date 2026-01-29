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
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db)
):
    """Get all active categories"""
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
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
    current_user: User = Depends(get_current_active_user)
):
    """Create new category (admin only)"""
    category = Category(
        id=str(uuid.uuid4()),
        name=category_data.name,
        icon=category_data.icon,
        color=category_data.color,
        description=category_data.description,
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
    current_user: User = Depends(get_current_active_user)
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
