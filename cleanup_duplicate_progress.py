"""
Clean up duplicate word progress records
"""
import asyncio
from sqlalchemy import select, delete, func
from app.db.session import AsyncSessionLocal
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement

async def cleanup_duplicates():
    async with AsyncSessionLocal() as db:
        # Find all unique (child_id, word_id) combinations
        result = await db.execute(
            select(WordProgress.child_id, WordProgress.word_id, func.count(WordProgress.id))
            .group_by(WordProgress.child_id, WordProgress.word_id)
            .having(func.count(WordProgress.id) > 1)
        )
        duplicates = result.all()
        
        if not duplicates:
            print("✅ No duplicates found!")
            return
        
        print(f"Found {len(duplicates)} sets of duplicate records")
        
        for child_id, word_id, count in duplicates:
            # Get all progress records for this combination
            result = await db.execute(
                select(WordProgress)
                .where(
                    WordProgress.child_id == child_id,
                    WordProgress.word_id == word_id
                )
                .order_by(WordProgress.created_at.desc())
            )
            records = result.scalars().all()
            
            # Keep the most recent one, delete the rest
            keep = records[0]
            to_delete = records[1:]
            
            print(f"  Child {child_id[:8]}... Word {word_id[:8]}... - keeping 1, deleting {len(to_delete)}")
            
            for record in to_delete:
                await db.delete(record)
        
        await db.commit()
        print(f"\n✅ Cleaned up {len(duplicates)} sets of duplicates!")

if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())
