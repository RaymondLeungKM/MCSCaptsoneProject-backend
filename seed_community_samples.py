"""
Seed sample community data for testing the child community feed.

This script is idempotent. It:
1. Ensures a couple of sample parent/child accounts exist.
2. Enables community sharing for all existing children.
3. Creates approved sample community posts for each child.
4. Creates one pending sample post for the first existing child to test moderation.
5. Adds a few star reactions so the feed looks populated.
6. Seeds sample public community challenges and a small leaderboard.

Usage:
  ./venv/bin/python seed_community_samples.py
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, DailyStats, LearningSession  # noqa: F401
from app.models.community import (
    ChallengeParticipation,
    ChallengeStatus,
    CommunityChallenge,
    CommunityPost,
    ModerationStatus,
    PostReaction,
)
from app.models.content import Game, Mission, Story  # noqa: F401
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    DailyLearningStats,
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.user import (
    Child,
    LanguagePreference,
    LearningStyle,
    TimeOfDay,
    User,
    UserRole,
)
from app.models.vocabulary import Word


SAMPLE_PARENTS = [
    {
        "id": "sample-parent-community-1",
        "email": "community.parent.one@example.com",
        "full_name": "Community Sample Parent One",
    },
    {
        "id": "sample-parent-community-2",
        "email": "community.parent.two@example.com",
        "full_name": "Community Sample Parent Two",
    },
]

SAMPLE_CHILDREN = [
    {
        "id": "sample-child-community-1",
        "parent_id": "sample-parent-community-1",
        "name": "晴晴",
        "avatar": "🦊",
        "age": 5,
        "level": 4,
        "xp": 180,
        "words_learned": 28,
    },
    {
        "id": "sample-child-community-2",
        "parent_id": "sample-parent-community-2",
        "name": "朗朗",
        "avatar": "🐻",
        "age": 6,
        "level": 5,
        "xp": 240,
        "words_learned": 34,
    },
]

WORD_PREFERENCES = [
    "Apple",
    "Banana",
    "Cat",
    "Dog",
    "Ball",
    "Book",
    "Bus",
    "Car",
    "Rabbit",
    "Water Bottle",
    "Lunchbox",
    "Flower",
]

DEFAULT_PASSWORD = "CommunityDemo123!"

SAMPLE_CHALLENGES = [
    {
        "id": "sample-community-challenge-color-hunt",
        "title": "Color Hunt Week",
        "title_zh": "顏色尋寶週",
        "description": "Find colorful objects around home and say their names in Cantonese.",
        "description_zh": "在屋企搵唔同顏色嘅物件，再用廣東話講出名稱。",
        "target_count": 6,
        "category": "observation",
        "emoji": "🌈",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -1,
        "ends_in_days": 6,
        "created_in_days": -2,
    },
    {
        "id": "sample-community-challenge-home-talk",
        "title": "Home Talk Sprint",
        "title_zh": "屋企講多啲",
        "description": "Use Cantonese to describe everyday objects during one family routine each day.",
        "description_zh": "每日揀一段家庭日常時間，用廣東話形容身邊物件。",
        "target_count": 5,
        "category": "speaking",
        "emoji": "🗣️",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -2,
        "ends_in_days": 10,
        "created_in_days": -4,
    },
    {
        "id": "sample-community-challenge-bedtime-retell",
        "title": "Bedtime Retell Stars",
        "title_zh": "睡前故事星星",
        "description": "Retell a short bedtime story in Cantonese before sleep and collect stars.",
        "description_zh": "睡前用廣東話重講短故事，儲起故事星星。",
        "target_count": 4,
        "category": "stories",
        "emoji": "🌙",
        "status": ChallengeStatus.COMPLETED,
        "starts_in_days": -14,
        "ends_in_days": -3,
        "created_in_days": -16,
    },
    {
        "id": "sample-community-challenge-word-detective",
        "title": "Word Detective",
        "title_zh": "詞語小偵探",
        "description": "Spot target objects in the real world and report back with their Cantonese names.",
        "description_zh": "在真實生活入面搵目標物件，再講返佢哋嘅廣東話名稱。",
        "target_count": 8,
        "category": "vocabulary",
        "emoji": "🔎",
        "status": ChallengeStatus.EXPIRED,
        "starts_in_days": -20,
        "ends_in_days": -10,
        "created_in_days": -22,
    },
]


def _safe_id_fragment(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def _is_real_image_url(value: str | None) -> bool:
    return bool(
        value and (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("/")
        )
    )


async def _get_or_create_parent(db, payload: dict) -> User:
    result = await db.execute(select(User).where(User.id == payload["id"]))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=payload["id"],
            email=payload["email"],
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            full_name=payload["full_name"],
            role=UserRole.PARENT,
            is_active=True,
            consent_given=True,
            consent_camera=True,
            consent_microphone=True,
            consent_analytics=True,
            consent_given_at=datetime.now(timezone.utc),
        )
        db.add(user)
        return user

    user.email = payload["email"]
    user.full_name = payload["full_name"]
    user.role = UserRole.PARENT
    user.is_active = True
    user.consent_given = True
    user.consent_camera = True
    user.consent_microphone = True
    user.consent_analytics = True
    if not user.hashed_password:
        user.hashed_password = get_password_hash(DEFAULT_PASSWORD)
    if not user.consent_given_at:
        user.consent_given_at = datetime.now(timezone.utc)
    return user


async def _get_or_create_child(db, payload: dict) -> Child:
    result = await db.execute(select(Child).where(Child.id == payload["id"]))
    child = result.scalar_one_or_none()

    if child is None:
        child = Child(
            id=payload["id"],
            parent_id=payload["parent_id"],
            name=payload["name"],
            avatar=payload["avatar"],
            age=payload["age"],
            birth_year=2020 - payload["age"],
            birth_month=6,
            level=payload["level"],
            xp=payload["xp"],
            words_learned=payload["words_learned"],
            daily_goal=5,
            today_progress=3,
            learning_style=LearningStyle.MIXED,
            language_preference=LanguagePreference.CANTONESE,
            attention_span=15,
            preferred_time_of_day=TimeOfDay.EVENING,
            community_sharing_enabled=True,
            last_active=datetime.now(timezone.utc),
        )
        db.add(child)
        return child

    child.parent_id = payload["parent_id"]
    child.name = payload["name"]
    child.avatar = payload["avatar"]
    child.age = payload["age"]
    child.level = payload["level"]
    child.xp = payload["xp"]
    child.words_learned = payload["words_learned"]
    child.language_preference = LanguagePreference.CANTONESE
    child.learning_style = LearningStyle.MIXED
    child.preferred_time_of_day = TimeOfDay.EVENING
    child.community_sharing_enabled = True
    child.last_active = datetime.now(timezone.utc)
    return child


def _pick_words(words: list[Word], start: int, count: int) -> list[Word]:
    if not words:
        return []
    return [words[(start + index) % len(words)] for index in range(count)]


async def _upsert_post(
    db,
    *,
    post_id: str,
    child_id: str,
    word: Word,
    status: ModerationStatus,
    created_at: datetime,
    caption: str,
) -> CommunityPost:
    if not _is_real_image_url(word.image_url):
        raise ValueError(f"Word '{word.word}' does not have a usable image URL")

    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()

    if post is None:
        post = CommunityPost(
            id=post_id,
            child_id=child_id,
            word_id=word.id,
            word_text=word.word,
            word_text_cantonese=word.word_cantonese,
            caption=caption,
            image_url=word.image_url,
            is_anonymous=True,
            moderation_status=status,
            reaction_count=0,
            created_at=created_at,
            moderated_at=created_at if status == ModerationStatus.APPROVED else None,
        )
        db.add(post)
        return post

    post.child_id = child_id
    post.word_id = word.id
    post.word_text = word.word
    post.word_text_cantonese = word.word_cantonese
    post.caption = caption
    post.image_url = word.image_url
    post.is_anonymous = True
    post.moderation_status = status
    post.created_at = created_at
    post.moderated_at = created_at if status == ModerationStatus.APPROVED else None
    post.moderation_note = None
    post.reaction_count = 0
    return post


async def _upsert_challenge(db, payload: dict, *, now: datetime) -> CommunityChallenge:
    starts_at = now + timedelta(days=payload["starts_in_days"])
    ends_at = now + timedelta(days=payload["ends_in_days"])
    created_at = now + timedelta(days=payload["created_in_days"])

    result = await db.execute(
        select(CommunityChallenge).where(CommunityChallenge.id == payload["id"])
    )
    challenge = result.scalar_one_or_none()

    if challenge is None:
        challenge = CommunityChallenge(
            id=payload["id"],
            title=payload["title"],
            title_zh=payload["title_zh"],
            description=payload["description"],
            description_zh=payload["description_zh"],
            target_count=payload["target_count"],
            category=payload["category"],
            emoji=payload["emoji"],
            status=payload["status"],
            starts_at=starts_at,
            ends_at=ends_at,
            created_at=created_at,
        )
        db.add(challenge)
        return challenge

    challenge.title = payload["title"]
    challenge.title_zh = payload["title_zh"]
    challenge.description = payload["description"]
    challenge.description_zh = payload["description_zh"]
    challenge.target_count = payload["target_count"]
    challenge.category = payload["category"]
    challenge.emoji = payload["emoji"]
    challenge.status = payload["status"]
    challenge.starts_at = starts_at
    challenge.ends_at = ends_at
    challenge.created_at = created_at
    return challenge


async def _upsert_participation(
    db,
    *,
    challenge_id: str,
    child_id: str,
    progress: int,
    is_completed: bool,
    created_at: datetime,
    updated_at: datetime,
    completed_at: datetime | None = None,
) -> ChallengeParticipation:
    result = await db.execute(
        select(ChallengeParticipation).where(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.child_id == child_id,
        )
    )
    participation = result.scalar_one_or_none()

    if participation is None:
        participation = ChallengeParticipation(
            id=f"sample-challenge-participation-{_safe_id_fragment(challenge_id)}-{_safe_id_fragment(child_id)}",
            challenge_id=challenge_id,
            child_id=child_id,
            progress=progress,
            is_completed=is_completed,
            completed_at=completed_at,
            created_at=created_at,
            updated_at=updated_at,
        )
        db.add(participation)
        return participation

    participation.progress = progress
    participation.is_completed = is_completed
    participation.completed_at = completed_at
    participation.created_at = created_at
    participation.updated_at = updated_at
    return participation


async def seed_community_samples() -> None:
    async with AsyncSessionLocal() as db:
        for parent_payload in SAMPLE_PARENTS:
            await _get_or_create_parent(db, parent_payload)

        for child_payload in SAMPLE_CHILDREN:
            await _get_or_create_child(db, child_payload)

        await db.flush()

        existing_children_result = await db.execute(select(Child).order_by(Child.created_at.asc(), Child.id.asc()))
        all_children = list(existing_children_result.scalars().all())
        for child in all_children:
            child.community_sharing_enabled = True

        preferred_words_result = await db.execute(
            select(Word)
            .where(Word.word.in_(WORD_PREFERENCES), Word.image_url.isnot(None), Word.image_url != "")
            .order_by(Word.word.asc())
        )
        preferred_words = [
            word for word in preferred_words_result.scalars().all() if _is_real_image_url(word.image_url)
        ]

        if len(preferred_words) < 6:
            fallback_words_result = await db.execute(
                select(Word)
                .where(Word.image_url.isnot(None), Word.image_url != "")
                .order_by(Word.word.asc())
                .limit(18)
            )
            seen_ids = {word.id for word in preferred_words}
            for word in fallback_words_result.scalars().all():
                if word.id not in seen_ids and _is_real_image_url(word.image_url):
                    preferred_words.append(word)
                    seen_ids.add(word.id)

        sample_post_ids: list[str] = []
        approved_posts: list[CommunityPost] = []
        pending_post_count = 0
        now = datetime.now(timezone.utc)
        base_children = [child for child in all_children if child.community_sharing_enabled]
        can_seed_posts = len(preferred_words) >= 3

        if can_seed_posts:
            for index, child in enumerate(base_children):
                selected_words = _pick_words(preferred_words, index * 2, 2)
                for offset, word in enumerate(selected_words):
                    post_id = f"sample-community-approved-{_safe_id_fragment(child.id)}-{_safe_id_fragment(str(word.id))}"
                    sample_post_ids.append(post_id)
                    await _upsert_post(
                        db,
                        post_id=post_id,
                        child_id=child.id,
                        word=word,
                        status=ModerationStatus.APPROVED,
                        created_at=now - timedelta(days=index, hours=offset * 6 + 2),
                        caption=f"sample-community:approved:{child.id}:{word.word}",
                    )

            first_real_child = next(
                (child for child in base_children if not child.id.startswith("sample-child-community-")),
                base_children[0],
            )
            pending_word = _pick_words(preferred_words, len(base_children), 1)[0]
            pending_post_id = f"sample-community-pending-{_safe_id_fragment(first_real_child.id)}-{_safe_id_fragment(str(pending_word.id))}"
            sample_post_ids.append(pending_post_id)
            await _upsert_post(
                db,
                post_id=pending_post_id,
                child_id=first_real_child.id,
                word=pending_word,
                status=ModerationStatus.PENDING,
                created_at=now - timedelta(hours=3),
                caption=f"sample-community:pending:{first_real_child.id}:{pending_word.word}",
            )
            pending_post_count = 1

            await db.flush()

        seeded_challenges: list[CommunityChallenge] = []
        for challenge_payload in SAMPLE_CHALLENGES:
            seeded_challenges.append(
                await _upsert_challenge(db, challenge_payload, now=now)
            )

        leaderboard_children = base_children[: min(3, len(base_children))]
        challenge_by_id = {challenge.id: challenge for challenge in seeded_challenges}

        if leaderboard_children:
            active_primary = challenge_by_id["sample-community-challenge-color-hunt"]
            active_secondary = challenge_by_id["sample-community-challenge-home-talk"]
            completed_story = challenge_by_id["sample-community-challenge-bedtime-retell"]
            expired_detective = challenge_by_id["sample-community-challenge-word-detective"]

            sample_progress_rows = [
                {
                    "challenge": active_primary,
                    "child": leaderboard_children[0],
                    "progress": min(active_primary.target_count, active_primary.target_count - 1),
                    "is_completed": False,
                    "updated_at": now - timedelta(hours=4),
                },
                {
                    "challenge": active_secondary,
                    "child": leaderboard_children[0],
                    "progress": min(active_secondary.target_count, 2),
                    "is_completed": False,
                    "updated_at": now - timedelta(hours=7),
                },
                {
                    "challenge": completed_story,
                    "child": leaderboard_children[0],
                    "progress": completed_story.target_count,
                    "is_completed": True,
                    "completed_at": now - timedelta(days=4),
                    "updated_at": now - timedelta(days=4),
                },
                {
                    "challenge": expired_detective,
                    "child": leaderboard_children[0],
                    "progress": min(expired_detective.target_count, 5),
                    "is_completed": False,
                    "updated_at": now - timedelta(days=11),
                },
            ]

            if len(leaderboard_children) > 1:
                sample_progress_rows.extend(
                    [
                        {
                            "challenge": active_primary,
                            "child": leaderboard_children[1],
                            "progress": min(active_primary.target_count, 3),
                            "is_completed": False,
                            "updated_at": now - timedelta(hours=9),
                        },
                        {
                            "challenge": active_secondary,
                            "child": leaderboard_children[1],
                            "progress": min(active_secondary.target_count, active_secondary.target_count - 1),
                            "is_completed": False,
                            "updated_at": now - timedelta(hours=2),
                        },
                        {
                            "challenge": completed_story,
                            "child": leaderboard_children[1],
                            "progress": completed_story.target_count,
                            "is_completed": True,
                            "completed_at": now - timedelta(days=5),
                            "updated_at": now - timedelta(days=5),
                        },
                    ]
                )

            if len(leaderboard_children) > 2:
                sample_progress_rows.extend(
                    [
                        {
                            "challenge": active_primary,
                            "child": leaderboard_children[2],
                            "progress": min(active_primary.target_count, 1),
                            "is_completed": False,
                            "updated_at": now - timedelta(hours=12),
                        },
                        {
                            "challenge": expired_detective,
                            "child": leaderboard_children[2],
                            "progress": min(expired_detective.target_count, 2),
                            "is_completed": False,
                            "updated_at": now - timedelta(days=12),
                        },
                    ]
                )

            for row in sample_progress_rows:
                challenge = row["challenge"]
                completed_at = row.get("completed_at")
                await _upsert_participation(
                    db,
                    challenge_id=challenge.id,
                    child_id=row["child"].id,
                    progress=row["progress"],
                    is_completed=row["is_completed"],
                    completed_at=completed_at,
                    created_at=challenge.starts_at,
                    updated_at=row["updated_at"],
                )

        if can_seed_posts:
            await db.execute(delete(PostReaction).where(PostReaction.post_id.in_(sample_post_ids)))

            approved_posts_result = await db.execute(
                select(CommunityPost)
                .where(CommunityPost.id.in_(sample_post_ids), CommunityPost.moderation_status == ModerationStatus.APPROVED)
                .order_by(CommunityPost.created_at.desc())
            )
            approved_posts = list(approved_posts_result.scalars().all())

            for post_index, post in enumerate(approved_posts):
                reactors = [child for child in base_children if child.id != post.child_id][: (post_index % 2) + 1]
                for reactor in reactors:
                    db.add(
                        PostReaction(
                            post_id=post.id,
                            child_id=reactor.id,
                            reaction_type="star",
                        )
                    )
                post.reaction_count = len(reactors)

        await db.commit()

        print("Seeded community sample data")
        print(f"  Children available for feed: {len(base_children)}")
        print(f"  Approved sample posts: {len(approved_posts)}")
        print(f"  Pending sample posts: {pending_post_count}")
        print(f"  Public sample challenges: {len(seeded_challenges)}")
        print(f"  Seeded leaderboard children: {min(3, len(base_children))}")
        if not can_seed_posts:
            print("  Skipped sample community posts because fewer than 3 words had real image URLs")
        print(f"  Demo parent password: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed_community_samples())