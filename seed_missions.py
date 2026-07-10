"""
Seed sample missions into the database.

Usage:
  python seed_missions.py
"""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, LearningSession  # noqa: F401
from app.models.content import (  # noqa: F401
    Game,
    Mission,
    MissionContext,
    MissionStatus,
    MissionSurface,
    Story,
)
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.user import Child, User  # noqa: F401
from app.models.vocabulary import Category, Word, WordProgress  # noqa: F401

MIN_WEEKLY_ROTATION_POOL = 7


SAMPLE_MISSIONS = [
    {
        "slug": "listen-3-words",
        "title": "聆聽3個詞語發音",
        "description": "今天點擊3個詞語的喇叭按鈕，認真聆聽發音，感受廣東話的聲調！",
        "context": MissionContext.GENERAL,
        "surface": MissionSurface.CHILD,
        "sort_order": 1,
        "conversation_prompts": ["你今天聽了哪些詞語？", "最難發音的是哪個？"],
        "selection_tags": ["listening", "pronunciation", "daily"],
        "target_word_keys": ["Cat", "Dog", "Bird"],
    },
    {
        "slug": "learn-new-word-today",
        "title": "學識1個新詞語",
        "description": "打開學習頁面，點擊一個未學過的詞語，把它加入你的詞彙庫！",
        "context": MissionContext.GENERAL,
        "surface": MissionSurface.CHILD,
        "sort_order": 2,
        "conversation_prompts": ["你今天學了什麼新詞語？", "這個詞語的意思是什麼？"],
        "selection_tags": ["vocabulary", "learning", "daily"],
        "target_word_keys": ["Apple", "Banana", "Rabbit"],
    },
    {
        "slug": "play-word-game",
        "title": "玩一個詞語遊戲",
        "description": "去遊戲區，選一個你喜歡的遊戲，挑戰自己！",
        "context": MissionContext.PLAYTIME,
        "surface": MissionSurface.CHILD,
        "sort_order": 3,
        "conversation_prompts": ["你玩了哪個遊戲？", "你答對了多少題？"],
        "selection_tags": ["game", "fun", "daily"],
        "target_word_keys": ["Ball", "Pencil", "Book"],
    },
    {
        "slug": "read-bedtime-story",
        "title": "睡前讀一個故事",
        "description": "臨睡前，去故事書架選一個故事，好好享受閱讀時光！",
        "context": MissionContext.BEDTIME,
        "surface": MissionSurface.CHILD,
        "sort_order": 4,
        "conversation_prompts": ["故事裡有哪些角色？", "你最喜歡哪個部分？"],
        "selection_tags": ["reading", "story", "bedtime"],
        "target_word_keys": ["Book", "Cat", "Rabbit"],
    },
    {
        "slug": "word-of-day-review",
        "title": "認識今日單字",
        "description": "看看今日單字，聆聽發音，嘗試記住它的意思！",
        "context": MissionContext.GENERAL,
        "surface": MissionSurface.CHILD,
        "sort_order": 5,
        "conversation_prompts": ["今日單字是什麼？", "你能用這個詞語造句嗎？"],
        "selection_tags": ["word-of-day", "vocabulary", "daily"],
        "target_word_keys": ["Apple", "Rice", "Milk"],
    },
    {
        "slug": "generate-ai-story",
        "title": "生成一個個人化故事",
        "description": "去故事生成器，選一個你喜歡的主題，用今天學到的詞語創作屬於你的故事！",
        "context": MissionContext.GENERAL,
        "surface": MissionSurface.CHILD,
        "sort_order": 6,
        "conversation_prompts": ["你選了哪個故事主題？", "故事裡有用到今天學的詞語嗎？"],
        "selection_tags": ["story", "ai", "creative"],
        "target_word_keys": ["Cat", "Apple", "Book"],
    },
    {
        "slug": "make-a-short-sentence",
        "title": "用兩個詞語講一句短句",
        "description": "揀兩個今天見過的詞語，試下用廣東話講一句短句，讓家人聽聽你的表達！",
        "context": MissionContext.GENERAL,
        "surface": MissionSurface.CHILD,
        "sort_order": 7,
        "conversation_prompts": ["你用了哪兩個詞語？", "你會怎樣把這句短句講得更完整？"],
        "selection_tags": ["speaking", "sentence-building", "daily"],
        "target_word_keys": ["Pencil", "Bread", "Dog"],
    },
]


def _word_display(word: Word) -> str:
    if word.word_cantonese and word.word_cantonese.strip():
        return word.word_cantonese.strip()
    return word.word


async def _load_seed_words(
    db,
    *,
    required_word_keys: list[str],
) -> dict[str, Word]:
    result = await db.execute(
        select(Word).where(
            Word.word.in_(required_word_keys),
            Word.is_active == True,
        )
    )
    return {word.word: word for word in result.scalars().all()}


def _resolve_target_words(
    *,
    mission_slug: str,
    target_word_keys: list[str],
    word_lookup: dict[str, Word],
) -> list[str]:
    missing = [word_key for word_key in target_word_keys if word_key not in word_lookup]
    if missing:
        raise RuntimeError(
            f"Missing seeded words for mission '{mission_slug}': {', '.join(missing)}"
        )

    return [_word_display(word_lookup[word_key]) for word_key in target_word_keys]


async def seed_missions():
    if len(SAMPLE_MISSIONS) < MIN_WEEKLY_ROTATION_POOL:
        raise RuntimeError(
            f"Expected at least {MIN_WEEKLY_ROTATION_POOL} seed missions for weekly rotation, "
            f"got {len(SAMPLE_MISSIONS)}."
        )

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        added = 0
        updated = 0
        required_word_keys = sorted(
            {
                word_key
                for mission in SAMPLE_MISSIONS
                for word_key in mission["target_word_keys"]
            }
        )
        word_lookup = await _load_seed_words(
            db,
            required_word_keys=required_word_keys,
        )

        for data in SAMPLE_MISSIONS:
            target_words = _resolve_target_words(
                mission_slug=data["slug"],
                target_word_keys=data["target_word_keys"],
                word_lookup=word_lookup,
            )
            existing = await db.execute(
                select(Mission).where(Mission.slug == data["slug"])
            )
            mission = existing.scalar_one_or_none()

            if mission is None:
                mission = Mission(
                    id=str(uuid.uuid4()),
                    slug=data["slug"],
                    title=data["title"],
                    description=data["description"],
                    context=data["context"],
                    surface=data["surface"],
                    status=MissionStatus.PUBLISHED,
                    locale="zh-HK",
                    is_offline=False,
                    is_active=True,
                    sort_order=data["sort_order"],
                    target_words=target_words,
                    conversation_prompts=data["conversation_prompts"],
                    selection_tags=data["selection_tags"],
                    published_at=now,
                    catalog_metadata={"seed_source": "seed_missions"},
                )
                db.add(mission)
                added += 1
                print(f"  ✅ Added: {data['title']}")
            else:
                mission.title = data["title"]
                mission.description = data["description"]
                mission.context = data["context"]
                mission.surface = data["surface"]
                mission.status = MissionStatus.PUBLISHED
                mission.locale = "zh-HK"
                mission.is_offline = False
                mission.is_active = True
                mission.sort_order = data["sort_order"]
                mission.target_words = target_words
                mission.conversation_prompts = data["conversation_prompts"]
                mission.selection_tags = data["selection_tags"]
                mission.published_at = mission.published_at or now
                mission.archived_at = None
                metadata = dict(mission.catalog_metadata or {})
                metadata["seed_source"] = "seed_missions"
                mission.catalog_metadata = metadata
                updated += 1
                print(f"  ♻️  Updated: {data['title']}")

            mission.assignment_repeat_cooldown_days = MIN_WEEKLY_ROTATION_POOL

        await db.commit()
        print(f"\nDone — {added} missions added, {updated} missions updated.")


if __name__ == "__main__":
    asyncio.run(seed_missions())
