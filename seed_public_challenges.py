"""
Seed 10 public community challenges for the admin challenge catalog UI.

This script is idempotent and will upsert the same challenge IDs on each run.

Usage:
  ./venv/bin/python seed_public_challenges.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, LearningSession  # noqa: F401
from app.models.community import ChallengeStatus, CommunityChallenge
from app.models.content import Game, Mission, Story  # noqa: F401
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.user import Child, User  # noqa: F401
from app.models.vocabulary import Category, Word, WordProgress  # noqa: F401


SAMPLE_PUBLIC_CHALLENGES = [
    {
        "id": "seed-admin-public-challenge-01",
        "title": "Capture 3 Words Today",
        "title_zh": "今日拍攝3個詞語",
        "description": "Use the camera to capture and learn 3 real-world objects today.",
        "description_zh": "今日用相機拍攝並學習3個生活詞語。",
        "target_count": 3,
        "category": "camera",
        "emoji": "📷",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -2,
        "ends_in_days": 5,
        "created_in_days": -4,
    },
    {
        "id": "seed-admin-public-challenge-02",
        "title": "Kitchen Word Hunt",
        "title_zh": "廚房詞語尋寶",
        "description": "Find and say 5 kitchen words in Cantonese with your child.",
        "description_zh": "同小朋友一齊喺廚房搵出5個詞語並用廣東話講出嚟。",
        "target_count": 5,
        "category": "home",
        "emoji": "🍳",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -1,
        "ends_in_days": 6,
        "created_in_days": -3,
    },
    {
        "id": "seed-admin-public-challenge-03",
        "title": "Color Spotter Week",
        "title_zh": "顏色觀察週",
        "description": "Spot 6 colorful objects and name each one in Cantonese.",
        "description_zh": "觀察6件唔同顏色嘅物件，並逐一用廣東話命名。",
        "target_count": 6,
        "category": "observation",
        "emoji": "🌈",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -3,
        "ends_in_days": 4,
        "created_in_days": -6,
    },
    {
        "id": "seed-admin-public-challenge-04",
        "title": "Bedtime Story Retell",
        "title_zh": "睡前故事重講",
        "description": "Retell 4 short story moments before bedtime.",
        "description_zh": "睡前重講4個短故事片段。",
        "target_count": 4,
        "category": "stories",
        "emoji": "🌙",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -5,
        "ends_in_days": 3,
        "created_in_days": -8,
    },
    {
        "id": "seed-admin-public-challenge-05",
        "title": "Playground Action Words",
        "title_zh": "遊樂場動作詞",
        "description": "Practice 5 action words while playing outside.",
        "description_zh": "戶外遊戲時練習5個動作詞語。",
        "target_count": 5,
        "category": "outdoor",
        "emoji": "🏃",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -2,
        "ends_in_days": 7,
        "created_in_days": -5,
    },
    {
        "id": "seed-admin-public-challenge-06",
        "title": "Family Conversation Sprint",
        "title_zh": "家庭對話衝刺",
        "description": "Have 5 short Cantonese conversations during daily routines.",
        "description_zh": "喺日常流程中完成5次簡短廣東話對話。",
        "target_count": 5,
        "category": "speaking",
        "emoji": "🗣️",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": -1,
        "ends_in_days": 8,
        "created_in_days": -2,
    },
    {
        "id": "seed-admin-public-challenge-07",
        "title": "Weekend Market Words",
        "title_zh": "週末街市詞語",
        "description": "Collect 7 food-related words from a market visit.",
        "description_zh": "逛街市時蒐集7個與食物相關嘅詞語。",
        "target_count": 7,
        "category": "shopping",
        "emoji": "🛒",
        "status": ChallengeStatus.ACTIVE,
        "starts_in_days": 1,
        "ends_in_days": 10,
        "created_in_days": -1,
    },
    {
        "id": "seed-admin-public-challenge-08",
        "title": "Picture Talk Challenge",
        "title_zh": "看圖講詞挑戰",
        "description": "Describe 6 picture cards using simple Cantonese phrases.",
        "description_zh": "用簡單廣東話短句描述6張圖卡。",
        "target_count": 6,
        "category": "vocabulary",
        "emoji": "🖼️",
        "status": ChallengeStatus.COMPLETED,
        "starts_in_days": -14,
        "ends_in_days": -2,
        "created_in_days": -16,
    },
    {
        "id": "seed-admin-public-challenge-09",
        "title": "Nature Walk Word List",
        "title_zh": "自然散步詞語表",
        "description": "Find and name 8 nature words during a walk.",
        "description_zh": "散步時搵出並講出8個自然主題詞語。",
        "target_count": 8,
        "category": "outdoor",
        "emoji": "🍃",
        "status": ChallengeStatus.EXPIRED,
        "starts_in_days": -21,
        "ends_in_days": -8,
        "created_in_days": -23,
    },
    {
        "id": "seed-admin-public-challenge-10",
        "title": "My Favorite Things",
        "title_zh": "我最鍾意嘅物件",
        "description": "Share 5 favorite objects and say why in Cantonese.",
        "description_zh": "分享5件最鍾意嘅物件，並用廣東話講原因。",
        "target_count": 5,
        "category": "speaking",
        "emoji": "⭐",
        "status": ChallengeStatus.COMPLETED,
        "starts_in_days": -18,
        "ends_in_days": -1,
        "created_in_days": -20,
    },
]


async def _upsert_challenge(db, payload: dict, *, now: datetime) -> bool:
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
        return True

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
    return False


async def seed_public_challenges() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        added = 0
        updated = 0

        for payload in SAMPLE_PUBLIC_CHALLENGES:
            created = await _upsert_challenge(db, payload, now=now)
            if created:
                added += 1
                print(f"  Added: {payload['title']}")
            else:
                updated += 1
                print(f"  Updated: {payload['title']}")

        await db.commit()

        print("\nSeeded public admin challenges")
        print(f"  Added: {added}")
        print(f"  Updated: {updated}")
        print(f"  Total configured in script: {len(SAMPLE_PUBLIC_CHALLENGES)}")


if __name__ == "__main__":
    asyncio.run(seed_public_challenges())