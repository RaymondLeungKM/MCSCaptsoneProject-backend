"""
Update category colors to use Tailwind classes instead of hex codes
"""
import asyncio
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
# Import all models to ensure relationships are configured
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement

async def update_colors():
    async with AsyncSessionLocal() as db:
        # Map of category names to Tailwind color classes
        color_map = {
            "Animals": "bg-sunny",
            "Food": "bg-coral",
            "Colors": "bg-sky",
            "Nature": "bg-mint",
            "Family": "bg-lavender",
        }
        
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        
        for category in categories:
            if category.name in color_map:
                category.color = color_map[category.name]
                print(f"✓ Updated {category.name}: {category.color}")
        
        await db.commit()
        print("\n✅ All category colors updated!")

if __name__ == "__main__":
    asyncio.run(update_colors())
