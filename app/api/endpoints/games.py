"""
Game endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone, timedelta

from app.db.session import get_db
from app.schemas.content import GameResponse
from app.schemas.analytics import GameSessionCreate, GameSessionResponse
from app.models.content import Game
from app.models.analytics import GameSession
from app.models.user import User, Child
from app.models.vocabulary import WordProgress
from app.core.local_time import ClientLocalDay, get_client_local_day
from app.core.security import get_current_active_user

router = APIRouter()

MAX_WORD_EXPOSURE_STARS = 6


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _apply_daily_star_increment_limit(
    progress: WordProgress,
    *,
    event_at: datetime,
    client_local_day: ClientLocalDay,
) -> bool:
    current_exposure = min(int(progress.exposure_count or 0), MAX_WORD_EXPOSURE_STARS)
    progress.exposure_count = current_exposure

    if current_exposure >= MAX_WORD_EXPOSURE_STARS:
        return False

    last_practiced = progress.last_practiced
    if last_practiced and (
        client_local_day.date_for_timestamp(last_practiced)
        == client_local_day.date_for_timestamp(event_at)
    ):
        return False

    progress.exposure_count = min(current_exposure + 1, MAX_WORD_EXPOSURE_STARS)
    progress.last_practiced = event_at
    return True


@router.get("/", response_model=List[GameResponse])
async def get_games(
    db: AsyncSession = Depends(get_db)
):
    """Get all active games"""
    result = await db.execute(
        select(Game).where(Game.is_active == True).order_by(Game.sort_order)
    )
    return result.scalars().all()


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific game details"""
    result = await db.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return game


@router.post("/{game_id}/play", response_model=GameSessionResponse)
async def record_game_session(
    game_id: str,
    session_data: GameSessionCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record a completed mini-game session.

    - Saves a GameSession row
    - Increments WordProgress for every word shown (exposure_count, total_attempts)
    - Increments correct_attempts for correctly answered words
    - Auto-masters a word when success_rate >= 80 % after >= 3 attempts
    - Awards XP to the child (5 XP per correct answer + star bonus)
    - Handles child level-ups
    """
    # ── 1. Verify child belongs to the authenticated parent ────────────────
    result = await db.execute(
        select(Child).where(
            Child.id == session_data.child_id,
            Child.parent_id == current_user.id,
        )
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")

    # ── 2. Calculate XP ────────────────────────────────────────────────────
    base_xp = session_data.score * 5            # 5 XP per correct answer
    star_bonus = (session_data.stars - 1) * 10  # 0 / 10 / 20 for ⭐/🌟/🏆
    xp_earned = base_xp + star_bonus

    # ── 3. Persist game session ────────────────────────────────────────────
    game_session = GameSession(
        child_id=session_data.child_id,
        game_id=game_id,
        score=session_data.score,
        max_score=session_data.max_score,
        duration_seconds=session_data.duration_seconds,
        words_seen=session_data.words_seen,
        words_correct=session_data.words_correct,
        stars=session_data.stars,
        xp_earned=xp_earned,
    )
    db.add(game_session)

    # ── 4. Update WordProgress for every word the child saw ───────────────
    words_correct_set = set(session_data.words_correct)
    now_utc = datetime.now(timezone.utc)
    client_local_day = get_client_local_day(request)

    for word_id in session_data.words_seen:
        prog_result = await db.execute(
            select(WordProgress).where(
                WordProgress.child_id == session_data.child_id,
                WordProgress.word_id == word_id,
            )
        )
        progress = prog_result.scalar_one_or_none()
        is_correct = word_id in words_correct_set

        if not progress:
            # First ever exposure — create record and bump word count
            progress = WordProgress(
                child_id=session_data.child_id,
                word_id=word_id,
                exposure_count=1,
                last_practiced=now_utc,
                correct_attempts=1 if is_correct else 0,
                total_attempts=1,
                success_rate=1.0 if is_correct else 0.0,
            )
            db.add(progress)
            child.words_learned = (child.words_learned or 0) + 1
        else:
            _apply_daily_star_increment_limit(
                progress,
                event_at=now_utc,
                client_local_day=client_local_day,
            )
            progress.total_attempts = (progress.total_attempts or 0) + 1
            if is_correct:
                progress.correct_attempts = (progress.correct_attempts or 0) + 1
            ca = progress.correct_attempts or 0
            ta = progress.total_attempts or 1
            progress.success_rate = ca / ta
            # Auto-mastery threshold
            if ta >= 3 and (progress.success_rate or 0) >= 0.8:
                progress.mastered = True

    # ── 5. Award XP and handle level-up ───────────────────────────────────
    child.xp = (child.xp or 0) + xp_earned
    while child.xp >= (child.level or 1) * 100:
        child.level = (child.level or 1) + 1

    await db.commit()
    await db.refresh(game_session)
    return game_session
