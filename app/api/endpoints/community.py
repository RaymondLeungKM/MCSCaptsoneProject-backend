"""
Community Feed API endpoints – Epic 10.1 (Phase 10)

Handles:
  • Submitting child photo check-ins
  • Browsing the approved community feed
  • Reacting (starring) posts anonymously
  • Parental moderation (approve / reject)
  • COPPA / GDPR-K safety: no names or locations are exposed
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import uuid
import aiofiles

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.user import User, Child
from app.models.community import CommunityPost, PostReaction, ModerationStatus
from app.schemas.community import (
    CommunityPostResponse,
    CommunityPostFromCollectionCreate,
    ModerationAction,
    PostReactionCreate,
    PostReactionResponse,
)
from app.models.vocabulary import Word

router = APIRouter()

# ---------------------------------------------------------------------------
# Storage configuration (mirrors uploads.py)
# ---------------------------------------------------------------------------
UPLOAD_DIR = Path("uploads/images/community")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Helper: verify child belongs to the current user
# ---------------------------------------------------------------------------
async def _get_child(child_id: str, parent: User, db: AsyncSession) -> Child:
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == parent.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    return child


# ===========================================================================
# 10.1.1  Safe Photo Sharing – submission endpoint
# ===========================================================================

@router.post("/posts/{child_id}", response_model=CommunityPostResponse, status_code=201)
async def submit_community_post(
    child_id: str,
    file: UploadFile = File(..., description="Photo of the discovered object"),
    word_id: Optional[str] = Form(None),
    word_text: Optional[str] = Form(None),
    word_text_cantonese: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a child's photo check-in for parental review.

    The post is created with `moderation_status = PENDING`.  It will **not**
    appear in the public feed until a parent approves it via the moderation
    endpoint.  This satisfies the COPPA / GDPR-K requirement of parental
    approval before any content is shared.
    """
    # Verify child belongs to parent
    await _get_child(child_id, current_user, db)

    # Validate & save file
    if not file.filename or not _allowed(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use JPG, PNG, GIF, or WEBP.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be less than 10 MB.",
        )

    ext = Path(file.filename).suffix.lower()
    filename = f"{uuid.uuid4()}{ext}"
    dest = UPLOAD_DIR / filename
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    image_url = f"/uploads/images/community/{filename}"

    # Truncate caption to 120 chars for safety
    safe_caption = (caption or "").strip()[:120] or None

    post = CommunityPost(
        id=str(uuid.uuid4()),
        child_id=child_id,
        word_id=word_id,
        word_text=word_text,
        word_text_cantonese=word_text_cantonese,
        caption=safe_caption,
        image_url=image_url,
        is_anonymous=True,
        moderation_status=ModerationStatus.PENDING,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


# ===========================================================================
# 10.1.1  Share from My Collection – no new file upload required
# ===========================================================================

@router.post("/posts/{child_id}/from-collection", response_model=CommunityPostResponse, status_code=201)
async def submit_community_post_from_collection(
    child_id: str,
    payload: CommunityPostFromCollectionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a community post by picking an existing word from the child's
    My Collection.  Re-uses the word's existing image URL – no new file
    upload is needed.

    The post is created with ``moderation_status = PENDING`` and will **not**
    appear in the public feed until a parent approves it, satisfying the
    COPPA / GDPR-K parental-approval requirement.
    """
    # Verify child belongs to parent
    await _get_child(child_id, current_user, db)

    # Fetch the word and verify it belongs to this child's collection
    word_result = await db.execute(
        select(Word).where(Word.id == payload.word_id, Word.is_active == True)
    )
    word = word_result.scalar_one_or_none()
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    if word.created_by_child_id != child_id:
        raise HTTPException(
            status_code=403,
            detail="Word does not belong to this child's collection",
        )

    if not word.image_url:
        raise HTTPException(
            status_code=400,
            detail="Selected word has no image to share",
        )

    safe_caption = (payload.caption or "").strip()[:120] or None

    post = CommunityPost(
        id=str(uuid.uuid4()),
        child_id=child_id,
        word_id=word.id,
        word_text=word.word,
        word_text_cantonese=word.word_cantonese,
        caption=safe_caption,
        image_url=word.image_url,
        is_anonymous=True,
        moderation_status=ModerationStatus.PENDING,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


# ===========================================================================
# 10.1.1  Parental Moderation – list & act on pending posts
# ===========================================================================

@router.get("/posts/pending", response_model=List[CommunityPostResponse])
async def list_pending_posts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all posts across the current parent's children that are
    awaiting moderation (status = PENDING).
    """
    # Get all child IDs belonging to this parent
    child_result = await db.execute(
        select(Child.id).where(Child.parent_id == current_user.id)
    )
    child_ids = [r for r in child_result.scalars().all()]
    if not child_ids:
        return []

    result = await db.execute(
        select(CommunityPost)
        .where(
            CommunityPost.child_id.in_(child_ids),
            CommunityPost.moderation_status == ModerationStatus.PENDING,
        )
        .order_by(CommunityPost.created_at.desc())
    )
    return result.scalars().all()


@router.put("/posts/{post_id}/moderate", response_model=CommunityPostResponse)
async def moderate_post(
    post_id: str,
    action: ModerationAction,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Parent approves or rejects a pending community post.

    • **APPROVED** → post appears in the public community feed.
    • **REJECTED** → post is hidden; moderation_note explains why.
    """
    # Fetch post
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Verify the post belongs to one of this parent's children
    child_result = await db.execute(
        select(Child).where(Child.id == post.child_id, Child.parent_id == current_user.id)
    )
    if not child_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorised to moderate this post")

    post.moderation_status = action.status
    post.moderated_by = current_user.id
    post.moderated_at = datetime.utcnow()
    post.moderation_note = action.note

    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


# ===========================================================================
# 10.1.2  "What Others Found" – public community feed
# ===========================================================================

@router.get("/feed", response_model=List[CommunityPostResponse])
async def get_community_feed(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    word_id: Optional[str] = Query(None, description="Filter by vocabulary word"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the approved community feed (no PII exposed – all posts are
    anonymous).  Optionally filter by a specific vocabulary word.

    GDPR-K / COPPA compliance:
    - All posts are anonymous (is_anonymous=True is enforced at creation).
    - Only APPROVED posts are surfaced.
    - No real names, ages, or locations are returned.
    """
    query = select(CommunityPost).where(
        CommunityPost.moderation_status == ModerationStatus.APPROVED
    )
    if word_id:
        query = query.where(CommunityPost.word_id == word_id)

    query = query.order_by(CommunityPost.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# ===========================================================================
# 10.1.2  Reactions – children can star posts anonymously
# ===========================================================================

@router.post(
    "/posts/{post_id}/react",
    response_model=PostReactionResponse,
    status_code=201,
)
async def react_to_post(
    post_id: str,
    child_id: str = Query(..., description="ID of the reacting child"),
    payload: PostReactionCreate = PostReactionCreate(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add an anonymous star / reaction to an approved community post.

    Each child can react once per post (duplicate reactions are silently
    ignored and return the existing reaction).
    """
    # Verify child belongs to parent
    await _get_child(child_id, current_user, db)

    # Verify post exists and is approved
    post_result = await db.execute(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            CommunityPost.moderation_status == ModerationStatus.APPROVED,
        )
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found or not yet approved")

    # Idempotency: return existing reaction if already starred
    existing = await db.execute(
        select(PostReaction).where(
            PostReaction.post_id == post_id, PostReaction.child_id == child_id
        )
    )
    existing_reaction = existing.scalar_one_or_none()
    if existing_reaction:
        return existing_reaction

    reaction = PostReaction(
        post_id=post_id,
        child_id=child_id,
        reaction_type=payload.reaction_type,
    )
    db.add(reaction)

    # Increment cached count
    await db.execute(
        update(CommunityPost)
        .where(CommunityPost.id == post_id)
        .values(reaction_count=CommunityPost.reaction_count + 1)
    )

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
    """Remove a child's reaction from a post."""
    await _get_child(child_id, current_user, db)

    result = await db.execute(
        select(PostReaction).where(
            PostReaction.post_id == post_id, PostReaction.child_id == child_id
        )
    )
    reaction = result.scalar_one_or_none()
    if reaction:
        await db.delete(reaction)
        await db.execute(
            update(CommunityPost)
            .where(CommunityPost.id == post_id, CommunityPost.reaction_count > 0)
            .values(reaction_count=CommunityPost.reaction_count - 1)
        )
        await db.commit()
