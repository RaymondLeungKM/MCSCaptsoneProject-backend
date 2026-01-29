"""
Check if word progress is being saved
"""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement

async def check_progress():
    async with AsyncSessionLocal() as db:
        # Get all children
        result = await db.execute(select(Child))
        children = result.scalars().all()
        
        print("\n=== Children ===")
        for child in children:
            print(f"\nChild: {child.name} (ID: {child.id[:8]}...)")
            print(f"  Level: {child.level}")
            print(f"  XP: {child.xp}")
            print(f"  Words Learned: {child.words_learned}")
            print(f"  Today Progress: {child.today_progress}")
            
            # Get word progress for this child
            result = await db.execute(
                select(WordProgress).where(WordProgress.child_id == child.id)
            )
            progress_records = result.scalars().all()
            
            print(f"  Word Progress Records: {len(progress_records)}")
            for prog in progress_records:
                print(f"    - Word ID {prog.word_id[:8]}...: exposure_count={prog.exposure_count}, mastered={prog.mastered}")

if __name__ == "__main__":
    asyncio.run(check_progress())
