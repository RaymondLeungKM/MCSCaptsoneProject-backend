"""
Parent Social Networking API endpoints – Epic 10.2 (Phase 10)

Handles:
  • Friend requests & responses (connect / block)
  • Shared progress dashboard (what friends' kids are learning)
  • Community challenge CRUD & participation tracking
  • Group challenges / leaderboards
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from app.db.session import get_db
from app.core.security import get_current_active_user, get_current_admin_user
from app.models.user import User, Child
from app.core.child_age import calculate_child_age
from app.models.vocabulary import WordProgress, Word
from app.models.community import (
    ParentFriendship,
    FriendshipStatus,
    CommunityChallenge,
    ChallengeParticipation,
    ChallengeStatus,
)
from app.schemas.community import (
    FriendRequestCreate,
    FriendRequestByIdCreate,
    UserSearchResult,
    FriendshipResponse,
    FriendshipStatusUpdate,
    FriendProgressResponse,
    FriendChildStats,
    CommunityChallengeCreate,
    CommunityChallengeUpdate,
    CommunityChallengeResponse,
    ChallengeParticipationResponse,
    ChallengeProgressUpdate,
)

router = APIRouter()


# ===========================================================================
# 10.2.1  Friend Connections & "Following"
# ===========================================================================

@router.post("/friends/request", response_model=FriendshipResponse, status_code=201)
async def send_friend_request(
    payload: FriendRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a friendship request to another parent identified by email address.

    The addressee must have an active account.  An invitation link / in-app
    notification would normally be sent via a background task; here we create
    the DB record in PENDING state and return it.
    """
    # Resolve addressee
    result = await db.execute(
        select(User).where(User.email == payload.addressee_email, User.is_active == True)
    )
    addressee = result.scalar_one_or_none()
    if not addressee:
        raise HTTPException(status_code=404, detail="User with that email not found")

    if addressee.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a friend")

    # Check for an existing relationship in either direction
    existing = await db.execute(
        select(ParentFriendship).where(
            or_(
                and_(
                    ParentFriendship.requester_id == current_user.id,
                    ParentFriendship.addressee_id == addressee.id,
                ),
                and_(
                    ParentFriendship.requester_id == addressee.id,
                    ParentFriendship.addressee_id == current_user.id,
                ),
            )
        )
    )
    existing_friendship = existing.scalar_one_or_none()
    if existing_friendship:
        if existing_friendship.status == FriendshipStatus.ACCEPTED:
            raise HTTPException(status_code=409, detail="Already friends")
        if existing_friendship.status == FriendshipStatus.PENDING:
            raise HTTPException(status_code=409, detail="Friend request already pending")
        if existing_friendship.status == FriendshipStatus.BLOCKED:
            raise HTTPException(status_code=403, detail="Cannot send request – relationship is blocked")

    friendship = ParentFriendship(
        id=str(uuid.uuid4()),
        requester_id=current_user.id,
        addressee_id=addressee.id,
        status=FriendshipStatus.PENDING,
    )
    db.add(friendship)
    await db.commit()
    await db.refresh(friendship)

    return FriendshipResponse(
        id=friendship.id,
        requester_id=friendship.requester_id,
        addressee_id=friendship.addressee_id,
        status=friendship.status,
        created_at=friendship.created_at,
        updated_at=friendship.updated_at,
        requester_name=current_user.full_name,
        addressee_name=addressee.full_name,
    )


@router.get("/users/search", response_model=UserSearchResult)
async def search_user_by_id(
    user_id: str = Query(..., description="Exact user ID to look up"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Look up a parent account by their exact user ID.

    Returns only the user's ID and display name (no email or other PII)
    so that a parent can confirm they found the right person before
    sending a friend request.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="That is your own user ID")

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    found = result.scalar_one_or_none()
    if not found:
        raise HTTPException(status_code=404, detail="No user found with that ID")

    return UserSearchResult(id=found.id, full_name=found.full_name)


@router.post("/friends/request-by-id", response_model=FriendshipResponse, status_code=201)
async def send_friend_request_by_id(
    payload: FriendRequestByIdCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a friendship request to another parent identified by their user ID.

    Useful when parents share their user ID directly instead of their email
    address.
    """
    if payload.addressee_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a friend")

    result = await db.execute(
        select(User).where(User.id == payload.addressee_id, User.is_active == True)
    )
    addressee = result.scalar_one_or_none()
    if not addressee:
        raise HTTPException(status_code=404, detail="No active user found with that ID")

    # Check for an existing relationship in either direction
    existing = await db.execute(
        select(ParentFriendship).where(
            or_(
                and_(
                    ParentFriendship.requester_id == current_user.id,
                    ParentFriendship.addressee_id == addressee.id,
                ),
                and_(
                    ParentFriendship.requester_id == addressee.id,
                    ParentFriendship.addressee_id == current_user.id,
                ),
            )
        )
    )
    existing_friendship = existing.scalar_one_or_none()
    if existing_friendship:
        if existing_friendship.status == FriendshipStatus.ACCEPTED:
            raise HTTPException(status_code=409, detail="Already friends")
        if existing_friendship.status == FriendshipStatus.PENDING:
            raise HTTPException(status_code=409, detail="Friend request already pending")
        if existing_friendship.status == FriendshipStatus.BLOCKED:
            raise HTTPException(status_code=403, detail="Cannot send request – relationship is blocked")

    friendship = ParentFriendship(
        id=str(uuid.uuid4()),
        requester_id=current_user.id,
        addressee_id=addressee.id,
        status=FriendshipStatus.PENDING,
    )
    db.add(friendship)
    await db.commit()
    await db.refresh(friendship)

    return FriendshipResponse(
        id=friendship.id,
        requester_id=friendship.requester_id,
        addressee_id=friendship.addressee_id,
        status=friendship.status,
        created_at=friendship.created_at,
        updated_at=friendship.updated_at,
        requester_name=current_user.full_name,
        addressee_name=addressee.full_name,
    )


@router.put("/friends/{friendship_id}/respond", response_model=FriendshipResponse)
async def respond_to_friend_request(
    friendship_id: str,
    payload: FriendshipStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept or block a pending friend request.

    Only the addressee of the original request may call this endpoint.
    Accepted → status = ACCEPTED (both parents can view each other's opt-in data).
    Blocked  → status = BLOCKED  (no new requests can be sent).
    """
    result = await db.execute(
        select(ParentFriendship).where(ParentFriendship.id == friendship_id)
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        raise HTTPException(status_code=404, detail="Friendship record not found")

    if friendship.addressee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the addressee can respond to this request")

    if friendship.status != FriendshipStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Request is already {friendship.status}")

    if payload.status not in (FriendshipStatus.ACCEPTED, FriendshipStatus.BLOCKED):
        raise HTTPException(status_code=400, detail="status must be ACCEPTED or BLOCKED")

    friendship.status = payload.status
    friendship.updated_at = datetime.now(timezone.utc)
    db.add(friendship)
    await db.commit()
    await db.refresh(friendship)

    # Resolve names for response
    req_result = await db.execute(select(User).where(User.id == friendship.requester_id))
    req_user = req_result.scalar_one_or_none()
    addr_result = await db.execute(select(User).where(User.id == friendship.addressee_id))
    addr_user = addr_result.scalar_one_or_none()

    return FriendshipResponse(
        id=friendship.id,
        requester_id=friendship.requester_id,
        addressee_id=friendship.addressee_id,
        status=friendship.status,
        created_at=friendship.created_at,
        updated_at=friendship.updated_at,
        requester_name=req_user.full_name if req_user else None,
        addressee_name=addr_user.full_name if addr_user else None,
    )


@router.get("/friends", response_model=List[FriendshipResponse])
async def list_friends(
    include_pending: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all accepted friendships (and optionally pending requests) for the
    current user.
    """
    status_filter = (
        [FriendshipStatus.ACCEPTED, FriendshipStatus.PENDING]
        if include_pending
        else [FriendshipStatus.ACCEPTED]
    )
    result = await db.execute(
        select(ParentFriendship).where(
            or_(
                ParentFriendship.requester_id == current_user.id,
                ParentFriendship.addressee_id == current_user.id,
            ),
            ParentFriendship.status.in_(status_filter),
        )
    )
    friendships = result.scalars().all()

    # Enrich with names
    enriched = []
    for f in friendships:
        other_id = (
            f.addressee_id if f.requester_id == current_user.id else f.requester_id
        )
        other_result = await db.execute(select(User).where(User.id == other_id))
        other = other_result.scalar_one_or_none()
        enriched.append(
            FriendshipResponse(
                id=f.id,
                requester_id=f.requester_id,
                addressee_id=f.addressee_id,
                status=f.status,
                created_at=f.created_at,
                updated_at=f.updated_at,
                requester_name=(
                    current_user.full_name
                    if f.requester_id == current_user.id
                    else (other.full_name if other else None)
                ),
                addressee_name=(
                    other.full_name
                    if f.requester_id == current_user.id
                    else current_user.full_name
                ) if other else None,
            )
        )
    return enriched


# ===========================================================================
# 10.2.2  Shared Progress Dashboard
# ===========================================================================

@router.get("/friends/progress", response_model=List[FriendProgressResponse])
async def get_friends_progress(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return aggregate learning progress for children of all accepted friends.

    Privacy rules (opt-in):
    - Only child first name + avatar + aggregate stats (no PII, no location).
    - Parents can opt out via privacy settings (future enhancement).
    """
    # Collect accepted friend user IDs
    result = await db.execute(
        select(ParentFriendship).where(
            or_(
                ParentFriendship.requester_id == current_user.id,
                ParentFriendship.addressee_id == current_user.id,
            ),
            ParentFriendship.status == FriendshipStatus.ACCEPTED,
        )
    )
    friendships = result.scalars().all()

    friend_ids = [
        f.addressee_id if f.requester_id == current_user.id else f.requester_id
        for f in friendships
    ]
    if not friend_ids:
        return []

    progress_list: List[FriendProgressResponse] = []

    for friend_id in friend_ids:
        friend_result = await db.execute(select(User).where(User.id == friend_id))
        friend = friend_result.scalar_one_or_none()
        if not friend:
            continue

        # Get friend's children
        children_result = await db.execute(
            select(Child).where(Child.parent_id == friend_id)
        )
        children = children_result.scalars().all()

        children_stats: List[FriendChildStats] = []
        for child in children:
            # Fetch the 8 most recently practiced words for this child
            recent_result = await db.execute(
                select(Word)
                .join(WordProgress, WordProgress.word_id == Word.id)
                .where(WordProgress.child_id == child.id)
                .order_by(WordProgress.last_practiced.desc().nullslast())
                .limit(8)
            )
            recent_word_objs = recent_result.scalars().all()
            recent_words = [
                w.word_cantonese or w.word for w in recent_word_objs if w
            ]

            children_stats.append(
                FriendChildStats(
                    child_name=child.name,
                    avatar=child.avatar or "🧒",
                    age=calculate_child_age(
                        stored_age=child.age,
                        birth_year=child.birth_year,
                        birth_month=child.birth_month,
                    ),
                    words_learned=child.words_learned,
                    current_streak=child.current_streak,
                    level=child.level,
                    recent_words=recent_words,
                )
            )

        progress_list.append(
            FriendProgressResponse(
                friend_id=friend.id,
                friend_name=friend.full_name,
                children_stats=children_stats,
            )
        )

    return progress_list


# ===========================================================================
# 10.2.3  Community Challenges
# ===========================================================================

def _challenge_window_filters(now: datetime):
    return (
        CommunityChallenge.starts_at <= now,
        CommunityChallenge.ends_at >= now,
    )


def _validate_challenge_window(starts_at: datetime, ends_at: datetime):
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge end time must be after start time",
        )


@router.get("/admin/challenges", response_model=List[CommunityChallengeResponse])
async def list_admin_challenges(
    status_filter: Optional[ChallengeStatus] = Query(
        None, alias="status", description="Filter by challenge status"
    ),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List public community challenges for admin management."""
    query = select(CommunityChallenge)
    if status_filter:
        query = query.where(CommunityChallenge.status == status_filter)

    result = await db.execute(
        query.order_by(CommunityChallenge.starts_at.desc(), CommunityChallenge.created_at.desc())
    )
    return result.scalars().all()


@router.get("/challenges", response_model=List[CommunityChallengeResponse])
async def list_challenges(
    status_filter: Optional[ChallengeStatus] = Query(
        None, alias="status", description="Filter by challenge status"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return community challenges (defaults to ACTIVE)."""
    now = datetime.now(timezone.utc)
    query = select(CommunityChallenge)
    if status_filter:
        query = query.where(CommunityChallenge.status == status_filter)
        if status_filter == ChallengeStatus.ACTIVE:
            query = query.where(*_challenge_window_filters(now))
    else:
        query = query.where(
            CommunityChallenge.status == ChallengeStatus.ACTIVE,
            *_challenge_window_filters(now),
        )

    result = await db.execute(query.order_by(CommunityChallenge.ends_at.asc()))
    return result.scalars().all()


@router.post("/admin/challenges", response_model=CommunityChallengeResponse, status_code=201)
async def create_admin_challenge(
    payload: CommunityChallengeCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new public community challenge."""
    _validate_challenge_window(payload.starts_at, payload.ends_at)

    challenge = CommunityChallenge(
        id=str(uuid.uuid4()),
        title=payload.title,
        title_zh=payload.title_zh,
        description=payload.description,
        description_zh=payload.description_zh,
        target_count=payload.target_count,
        category=payload.category,
        emoji=payload.emoji,
        status=payload.status,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    return challenge


@router.patch("/admin/challenges/{challenge_id}", response_model=CommunityChallengeResponse)
async def update_admin_challenge(
    challenge_id: str,
    payload: CommunityChallengeUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing public community challenge."""
    result = await db.execute(
        select(CommunityChallenge).where(CommunityChallenge.id == challenge_id)
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    update_data = payload.dict(exclude_unset=True)
    next_starts_at = update_data.get("starts_at", challenge.starts_at)
    next_ends_at = update_data.get("ends_at", challenge.ends_at)
    _validate_challenge_window(next_starts_at, next_ends_at)

    for field, value in update_data.items():
        setattr(challenge, field, value)

    await db.commit()
    await db.refresh(challenge)
    return challenge


@router.get(
    "/challenges/{challenge_id}/participations",
    response_model=List[ChallengeParticipationResponse],
)
async def list_challenge_participations(
    challenge_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all participation records for a challenge (leaderboard data)."""
    # Verify challenge exists
    ch_result = await db.execute(
        select(CommunityChallenge).where(CommunityChallenge.id == challenge_id)
    )
    challenge = ch_result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    result = await db.execute(
        select(ChallengeParticipation)
        .where(ChallengeParticipation.challenge_id == challenge_id)
        .order_by(ChallengeParticipation.progress.desc())
    )
    participations = result.scalars().all()

    return [
        ChallengeParticipationResponse(
            id=p.id,
            challenge_id=p.challenge_id,
            child_id=p.child_id,
            progress=p.progress,
            is_completed=p.is_completed,
            completed_at=p.completed_at,
            created_at=p.created_at,
            updated_at=p.updated_at,
            challenge_title=challenge.title,
            challenge_title_zh=challenge.title_zh,
            challenge_target=challenge.target_count,
            challenge_emoji=challenge.emoji,
        )
        for p in participations
    ]


@router.post(
    "/challenges/{challenge_id}/participate/{child_id}",
    response_model=ChallengeParticipationResponse,
    status_code=201,
)
async def join_or_update_challenge(
    challenge_id: str,
    child_id: str,
    payload: ChallengeProgressUpdate = ChallengeProgressUpdate(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Join a challenge (creates participation record) or increment progress if
    already participating.  Also marks the participation as completed when
    progress reaches the challenge target.
    """
    # Verify child
    child_result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not child_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    now = datetime.now(timezone.utc)

    # Verify challenge is active
    ch_result = await db.execute(
        select(CommunityChallenge).where(
            CommunityChallenge.id == challenge_id,
            CommunityChallenge.status == ChallengeStatus.ACTIVE,
            *_challenge_window_filters(now),
        )
    )
    challenge = ch_result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Active challenge not found")

    # Get or create participation
    part_result = await db.execute(
        select(ChallengeParticipation).where(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.child_id == child_id,
        )
    )
    participation = part_result.scalar_one_or_none()

    if not participation:
        participation = ChallengeParticipation(
            id=str(uuid.uuid4()),
            challenge_id=challenge_id,
            child_id=child_id,
            progress=0,
            is_completed=False,
        )
        db.add(participation)

    if not participation.is_completed:
        participation.progress = min(
            participation.progress + payload.increment,
            challenge.target_count,
        )
        participation.updated_at = datetime.now(timezone.utc)

        if participation.progress >= challenge.target_count and not participation.is_completed:
            participation.is_completed = True
            participation.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(participation)

    return ChallengeParticipationResponse(
        id=participation.id,
        challenge_id=participation.challenge_id,
        child_id=participation.child_id,
        progress=participation.progress,
        is_completed=participation.is_completed,
        completed_at=participation.completed_at,
        created_at=participation.created_at,
        updated_at=participation.updated_at,
        challenge_title=challenge.title,
        challenge_title_zh=challenge.title_zh,
        challenge_target=challenge.target_count,
        challenge_emoji=challenge.emoji,
    )


@router.get(
    "/challenges/{challenge_id}/my-progress/{child_id}",
    response_model=ChallengeParticipationResponse,
)
async def get_my_challenge_progress(
    challenge_id: str,
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's child's participation record for a challenge."""
    # Verify child
    child_result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not child_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    ch_result = await db.execute(
        select(CommunityChallenge).where(CommunityChallenge.id == challenge_id)
    )
    challenge = ch_result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    part_result = await db.execute(
        select(ChallengeParticipation).where(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.child_id == child_id,
        )
    )
    participation = part_result.scalar_one_or_none()
    if not participation:
        raise HTTPException(status_code=404, detail="Not participating in this challenge")

    return ChallengeParticipationResponse(
        id=participation.id,
        challenge_id=participation.challenge_id,
        child_id=participation.child_id,
        progress=participation.progress,
        is_completed=participation.is_completed,
        completed_at=participation.completed_at,
        created_at=participation.created_at,
        updated_at=participation.updated_at,
        challenge_title=challenge.title,
        challenge_title_zh=challenge.title_zh,
        challenge_target=challenge.target_count,
        challenge_emoji=challenge.emoji,
    )
