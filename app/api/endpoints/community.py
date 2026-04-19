"""
Community endpoints – Epic 10.1 (Phase 10)

Covers:
  GET  /community/feed                         – approved posts (public)
  POST /community/posts/{child_id}             – submit via file upload
  POST /community/posts/{child_id}/from-collection – submit from existing word image
  GET  /community/posts/pending                – moderation queue (parent only)
  PUT  /community/posts/{post_id}/moderate     – approve / reject (parent only)
  POST /community/posts/{post_id}/react        – add star reaction
  DELETE /community/posts/{post_id}/react      – remove reaction
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
import uuid
import aiofiles
import os

from app.db.session import get_db
from app.core.security import get_current_active_user, get_current_user
from app.models.user import User, Child
from app.models.vocabulary import Word
from app.models.community import CommunityPost, PostReaction, ModerationStatus

router = APIRouter()

# ── Upload helpers ──────────────────────────────────────────────────────────

UPLOAD_DIR = Path("uploads/community")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_ext(filename: str) -> str:
    return Path(filename).suffix.lower()


async def _save_upload(file: UploadFile) -> str:
    """Save an upload and return the relative URL path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    ext = _safe_ext(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {ext}")

    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = UPLOAD_DIR / unique_name

    size = 0
    async with aiofiles.open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                await f.close()
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
            await f.write(chunk)

    return f"/uploads/community/{unique_name}"


# ── Schemas (inline Pydantic to avoid creating a separate schema file) ──────

from pydantic import BaseModel


class CommunityPostOut(BaseModel):
    id: str
    child_id: str
    word_id: Optional[str]
    word_text: Optional[str]
    word_text_cantonese: Optional[str]
    caption: Optional[str]
    image_url: str
    is_anonymous: bool
    moderation_status: str
    reaction_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ModerateRequest(BaseModel):
    status: str  # "approved" | "rejected"
    note: Optional[str] = None


class FromCollectionRequest(BaseModel):
    word_id: str
    caption: Optional[str] = None


class ReactRequest(BaseModel):
    reaction_type: str = "star"


# ── Helper: verify child belongs to current user ────────────────────────────

async def _get_owned_child(child_id: str, current_user: User, db: AsyncSession) -> Child:
    result = await db.execute(
        select(Child).where(
            and_(Child.id == child_id, Child.parent_id == current_user.id)
        )
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return child


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[CommunityPostOut])
async def get_community_feed(
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0, ge=0),
    word_id: Optional[str] = Query(default=None),
    child_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Approved community posts – no auth required (public feed)."""
    q = select(CommunityPost).where(
        CommunityPost.moderation_status == ModerationStatus.APPROVED
    )
    if word_id:
        q = q.where(CommunityPost.word_id == word_id)
    if child_id:
        q = q.where(CommunityPost.child_id == child_id)
    q = q.order_by(CommunityPost.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/posts/{child_id}", response_model=CommunityPostOut, status_code=201)
async def submit_community_post(
    child_id: str,
    file: UploadFile = File(...),
    word_id: Optional[str] = Query(default=None),
    word_text: Optional[str] = Query(default=None),
    word_text_cantonese: Optional[str] = Query(default=None),
    caption: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new community photo check-in (starts as 'pending')."""
    await _get_owned_child(child_id, current_user, db)

    image_url = await _save_upload(file)

    post = CommunityPost(
        id=str(uuid.uuid4()),
        child_id=child_id,
        word_id=word_id,
        word_text=word_text,
        word_text_cantonese=word_text_cantonese,
        caption=caption[:120] if caption else None,
        image_url=image_url,
        is_anonymous=True,
        moderation_status=ModerationStatus.PENDING,
        reaction_count=0,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.post("/posts/{child_id}/from-collection", response_model=CommunityPostOut, status_code=201)
async def submit_post_from_collection(
    child_id: str,
    body: FromCollectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a community post reusing an existing word image from the child's collection."""
    await _get_owned_child(child_id, current_user, db)

    # Fetch word for image URL and display text
    word_result = await db.execute(select(Word).where(Word.id == body.word_id))
    word = word_result.scalar_one_or_none()
    if not word or not word.image_url:
        raise HTTPException(status_code=400, detail="Word has no image")

    post = CommunityPost(
        id=str(uuid.uuid4()),
        child_id=child_id,
        word_id=word.id,
        word_text=word.word,
        word_text_cantonese=word.word_cantonese,
        caption=body.caption[:120] if body.caption else None,
        image_url=word.image_url,
        is_anonymous=True,
        moderation_status=ModerationStatus.PENDING,
        reaction_count=0,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.get("/posts/pending", response_model=List[CommunityPostOut])
async def get_pending_posts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all pending posts belonging to the current parent's children."""
    # Collect children IDs for this parent
    children_result = await db.execute(
        select(Child.id).where(Child.parent_id == current_user.id)
    )
    child_ids = [row[0] for row in children_result.fetchall()]
    if not child_ids:
        return []

    result = await db.execute(
        select(CommunityPost)
        .where(
            and_(
                CommunityPost.child_id.in_(child_ids),
                CommunityPost.moderation_status == ModerationStatus.PENDING,
            )
        )
        .order_by(CommunityPost.created_at.desc())
    )
    return result.scalars().all()


@router.put("/posts/{post_id}/moderate", response_model=CommunityPostOut)
async def moderate_post(
    post_id: str,
    body: ModerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a pending post (parent must own the child)."""
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Verify ownership
    await _get_owned_child(post.child_id, current_user, db)

    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")

    post.moderation_status = ModerationStatus(body.status)
    post.moderation_note = body.note
    post.moderated_by = current_user.id
    post.moderated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(post)
    return post


@router.post("/posts/{post_id}/react", status_code=201)
async def react_to_post(
    post_id: str,
    child_id: str = Query(...),
    body: ReactRequest = ReactRequest(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a star reaction from a child."""
    # Verify the child belongs to the current user
    await _get_owned_child(child_id, current_user, db)

    # Check post exists and is approved
    post_result = await db.execute(
        select(CommunityPost).where(
            and_(
                CommunityPost.id == post_id,
                CommunityPost.moderation_status == ModerationStatus.APPROVED,
            )
        )
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Idempotent – ignore duplicate reactions
    existing = await db.execute(
        select(PostReaction).where(
            and_(
                PostReaction.post_id == post_id,
                PostReaction.child_id == child_id,
                PostReaction.reaction_type == body.reaction_type,
            )
        )
    )
    if existing.scalar_one_or_none():
        return {"detail": "already reacted"}

    reaction = PostReaction(
        post_id=post_id,
        child_id=child_id,
        reaction_type=body.reaction_type,
    )
    db.add(reaction)
    post.reaction_count = post.reaction_count + 1
    await db.commit()
    await db.refresh(reaction)
    return reaction


@router.delete("/posts/{post_id}/react", status_code=204)
async def remove_reaction(
    post_id: str,
    child_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a star reaction."""
    await _get_owned_child(child_id, current_user, db)

    result = await db.execute(
        select(PostReaction).where(
            and_(
                PostReaction.post_id == post_id,
                PostReaction.child_id == child_id,
            )
        )
    )
    reaction = result.scalar_one_or_none()
    if reaction:
        await db.delete(reaction)
        # Decrement counter
        post_result = await db.execute(
            select(CommunityPost).where(CommunityPost.id == post_id)
        )
        post = post_result.scalar_one_or_none()
        if post and post.reaction_count > 0:
            post.reaction_count = post.reaction_count - 1
        await db.commit()
