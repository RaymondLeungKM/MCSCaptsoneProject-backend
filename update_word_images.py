"""
Update word images with emojis
"""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement

async def update_images():
    async with AsyncSessionLocal() as db:
        # Map of words to their emoji images
        word_images = {
            "Cat": "🐱",
            "Dog": "🐶",
            "Elephant": "🐘",
            "Lion": "🦁",
            "Butterfly": "🦋",
            "Apple": "🍎",
            "Banana": "🍌",
            "Pizza": "🍕",
            "Carrot": "🥕",
            "Strawberry": "🍓",
            "Red": "🔴",
            "Blue": "🔵",
            "Yellow": "🟡",
            "Green": "🟢",
            "Purple": "🟣",
            "Tree": "🌳",
            "Flower": "🌸",
            "Sun": "☀️",
            "Rainbow": "🌈",
            "Ocean": "🌊",
            "Mom": "👩",
            "Dad": "👨",
            "Sister": "👧",
            "Brother": "👦",
            "Grandma": "👵",
        }
        
        result = await db.execute(select(Word))
        words = result.scalars().all()
        
        for word in words:
            if word.word in word_images:
                word.image_url = word_images[word.word]
                print(f"✓ Updated {word.word}: {word.image_url}")
        
        await db.commit()
        print(f"\n✅ Updated {len(word_images)} word images!")

if __name__ == "__main__":
    asyncio.run(update_images())
