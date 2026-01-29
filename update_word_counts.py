"""
Update word counts for all categories
"""
import asyncio
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement


async def update_word_counts():
    async with AsyncSessionLocal() as db:
        # Get all categories
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        
        print(f"Updating word counts for {len(categories)} categories...\n")
        
        for category in categories:
            # Count words in this category
            result = await db.execute(
                select(Word).where(Word.category == category.id, Word.is_active == True)
            )
            words = result.scalars().all()
            
            old_count = category.word_count
            category.word_count = len(words)
            
            print(f"  {category.icon} {category.name}: {old_count} → {len(words)} words")
        
        await db.commit()
        
        print(f"\n✅ Word counts updated successfully!")


if __name__ == "__main__":
    print("🔄 Updating category word counts...\n")
    asyncio.run(update_word_counts())
