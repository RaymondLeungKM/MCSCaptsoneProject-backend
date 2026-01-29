"""
Seed the database with initial vocabulary words and categories
"""
import asyncio
import uuid
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
# Import all models to ensure relationships are configured
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement


async def seed_data():
    async with AsyncSessionLocal() as db:
        # Check if we already have categories
        result = await db.execute(select(Category))
        existing_categories = result.scalars().all()
        
        # Check words
        result = await db.execute(select(Word))
        existing_words = result.scalars().all()
        
        if existing_categories and existing_words:
            print(f"✓ Database already has {len(existing_categories)} categories")
            print(f"✓ Database already has {len(existing_words)} words")
            print("\n✅ Database already seeded!")
            return
        
        print("📚 Seeding database with initial data...")
        
        # Get or create categories
        if existing_categories:
            print(f"✓ Using existing {len(existing_categories)} categories")
            categories = {cat.name: cat for cat in existing_categories}
        else:
            # Create categories
            categories_data = [
            {
                "name": "Animals",
                "description": "Learn about different animals",
                "icon": "🦁",
                "color": "bg-sunny",
                "sort_order": 1
            },
            {
                "name": "Food",
                "description": "Learn about different foods",
                "icon": "🍎",
                "color": "bg-coral",
                "sort_order": 2
            },
            {
                "name": "Colors",
                "description": "Learn about colors",
                "icon": "🎨",
                "color": "bg-sky",
                "sort_order": 3
            },
            {
                "name": "Nature",
                "description": "Learn about nature",
                "icon": "🌳",
                "color": "bg-mint",
                "sort_order": 4
            },
            {
                "name": "Family",
                "description": "Learn about family members",
                "icon": "👨‍👩‍👧",
                "color": "bg-lavender",
                "sort_order": 5
            },
            ]
            
            categories = {}
            for cat_data in categories_data:
                category = Category(
                    id=str(uuid.uuid4()),
                    **cat_data
                )
                db.add(category)
                categories[cat_data["name"]] = category
            
            await db.commit()
            print(f"✓ Created {len(categories)} categories")
        
        # Create words
        words_data = [
            # Animals
            {"word": "Cat", "category": "Animals", "difficulty": "easy", "definition": "A small furry pet that says meow", "image": "🐱"},
            {"word": "Dog", "category": "Animals", "difficulty": "easy", "definition": "A friendly pet that says woof", "image": "🐶"},
            {"word": "Elephant", "category": "Animals", "difficulty": "medium", "definition": "A very large gray animal with a long trunk", "image": "🐘"},
            {"word": "Lion", "category": "Animals", "difficulty": "medium", "definition": "A big cat with a mane that roars", "image": "🦁"},
            {"word": "Butterfly", "category": "Animals", "difficulty": "hard", "definition": "A colorful insect with beautiful wings", "image": "🦋"},
            
            # Food
            {"word": "Apple", "category": "Food", "difficulty": "easy", "definition": "A round red or green fruit", "image": "🍎"},
            {"word": "Banana", "category": "Food", "difficulty": "easy", "definition": "A long yellow fruit", "image": "🍌"},
            {"word": "Pizza", "category": "Food", "difficulty": "easy", "definition": "A round food with cheese and toppings", "image": "🍕"},
            {"word": "Carrot", "category": "Food", "difficulty": "medium", "definition": "A long orange vegetable", "image": "🥕"},
            {"word": "Strawberry", "category": "Food", "difficulty": "medium", "definition": "A small red fruit with seeds", "image": "🍓"},
            
            # Colors
            {"word": "Red", "category": "Colors", "difficulty": "easy", "definition": "The color of an apple or fire truck", "image": "🔴"},
            {"word": "Blue", "category": "Colors", "difficulty": "easy", "definition": "The color of the sky", "image": "🔵"},
            {"word": "Yellow", "category": "Colors", "difficulty": "easy", "definition": "The color of the sun", "image": "🟡"},
            {"word": "Green", "category": "Colors", "difficulty": "easy", "definition": "The color of grass", "image": "🟢"},
            {"word": "Purple", "category": "Colors", "difficulty": "medium", "definition": "A mix of red and blue", "image": "🟣"},
            
            # Nature
            {"word": "Tree", "category": "Nature", "difficulty": "easy", "definition": "A tall plant with leaves", "image": "🌳"},
            {"word": "Flower", "category": "Nature", "difficulty": "easy", "definition": "A pretty plant that smells nice", "image": "🌸"},
            {"word": "Sun", "category": "Nature", "difficulty": "easy", "definition": "The bright light in the sky during day", "image": "☀️"},
            {"word": "Rainbow", "category": "Nature", "difficulty": "medium", "definition": "Colorful arc in the sky after rain", "image": "🌈"},
            {"word": "Ocean", "category": "Nature", "difficulty": "medium", "definition": "A very big area of water", "image": "🌊"},
            
            # Family
            {"word": "Mom", "category": "Family", "difficulty": "easy", "definition": "Your mother", "image": "👩"},
            {"word": "Dad", "category": "Family", "difficulty": "easy", "definition": "Your father", "image": "👨"},
            {"word": "Sister", "category": "Family", "difficulty": "easy", "definition": "A girl who shares your parents", "image": "👧"},
            {"word": "Brother", "category": "Family", "difficulty": "easy", "definition": "A boy who shares your parents", "image": "👦"},
            {"word": "Grandma", "category": "Family", "difficulty": "medium", "definition": "Your parent's mother", "image": "👵"},
        ]
        
        for word_data in words_data:
            category = categories[word_data["category"]]
            word = Word(
                id=str(uuid.uuid4()),
                word=word_data["word"],
                category=category.id,
                difficulty=word_data["difficulty"],
                definition=word_data["definition"],
                example=f"I see a {word_data['word'].lower()}!",
                pronunciation=word_data["word"].lower(),
                is_active=True,
                image_url=word_data.get("image"),
                audio_url=None
            )
            db.add(word)
        
        await db.commit()
        print(f"✓ Created {len(words_data)} words")
        
        # Update word counts for each category
        for category in categories.values():
            result = await db.execute(
                select(Word).where(Word.category == category.id, Word.is_active == True)
            )
            words_in_category = result.scalars().all()
            category.word_count = len(words_in_category)
        
        await db.commit()
        print(f"✓ Updated category word counts")
        
        print("\n✅ Database seeding complete!")
        print(f"   - {len(categories)} categories")
        print(f"   - {len(words_data)} words")
        print("\n🚀 You can now use the app!")


if __name__ == "__main__":
    print("🌱 Starting database seeding...\n")
    asyncio.run(seed_data())
