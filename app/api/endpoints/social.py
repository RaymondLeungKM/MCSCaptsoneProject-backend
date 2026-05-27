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
from sqlalchemy import select, or_, and_, func
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import uuid

from app.db.session import get_db
from app.core.security import get_current_active_user, get_current_admin_user
from app.models.user import User, Child
from app.core.child_age import calculate_child_age
from app.models.vocabulary import WordProgress, Word
from app.models.daily_words import DailyWordTracking
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
    CommunityChallengeUpdate,
    CommunityChallengeResponse,
    ChallengeParticipationResponse,
    ChallengeProgressUpdate,
    FriendChallengeCreate,
    FriendChallengeRespond,
    FriendChallengeResponse,
    FriendChallengeParticipantResponse,
    FriendChallengeViewStatus,
)

router = APIRouter()


def _friend_challenge_template(
    metric_type: FriendChallengeMetric,
    target_count: int,
) -> tuple[str, str, str]:
    if metric_type == FriendChallengeMetric.PRACTICE_DAYS:
        return (
            f"Practice for {target_count} days",
            f"連續練習 {target_count} 天",
            "📅",
        )
    if metric_type == FriendChallengeMetric.NEW_WORDS:
        return (
            f"Learn {target_count} new words",
            f"學習 {target_count} 個新詞語",
            "📚",
        )
    return (
        f"Use {target_count} words actively",
        f"活用 {target_count} 個詞語",
        "🗣️",
    )


async def _get_accepted_friend_ids(
    current_user_id: str,
    db: AsyncSession,
) -> set[str]:
    result = await db.execute(
        select(ParentFriendship).where(
            or_(
                ParentFriendship.requester_id == current_user_id,
                ParentFriendship.addressee_id == current_user_id,
            ),
            ParentFriendship.status == FriendshipStatus.ACCEPTED,
        )
    )
    friendships = result.scalars().all()
    return {
        f.addressee_id if f.requester_id == current_user_id else f.requester_id
        for f in friendships
    }


async def _compute_friend_challenge_progress(
    child_id: str,
    metric_type: FriendChallengeMetric,
    starts_at: datetime,
    ends_at: datetime,
    db: AsyncSession,
) -> int:
    base_filters = and_(
        DailyWordTracking.child_id == child_id,
        DailyWordTracking.date >= starts_at,
        DailyWordTracking.date <= ends_at,
    )

    if metric_type == FriendChallengeMetric.PRACTICE_DAYS:
        result = await db.execute(
            select(func.count(func.distinct(func.date(DailyWordTracking.date)))).where(
                base_filters
            )
        )
        return int(result.scalar() or 0)

    if metric_type == FriendChallengeMetric.ACTIVE_WORDS:
        result = await db.execute(
            select(func.count(func.distinct(DailyWordTracking.word_id))).where(
                and_(base_filters, DailyWordTracking.used_actively == True)
            )
        )
        return int(result.scalar() or 0)

    first_seen_subquery = (
        select(
            DailyWordTracking.word_id.label("word_id"),
            func.min(DailyWordTracking.date).label("first_seen"),
        )
        .where(DailyWordTracking.child_id == child_id)
        .group_by(DailyWordTracking.word_id)
        .subquery()
    )
    result = await db.execute(
        select(func.count())
        .select_from(first_seen_subquery)
        .where(
            and_(
                first_seen_subquery.c.first_seen >= starts_at,
                first_seen_subquery.c.first_seen <= ends_at,
            )
        )
    )
    return int(result.scalar() or 0)


def _derive_friend_challenge_view_status(
    invite_status: FriendChallengeInviteStatus,
    progress: int,
    target_count: int,
    ends_at: datetime,
) -> FriendChallengeViewStatus:
    if invite_status == FriendChallengeInviteStatus.PENDING:
        return FriendChallengeViewStatus.PENDING
    if invite_status == FriendChallengeInviteStatus.DECLINED:
        return FriendChallengeViewStatus.DECLINED
    if progress >= target_count:
        return FriendChallengeViewStatus.COMPLETED
    if ends_at < datetime.now(timezone.utc):
        return FriendChallengeViewStatus.EXPIRED
    return FriendChallengeViewStatus.ACTIVE


async def _build_friend_challenge_response(
    challenge: FriendChallenge,
    current_user_id: str,
    db: AsyncSession,
) -> FriendChallengeResponse:
    participant_result = await db.execute(
        select(FriendChallengeParticipant).where(
            FriendChallengeParticipant.challenge_id == challenge.id
        )
    )
    participant_rows = participant_result.scalars().all()

    parent_ids = {challenge.creator_id, *(p.parent_id for p in participant_rows)}
    child_ids = {p.child_id for p in participant_rows if p.child_id}

    user_map: dict[str, User] = {}
    if parent_ids:
        user_result = await db.execute(select(User).where(User.id.in_(parent_ids)))
        user_map = {user.id: user for user in user_result.scalars().all()}

    child_map: dict[str, Child] = {}
    if child_ids:
        child_result = await db.execute(select(Child).where(Child.id.in_(child_ids)))
        child_map = {child.id: child for child in child_result.scalars().all()}

    accepted_count = 0
    pending_count = 0
    my_invite_status = FriendChallengeInviteStatus.PENDING
    my_child_id: Optional[str] = None
    my_progress = 0
    my_completed = False
    participants: List[FriendChallengeParticipantResponse] = []

    for participant in participant_rows:
        progress = 0
        is_completed = False
        child = child_map.get(participant.child_id) if participant.child_id else None

        if participant.invite_status == FriendChallengeInviteStatus.ACCEPTED:
            accepted_count += 1
            if participant.child_id:
                progress = await _compute_friend_challenge_progress(
                    participant.child_id,
                    challenge.metric_type,
                    challenge.starts_at,
                    challenge.ends_at,
                    db,
                )
                is_completed = progress >= challenge.target_count
        elif participant.invite_status == FriendChallengeInviteStatus.PENDING:
            pending_count += 1

        if participant.parent_id == current_user_id:
            my_invite_status = participant.invite_status
            my_child_id = participant.child_id
            my_progress = progress
            my_completed = is_completed

        participants.append(
            FriendChallengeParticipantResponse(
                id=participant.id,
                parent_id=participant.parent_id,
                parent_name=user_map.get(participant.parent_id).full_name
                if user_map.get(participant.parent_id)
                else None,
                child_id=participant.child_id,
                child_name=child.name if child else None,
                child_avatar=child.avatar if child else None,
                invite_status=participant.invite_status,
                progress=progress,
                is_completed=is_completed,
            )
        )

    return FriendChallengeResponse(
        id=challenge.id,
        creator_id=challenge.creator_id,
        creator_name=user_map.get(challenge.creator_id).full_name
        if user_map.get(challenge.creator_id)
        else None,
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
        view_status=_derive_friend_challenge_view_status(
            my_invite_status,
            my_progress,
            challenge.target_count,
            challenge.ends_at,
        ),
        participants=participants,
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
# 10.2.3  Private Friend Challenges
# ===========================================================================

@router.get("/friend-challenges", response_model=List[FriendChallengeResponse])
async def list_friend_challenges(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    created_result = await db.execute(
        select(FriendChallenge).where(FriendChallenge.creator_id == current_user.id)
    )
    created_challenges = created_result.scalars().all()

    invited_result = await db.execute(
        select(FriendChallengeParticipant.challenge_id).where(
            FriendChallengeParticipant.parent_id == current_user.id,
            FriendChallengeParticipant.invite_status
            != FriendChallengeInviteStatus.DECLINED,
        )
    )
    visible_ids = {challenge.id for challenge in created_challenges}
    visible_ids.update(invited_result.scalars().all())

    if not visible_ids:
        return []

    challenge_result = await db.execute(
        select(FriendChallenge)
        .where(FriendChallenge.id.in_(visible_ids))
        .order_by(FriendChallenge.created_at.desc())
    )
    challenges = challenge_result.scalars().all()

    responses = [
        await _build_friend_challenge_response(challenge, current_user.id, db)
        for challenge in challenges
    ]

    status_priority = {
        FriendChallengeViewStatus.PENDING: 0,
        FriendChallengeViewStatus.ACTIVE: 1,
        FriendChallengeViewStatus.COMPLETED: 2,
        FriendChallengeViewStatus.EXPIRED: 3,
        FriendChallengeViewStatus.DECLINED: 4,
    }
    responses.sort(
        key=lambda challenge: (
            status_priority.get(challenge.view_status, 99),
            challenge.ends_at,
        )
    )
    return responses


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
    invited_parent_ids = list(dict.fromkeys(payload.invited_parent_ids))
    if not invited_parent_ids:
        raise HTTPException(status_code=400, detail="Select at least one friend")
    if len(invited_parent_ids) > 5:
        raise HTTPException(status_code=400, detail="You can invite up to 5 friends")
    if current_user.id in invited_parent_ids:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    child_result = await db.execute(
        select(Child).where(Child.id == payload.child_id, Child.parent_id == current_user.id)
    )
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    accepted_friend_ids = await _get_accepted_friend_ids(current_user.id, db)
    invalid_friend_ids = [
        parent_id for parent_id in invited_parent_ids if parent_id not in accepted_friend_ids
    ]
    if invalid_friend_ids:
        raise HTTPException(
            status_code=400,
            detail="All invited parents must already be accepted friends",
        )

    starts_at = datetime.now(timezone.utc)
    ends_at = starts_at + timedelta(days=payload.duration_days)
    title, title_zh, emoji = _friend_challenge_template(
        payload.metric_type,
        payload.target_count,
    )

    challenge = FriendChallenge(
        id=str(uuid.uuid4()),
        creator_id=current_user.id,
        title=title,
        title_zh=title_zh,
        metric_type=payload.metric_type,
        target_count=payload.target_count,
        duration_days=payload.duration_days,
        emoji=emoji,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(challenge)
    db.add(
        FriendChallengeParticipant(
            id=str(uuid.uuid4()),
            challenge_id=challenge.id,
            parent_id=current_user.id,
            child_id=child.id,
            invite_status=FriendChallengeInviteStatus.ACCEPTED,
            responded_at=starts_at,
        )
    )

    for parent_id in invited_parent_ids:
        db.add(
            FriendChallengeParticipant(
                id=str(uuid.uuid4()),
                challenge_id=challenge.id,
                parent_id=parent_id,
                invite_status=FriendChallengeInviteStatus.PENDING,
            )
        )

    await db.commit()
    await db.refresh(challenge)
    return await _build_friend_challenge_response(challenge, current_user.id, db)


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
    challenge_result = await db.execute(
        select(FriendChallenge).where(FriendChallenge.id == challenge_id)
    )
    challenge = challenge_result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    participant_result = await db.execute(
        select(FriendChallengeParticipant).where(
            FriendChallengeParticipant.challenge_id == challenge_id,
            FriendChallengeParticipant.parent_id == current_user.id,
        )
    )
    participant = participant_result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Invite not found")

    if participant.invite_status != FriendChallengeInviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invite has already been answered")

    if payload.invite_status not in (
        FriendChallengeInviteStatus.ACCEPTED,
        FriendChallengeInviteStatus.DECLINED,
    ):
        raise HTTPException(status_code=400, detail="Invite response must be accepted or declined")

    if challenge.ends_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This challenge has already ended")

    if payload.invite_status == FriendChallengeInviteStatus.ACCEPTED:
        if not payload.child_id:
            raise HTTPException(status_code=400, detail="Choose a child to join this challenge")
        child_result = await db.execute(
            select(Child).where(
                Child.id == payload.child_id,
                Child.parent_id == current_user.id,
            )
        )
        child = child_result.scalar_one_or_none()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        participant.child_id = child.id
    else:
        participant.child_id = None

    participant.invite_status = payload.invite_status
    participant.responded_at = datetime.now(timezone.utc)
    db.add(participant)
    await db.commit()

    return await _build_friend_challenge_response(challenge, current_user.id, db)


# ===========================================================================
# 10.2.4  Community Challenges
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
