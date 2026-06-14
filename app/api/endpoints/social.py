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
from datetime import datetime, timezone, timedelta
import uuid

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.user import User, Child, UserRole
from app.core.child_age import calculate_child_age
from app.models.vocabulary import WordProgress, Word
from app.models.community import (
    ParentFriendship,
    FriendshipStatus,
    CommunityChallenge,
    ChallengeParticipation,
    ChallengeStatus,
    FriendChallenge,
    FriendChallengeParticipant,
    FriendChallengeMetric,
    FriendChallengeInviteStatus,
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
    CommunityChallengeResponse,
    CommunityChallengeUpdate,
    ChallengeParticipationResponse,
    ChallengeProgressUpdate,
    FriendChallengeCreate,
    FriendChallengeRespond,
    FriendChallengeResponse,
    FriendChallengeParticipantResponse,
    FriendChallengeViewStatus,
)

router = APIRouter()

MAX_ACTIVE_CREATED_FRIEND_CHALLENGES = 3


def _build_challenge_participation_response(
    participation: ChallengeParticipation,
    challenge: CommunityChallenge,
    *,
    child: Optional[Child] = None,
    parent_name: Optional[str] = None,
) -> ChallengeParticipationResponse:
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
        parent_name=parent_name,
        child_name=child.name if child else None,
        child_avatar=child.avatar if child else None,
        participant_code=None,
    )


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _friend_challenge_copy(metric_type: FriendChallengeMetric) -> tuple[str, str, str]:
    if metric_type == FriendChallengeMetric.PRACTICE_DAYS:
        return ("Practice Days Challenge", "練習天數挑戰", "🔥")
    if metric_type == FriendChallengeMetric.NEW_WORDS:
        return ("New Words Challenge", "新學詞語挑戰", "📚")
    return ("Active Usage Challenge", "主動活用挑戰", "⚡")


async def _compute_friend_metric_progress(
    db: AsyncSession,
    *,
    metric_type: FriendChallengeMetric,
    child_id: Optional[str],
    starts_at: datetime,
    ends_at: datetime,
) -> int:
    if not child_id:
        return 0

    starts_at_utc = _as_utc(starts_at)
    ends_at_utc = _as_utc(ends_at)

    if metric_type == FriendChallengeMetric.PRACTICE_DAYS:
        result = await db.execute(
            select(WordProgress.last_practiced).where(
                WordProgress.child_id == child_id,
                WordProgress.last_practiced.is_not(None),
                WordProgress.last_practiced >= starts_at_utc,
                WordProgress.last_practiced <= ends_at_utc,
            )
        )
        practiced_days = {
            _as_utc(ts).date()
            for ts in result.scalars().all()
            if ts is not None
        }
        return len(practiced_days)

    if metric_type == FriendChallengeMetric.NEW_WORDS:
        result = await db.execute(
            select(WordProgress.id).where(
                WordProgress.child_id == child_id,
                WordProgress.created_at >= starts_at_utc,
                WordProgress.created_at <= ends_at_utc,
            )
        )
        return len(result.scalars().all())

    result = await db.execute(
        select(WordProgress.word_id).where(
            WordProgress.child_id == child_id,
            WordProgress.active_vocab_requested_at.is_not(None),
            WordProgress.active_vocab_requested_at >= starts_at_utc,
            WordProgress.active_vocab_requested_at <= ends_at_utc,
        )
    )
    return len({word_id for word_id in result.scalars().all() if word_id})


async def _build_friend_challenge_response(
    db: AsyncSession,
    challenge: FriendChallenge,
    *,
    current_user_id: str,
) -> FriendChallengeResponse:
    creator_result = await db.execute(
        select(User).where(User.id == challenge.creator_id)
    )
    creator = creator_result.scalar_one_or_none()

    participant_result = await db.execute(
        select(FriendChallengeParticipant).where(
            FriendChallengeParticipant.challenge_id == challenge.id
        )
    )
    participant_rows = participant_result.scalars().all()

    now = datetime.now(timezone.utc)
    accepted_count = 0
    pending_count = 0
    my_invite_status = FriendChallengeInviteStatus.PENDING
    my_child_id: Optional[str] = None
    my_progress = 0
    my_completed = False
    participants_payload: List[FriendChallengeParticipantResponse] = []

    for row in participant_rows:
        if row.invite_status == FriendChallengeInviteStatus.ACCEPTED:
            accepted_count += 1
        elif row.invite_status == FriendChallengeInviteStatus.PENDING:
            pending_count += 1

        child = None
        if row.child_id:
            child_result = await db.execute(select(Child).where(Child.id == row.child_id))
            child = child_result.scalar_one_or_none()

        parent_result = await db.execute(select(User).where(User.id == row.parent_id))
        parent = parent_result.scalar_one_or_none()

        progress = await _compute_friend_metric_progress(
            db,
            metric_type=challenge.metric_type,
            child_id=row.child_id,
            starts_at=challenge.starts_at,
            ends_at=challenge.ends_at,
        )
        is_completed = progress >= challenge.target_count

        participants_payload.append(
            FriendChallengeParticipantResponse(
                id=row.id,
                parent_id=row.parent_id,
                parent_name=parent.full_name if parent else None,
                child_id=row.child_id,
                child_name=child.name if child else None,
                child_avatar=child.avatar if child else None,
                invite_status=row.invite_status,
                progress=progress,
                is_completed=is_completed,
            )
        )

        if row.parent_id == current_user_id:
            my_invite_status = row.invite_status
            my_child_id = row.child_id
            my_progress = progress
            my_completed = is_completed

    if my_invite_status == FriendChallengeInviteStatus.DECLINED:
        view_status = FriendChallengeViewStatus.DECLINED
    elif my_invite_status == FriendChallengeInviteStatus.PENDING:
        view_status = FriendChallengeViewStatus.PENDING
    elif now > _as_utc(challenge.ends_at):
        view_status = FriendChallengeViewStatus.EXPIRED
    elif my_completed:
        view_status = FriendChallengeViewStatus.COMPLETED
    else:
        view_status = FriendChallengeViewStatus.ACTIVE

    return FriendChallengeResponse(
        id=challenge.id,
        creator_id=challenge.creator_id,
        creator_name=creator.full_name if creator else None,
        title=challenge.title,
        title_zh=challenge.title_zh,
        metric_type=challenge.metric_type,
        target_count=challenge.target_count,
        duration_days=challenge.duration_days,
        emoji=challenge.emoji,
        starts_at=challenge.starts_at,
        ends_at=challenge.ends_at,
        created_at=challenge.created_at,
        accepted_participant_count=accepted_count,
        pending_participant_count=pending_count,
        my_invite_status=my_invite_status,
        my_child_id=my_child_id,
        my_progress=my_progress,
        my_completed=my_completed,
        view_status=view_status,
        participants=participants_payload,
    )


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
        if status_filter == ChallengeStatus.ACTIVE:
            query = query.where(
                CommunityChallenge.status == ChallengeStatus.ACTIVE,
                CommunityChallenge.starts_at <= now,
                CommunityChallenge.ends_at >= now,
            )
        elif status_filter == ChallengeStatus.EXPIRED:
            # Treat time-passed active rows as expired for read APIs.
            query = query.where(
                or_(
                    CommunityChallenge.status == ChallengeStatus.EXPIRED,
                    and_(
                        CommunityChallenge.status == ChallengeStatus.ACTIVE,
                        CommunityChallenge.ends_at < now,
                    ),
                )
            )
        else:
            query = query.where(CommunityChallenge.status == status_filter)
    else:
        query = query.where(
            CommunityChallenge.status == ChallengeStatus.ACTIVE,
            CommunityChallenge.starts_at <= now,
            CommunityChallenge.ends_at >= now,
        )

    result = await db.execute(query.order_by(CommunityChallenge.ends_at.asc()))
    return result.scalars().all()


@router.post("/challenges", response_model=CommunityChallengeResponse, status_code=201)
async def create_challenge(
    payload: CommunityChallengeCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new community challenge.

    In production this would be admin-only; for the demo any authenticated
    parent can create a challenge for their friend group.
    """
    challenge = CommunityChallenge(
        id=str(uuid.uuid4()),
        title=payload.title,
        title_zh=payload.title_zh,
        description=payload.description,
        description_zh=payload.description_zh,
        target_count=payload.target_count,
        category=payload.category,
        emoji=payload.emoji,
        status=ChallengeStatus.ACTIVE,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    return challenge


@router.get("/admin/challenges", response_model=List[CommunityChallengeResponse])
async def list_admin_challenges(
    status_filter: Optional[ChallengeStatus] = Query(
        None, alias="status", description="Filter by challenge status"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all community challenges for admin management."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = select(CommunityChallenge)
    if status_filter:
        query = query.where(CommunityChallenge.status == status_filter)

    result = await db.execute(query.order_by(CommunityChallenge.created_at.desc()))
    return result.scalars().all()


@router.post(
    "/admin/challenges",
    response_model=CommunityChallengeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_challenge(
    payload: CommunityChallengeCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a public challenge (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

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


@router.patch(
    "/admin/challenges/{challenge_id}",
    response_model=CommunityChallengeResponse,
)
async def update_admin_challenge(
    challenge_id: str,
    payload: CommunityChallengeUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing public challenge (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(
        select(CommunityChallenge).where(CommunityChallenge.id == challenge_id)
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(challenge, key, value)

    db.add(challenge)
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
        select(
            ChallengeParticipation,
            Child,
            User.full_name.label("parent_name"),
        )
        .join(Child, ChallengeParticipation.child_id == Child.id)
        .join(User, Child.parent_id == User.id, isouter=True)
        .where(ChallengeParticipation.challenge_id == challenge_id)
        .order_by(ChallengeParticipation.progress.desc())
    )
    participations = result.all()

    return [
        _build_challenge_participation_response(
            participation,
            challenge,
            child=child,
            parent_name=parent_name,
        )
        for participation, child, parent_name in participations
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
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify challenge is active
    ch_result = await db.execute(
        select(CommunityChallenge).where(
            CommunityChallenge.id == challenge_id,
            CommunityChallenge.status == ChallengeStatus.ACTIVE,
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

    return _build_challenge_participation_response(
        participation,
        challenge,
        child=child,
        parent_name=current_user.full_name,
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
    child = child_result.scalar_one_or_none()
    if not child:
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

    return _build_challenge_participation_response(
        participation,
        challenge,
        child=child,
        parent_name=current_user.full_name,
    )


# ===========================================================================
# 10.2.4  Private Friend Challenges
# ===========================================================================

@router.get("/friend-challenges", response_model=List[FriendChallengeResponse])
async def list_friend_challenges(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List private friend challenges for the current parent."""
    participant_result = await db.execute(
        select(FriendChallengeParticipant.challenge_id).where(
            FriendChallengeParticipant.parent_id == current_user.id
        )
    )
    participant_challenge_ids = participant_result.scalars().all()

    query = select(FriendChallenge).where(
        or_(
            FriendChallenge.creator_id == current_user.id,
            FriendChallenge.id.in_(participant_challenge_ids)
            if participant_challenge_ids
            else False,
        )
    )
    result = await db.execute(query.order_by(FriendChallenge.created_at.desc()))
    challenges = result.scalars().all()

    payload: List[FriendChallengeResponse] = []
    for challenge in challenges:
        payload.append(
            await _build_friend_challenge_response(
                db,
                challenge,
                current_user_id=current_user.id,
            )
        )
    return payload


@router.post(
    "/friend-challenges",
    response_model=FriendChallengeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_friend_challenge(
    payload: FriendChallengeCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a private challenge and invite accepted friends."""
    child_result = await db.execute(
        select(Child).where(
            Child.id == payload.child_id,
            Child.parent_id == current_user.id,
        )
    )
    creator_child = child_result.scalar_one_or_none()
    if not creator_child:
        raise HTTPException(status_code=404, detail="Child not found")

    invited_ids = list({parent_id for parent_id in payload.invited_parent_ids if parent_id})
    invited_ids = [parent_id for parent_id in invited_ids if parent_id != current_user.id]
    if not invited_ids:
        raise HTTPException(status_code=400, detail="At least one friend must be invited")

    friendship_result = await db.execute(
        select(ParentFriendship).where(
            ParentFriendship.status == FriendshipStatus.ACCEPTED,
            or_(
                and_(
                    ParentFriendship.requester_id == current_user.id,
                    ParentFriendship.addressee_id.in_(invited_ids),
                ),
                and_(
                    ParentFriendship.addressee_id == current_user.id,
                    ParentFriendship.requester_id.in_(invited_ids),
                ),
            ),
        )
    )
    friendships = friendship_result.scalars().all()
    accepted_friend_ids = {
        f.addressee_id if f.requester_id == current_user.id else f.requester_id
        for f in friendships
    }
    missing_ids = [parent_id for parent_id in invited_ids if parent_id not in accepted_friend_ids]
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail="All invited parents must be accepted friends",
        )

    now = datetime.now(timezone.utc)

    active_created_result = await db.execute(
        select(FriendChallenge).where(
            FriendChallenge.creator_id == current_user.id,
            FriendChallenge.ends_at > now,
        )
    )
    active_created = active_created_result.scalars().all()

    if len(active_created) >= MAX_ACTIVE_CREATED_FRIEND_CHALLENGES:
        raise HTTPException(
            status_code=400,
            detail=(
                "You already have too many active friend challenges. "
                "Please finish or wait for current ones to end before creating new ones."
            ),
        )

    invited_id_set = set(invited_ids)
    for existing_challenge in active_created:
        existing_participants_result = await db.execute(
            select(FriendChallengeParticipant).where(
                FriendChallengeParticipant.challenge_id == existing_challenge.id
            )
        )
        existing_participants = existing_participants_result.scalars().all()

        existing_invited_ids = {
            p.parent_id for p in existing_participants if p.parent_id != current_user.id
        }
        pending_overlap = any(
            p.parent_id in invited_id_set
            and p.invite_status == FriendChallengeInviteStatus.PENDING
            for p in existing_participants
        )
        if pending_overlap:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Some selected friends already have a pending invite from you. "
                    "Wait for their response before sending another challenge."
                ),
            )

        creator_participant = next(
            (p for p in existing_participants if p.parent_id == current_user.id),
            None,
        )
        is_exact_duplicate = (
            existing_challenge.metric_type == payload.metric_type
            and existing_challenge.target_count == payload.target_count
            and existing_challenge.duration_days == payload.duration_days
            and creator_participant is not None
            and creator_participant.child_id == payload.child_id
            and existing_invited_ids == invited_id_set
        )
        if is_exact_duplicate:
            raise HTTPException(
                status_code=409,
                detail="An equivalent active friend challenge already exists.",
            )

    ends_at = now + timedelta(days=payload.duration_days)
    title, title_zh, emoji = _friend_challenge_copy(payload.metric_type)

    challenge = FriendChallenge(
        id=str(uuid.uuid4()),
        creator_id=current_user.id,
        title=title,
        title_zh=title_zh,
        metric_type=payload.metric_type,
        target_count=payload.target_count,
        duration_days=payload.duration_days,
        emoji=emoji,
        starts_at=now,
        ends_at=ends_at,
    )
    db.add(challenge)
    await db.flush()

    db.add(
        FriendChallengeParticipant(
            id=str(uuid.uuid4()),
            challenge_id=challenge.id,
            parent_id=current_user.id,
            child_id=payload.child_id,
            invite_status=FriendChallengeInviteStatus.ACCEPTED,
            responded_at=now,
        )
    )

    for parent_id in invited_ids:
        db.add(
            FriendChallengeParticipant(
                id=str(uuid.uuid4()),
                challenge_id=challenge.id,
                parent_id=parent_id,
                child_id=None,
                invite_status=FriendChallengeInviteStatus.PENDING,
            )
        )

    await db.commit()
    await db.refresh(challenge)

    return await _build_friend_challenge_response(
        db,
        challenge,
        current_user_id=current_user.id,
    )


@router.post(
    "/friend-challenges/{challenge_id}/respond",
    response_model=FriendChallengeResponse,
)
async def respond_to_friend_challenge(
    challenge_id: str,
    payload: FriendChallengeRespond,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept or decline a private friend challenge invite."""
    if payload.invite_status not in (
        FriendChallengeInviteStatus.ACCEPTED,
        FriendChallengeInviteStatus.DECLINED,
    ):
        raise HTTPException(status_code=400, detail="invite_status must be accepted or declined")

    challenge_result = await db.execute(
        select(FriendChallenge).where(FriendChallenge.id == challenge_id)
    )
    challenge = challenge_result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Friend challenge not found")

    participant_result = await db.execute(
        select(FriendChallengeParticipant).where(
            FriendChallengeParticipant.challenge_id == challenge_id,
            FriendChallengeParticipant.parent_id == current_user.id,
        )
    )
    participant = participant_result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Invite not found")

    selected_child_id: Optional[str] = None
    if payload.invite_status == FriendChallengeInviteStatus.ACCEPTED:
        if not payload.child_id:
            raise HTTPException(status_code=400, detail="child_id is required when accepting")
        child_result = await db.execute(
            select(Child).where(
                Child.id == payload.child_id,
                Child.parent_id == current_user.id,
            )
        )
        child = child_result.scalar_one_or_none()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        selected_child_id = payload.child_id

    participant.invite_status = payload.invite_status
    participant.child_id = selected_child_id
    participant.responded_at = datetime.now(timezone.utc)
    db.add(participant)
    await db.commit()

    return await _build_friend_challenge_response(
        db,
        challenge,
        current_user_id=current_user.id,
    )
