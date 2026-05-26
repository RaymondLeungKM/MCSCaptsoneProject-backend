"""
Seed child demo missions and private photo words for local testing.

This script is idempotent. It:
1. Creates a small set of published missions shown in both child and parent mode.
2. Assigns those missions to every existing child for today.
3. Ensures each child has at least a few private photo words that have not been
   posted to the community yet, so the share flow can be tested end to end.

Usage:
  ./venv/bin/python seed_child_demo_content.py
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, DailyStats, LearningSession  # noqa: F401
from app.models.community import CommunityPost, PostReaction  # noqa: F401
from app.models.content import (  # noqa: F401
    Game,
    Mission,
    MissionAssignment,
    MissionAssignmentSource,
    MissionAssignmentStatus,
    MissionContext,
    MissionStatus,
    MissionSurface,
    Story,
)
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    DailyLearningStats,
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.user import Child
from app.models.vocabulary import Word


MIN_PRIVATE_PHOTO_WORDS = 4
PHOTO_TEMPLATE_WORDS = [
    "Mirror",
    "Shower",
    "Shampoo",
    "Towel",
    "Glue",
    "Pencil",
]

MISSION_SEED = [
    {
        "slug": "demo-daily-home-word-hunt",
        "title": "今日搵一搵",
        "description": "在家中找出兩樣看得到的物件，並用廣東話說出名字。",
        "context": MissionContext.GENERAL,
        "is_offline": False,
        "target_words": ["鏡", "毛巾", "鉛筆"],
        "conversation_prompts": ["我見到乜嘢？試下大聲講出來。"],
        "sort_order": 10,
    },
    {
        "slug": "demo-daily-bedtime-retell",
        "title": "睡前講一次",
        "description": "睡前選一個今天學過的詞語，再講一次意思和例句。",
        "context": MissionContext.BEDTIME,
        "is_offline": False,
        "target_words": ["膠水", "洗頭水", "花灑"],
        "conversation_prompts": ["今晚想講邊一個詞語畀家長聽？"],
        "sort_order": 20,
    },
    {
        "slug": "demo-daily-action-word",
        "title": "動作詞小挑戰",
        "description": "一邊做動作，一邊說出你今天學過的詞語。",
        "context": MissionContext.PLAYTIME,
        "is_offline": False,
        "target_words": ["毛巾", "鏡", "鉛筆"],
        "conversation_prompts": ["你可以一邊指住物件，一邊講出個詞語。"],
        "sort_order": 30,
    },
    {
        "slug": "demo-offline-bathroom-chat",
        "title": "浴室用品任務",
        "description": "和家長一起在浴室找出用品，再輪流說出名稱和用途。",
        "context": MissionContext.GENERAL,
        "is_offline": True,
        "target_words": ["鏡", "花灑", "洗頭水", "毛巾"],
        "conversation_prompts": ["這件浴室用品平時用來做什麼？"],
        "sort_order": 110,
    },
    {
        "slug": "demo-offline-mealtime-talk",
        "title": "用餐前說一說",
        "description": "開飯前請孩子用今天的詞語說一句完整句子。",
        "context": MissionContext.MEALTIME,
        "is_offline": True,
        "target_words": ["毛巾", "鏡"],
        "conversation_prompts": ["可唔可以用『我見到……』開頭說一句？"],
        "sort_order": 120,
    },
    {
        "slug": "demo-offline-outdoor-photo-talk",
        "title": "相片分享預備",
        "description": "先和家長挑一張自己拍的相片，說出物件名字，再決定是否提交分享。",
        "context": MissionContext.OUTDOOR,
        "is_offline": True,
        "target_words": ["鏡", "花灑", "膠水", "鉛筆"],
        "conversation_prompts": ["你想分享哪一張相片？先講講相中有什麼。"],
        "sort_order": 130,
    },
]


def _is_real_image_url(value: str | None) -> bool:
    return bool(
        value
        and (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("/")
            or value.startswith("uploads/")
        )
    )


async def _upsert_mission(db, payload: dict) -> Mission:
    result = await db.execute(select(Mission).where(Mission.slug == payload["slug"]))
    mission = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if mission is None:
        mission = Mission(
            id=f"seed-{payload['slug']}",
            slug=payload["slug"],
            title=payload["title"],
            description=payload["description"],
            context=payload["context"],
            is_offline=payload["is_offline"],
            status=MissionStatus.PUBLISHED,
            locale="zh-HK",
            age_min=2,
            age_max=8,
            difficulty="easy",
            surface=MissionSurface.BOTH,
            sort_order=payload["sort_order"],
            selection_tags=["seed", "local-demo", "child-home"],
            catalog_metadata={"seed_source": "seed_child_demo_content"},
            published_at=now,
            target_words=payload["target_words"],
            conversation_prompts=payload["conversation_prompts"],
            is_active=True,
        )
        db.add(mission)
        return mission

    mission.title = payload["title"]
    mission.description = payload["description"]
    mission.context = payload["context"]
    mission.is_offline = payload["is_offline"]
    mission.status = MissionStatus.PUBLISHED
    mission.locale = "zh-HK"
    mission.age_min = 2
    mission.age_max = 8
    mission.difficulty = "easy"
    mission.surface = MissionSurface.BOTH
    mission.sort_order = payload["sort_order"]
    mission.selection_tags = ["seed", "local-demo", "child-home"]
    mission.catalog_metadata = {"seed_source": "seed_child_demo_content"}
    mission.published_at = mission.published_at or now
    mission.archived_at = None
    mission.target_words = payload["target_words"]
    mission.conversation_prompts = payload["conversation_prompts"]
    mission.is_active = True
    return mission


async def _ensure_assignments(db, children: list[Child], missions: list[Mission]) -> int:
    assignment_date = date.today()
    created = 0

    existing_result = await db.execute(
        select(MissionAssignment).where(MissionAssignment.assignment_date == assignment_date)
    )
    existing_keys = {
        (assignment.child_id, assignment.mission_id)
        for assignment in existing_result.scalars().all()
    }

    daily_missions = [mission for mission in missions if not mission.is_offline]
    offline_missions = [mission for mission in missions if mission.is_offline]

    for child in children:
        priority = 1
        for mission in daily_missions + offline_missions:
            key = (child.id, mission.id)
            if key in existing_keys:
                priority += 1
                continue

            db.add(
                MissionAssignment(
                    id=str(uuid.uuid4()),
                    child_id=child.id,
                    mission_id=mission.id,
                    assignment_date=assignment_date,
                    source=MissionAssignmentSource.SEED,
                    status=MissionAssignmentStatus.ASSIGNED,
                    surface=mission.surface,
                    priority=priority,
                    selection_reason="Seeded local demo mission",
                    selection_metadata={
                        "seed_source": "seed_child_demo_content",
                        "is_offline": mission.is_offline,
                    },
                )
            )
            existing_keys.add(key)
            created += 1
            priority += 1

    return created


async def _get_photo_templates(db) -> list[Word]:
    preferred_result = await db.execute(
        select(Word)
        .where(Word.word.in_(PHOTO_TEMPLATE_WORDS), Word.image_url.isnot(None), Word.image_url != "")
        .order_by(Word.created_by_child_id.is_not(None).desc(), Word.created_at.desc())
    )
    preferred_words = []
    seen_words: set[str] = set()

    for word in preferred_result.scalars().all():
        if not _is_real_image_url(word.image_url):
            continue
        key = word.word.strip().lower()
        if key in seen_words:
            continue
        preferred_words.append(word)
        seen_words.add(key)

    if len(preferred_words) >= MIN_PRIVATE_PHOTO_WORDS:
        return preferred_words

    fallback_result = await db.execute(
        select(Word)
        .where(Word.created_by_child_id.isnot(None), Word.image_url.isnot(None), Word.image_url != "")
        .order_by(Word.created_at.desc())
        .limit(24)
    )

    for word in fallback_result.scalars().all():
        if not _is_real_image_url(word.image_url):
            continue
        key = f"{word.word.strip().lower()}|{word.image_url}"
        if key in seen_words:
            continue
        preferred_words.append(word)
        seen_words.add(key)
        if len(preferred_words) >= MIN_PRIVATE_PHOTO_WORDS:
            break

    return preferred_words


async def _ensure_private_photo_words(db, children: list[Child]) -> int:
    templates = await _get_photo_templates(db)
    if len(templates) < MIN_PRIVATE_PHOTO_WORDS:
        raise RuntimeError(
            "Need at least 4 image-backed word templates to seed child photo words."
        )

    posted_word_ids_result = await db.execute(
        select(CommunityPost.word_id).where(CommunityPost.word_id.is_not(None))
    )
    posted_word_ids = {word_id for word_id in posted_word_ids_result.scalars().all() if word_id}

    created = 0
    now = datetime.now(timezone.utc)

    for child in children:
        existing_result = await db.execute(
            select(Word)
            .where(
                Word.created_by_child_id == child.id,
                Word.is_active == True,
                Word.image_url.isnot(None),
                Word.image_url != "",
            )
            .order_by(Word.created_at.desc())
        )
        existing_words = [
            word
            for word in existing_result.scalars().all()
            if _is_real_image_url(word.image_url)
        ]
        unposted_count = sum(1 for word in existing_words if word.id not in posted_word_ids)
        if unposted_count >= MIN_PRIVATE_PHOTO_WORDS:
            continue

        existing_keys = {
            (word.word.strip().lower(), (word.image_url or "").strip())
            for word in existing_words
        }
        needed = MIN_PRIVATE_PHOTO_WORDS - unposted_count

        for index, template in enumerate(templates):
            template_key = (
                template.word.strip().lower(),
                (template.image_url or "").strip(),
            )
            if template_key in existing_keys:
                continue

            db.add(
                Word(
                    id=str(uuid.uuid4()),
                    word=template.word,
                    word_cantonese=template.word_cantonese,
                    category=template.category,
                    pronunciation=template.pronunciation,
                    jyutping=template.jyutping,
                    definition=template.definition,
                    definition_cantonese=template.definition_cantonese,
                    example=template.example,
                    example_cantonese=template.example_cantonese,
                    image_url=template.image_url,
                    audio_url=template.audio_url,
                    audio_url_english=template.audio_url_english,
                    difficulty=template.difficulty,
                    physical_action=template.physical_action,
                    contexts=template.contexts,
                    related_words=template.related_words,
                    total_exposures=0,
                    success_rate=0.0,
                    created_by_child_id=child.id,
                    is_active=True,
                    created_at=now - timedelta(minutes=index),
                )
            )
            existing_keys.add(template_key)
            created += 1
            needed -= 1
            if needed <= 0:
                break

    return created


async def seed_child_demo_content() -> None:
    async with AsyncSessionLocal() as db:
        children_result = await db.execute(
            select(Child).order_by(Child.created_at.asc(), Child.id.asc())
        )
        children = list(children_result.scalars().all())
        if not children:
            raise RuntimeError("No child profiles exist yet. Create a child first.")

        seeded_missions = []
        for payload in MISSION_SEED:
            seeded_missions.append(await _upsert_mission(db, payload))

        await db.flush()

        assignments_created = await _ensure_assignments(db, children, seeded_missions)
        photo_words_created = await _ensure_private_photo_words(db, children)

        await db.commit()

        print(
            "Seeded child demo content:",
            {
                "missions_upserted": len(seeded_missions),
                "assignments_created": assignments_created,
                "photo_words_created": photo_words_created,
                "children": len(children),
            },
        )


if __name__ == "__main__":
    asyncio.run(seed_child_demo_content())