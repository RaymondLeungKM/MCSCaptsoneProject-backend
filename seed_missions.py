"""
Seed sample missions into the database.

Usage:
  python seed_missions.py
"""
import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.content import Mission, MissionContext, MissionStatus, MissionSurface


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
    },
]


async def seed_missions():
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        added = 0
        skipped = 0

        for data in SAMPLE_MISSIONS:
            existing = await db.execute(
                select(Mission).where(Mission.slug == data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"  ⏭  Skipping (already exists): {data['slug']}")
                skipped += 1
                continue

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
                conversation_prompts=data["conversation_prompts"],
                selection_tags=data["selection_tags"],
                published_at=now,
            )
            db.add(mission)
            print(f"  ✅ Added: {data['title']}")
            added += 1

        await db.commit()
        print(f"\nDone — {added} missions added, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(seed_missions())
