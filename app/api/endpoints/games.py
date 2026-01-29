"""
Game endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.session import get_db
from app.schemas.content import GameResponse
from app.models.content import Game
from app.models.user import User
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/", response_model=List[GameResponse])
async def get_games(
    db: AsyncSession = Depends(get_db)
):
    """Get all active games"""
    result = await db.execute(
        select(Game).where(Game.is_active == True).order_by(Game.sort_order)
    )
    games = result.scalars().all()
    return games


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific game details"""
    result = await db.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found"
        )
    
    return game


@router.post("/{game_id}/play")
async def record_game_session(
    game_id: str,
    child_id: str,
    words_used: List[str],
    duration_minutes: int,
    score: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a game play session"""
    # Verify game exists
    result = await db.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found"
        )
    
    # TODO: Record in learning session
    # This would create/update a LearningSession record
    
    return {
        "message": "Game session recorded",
        "game_id": game_id,
        "words_used": len(words_used),
        "duration": duration_minutes
    }
