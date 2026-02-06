#!/usr/bin/env python3
"""
Setup test data for bedtime story generation

This script creates/updates daily word tracking for TODAY so you can test
the bedtime story generation feature in the UI.

Usage:
    python setup_story_test_data.py
    
    Then login to the UI with:
    - Email: parent@test.com
    - Password: password123
    
    Select the child and generate a bedtime story!
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import select, delete
from app.db.session import AsyncSessionLocal

# Import all models to ensure SQLAlchemy relationships are registered
from app.models.user import User, Child, ChildInterest
from app.models.vocabulary import Word, Category, WordProgress
from app.models.daily_words import DailyWordTracking, GeneratedStory
from app.models.analytics import LearningSession, DailyStats
from app.models.parent_analytics import DailyLearningStats, LearningInsight, WeeklyReport, ParentalControl
from app.models.content import Story, Mission, Game, StoryProgress
from app.models.generated_sentences import GeneratedSentence

from app.core.security import get_password_hash


async def setup_test_data():
    """Create test parent, child, and daily words for story generation"""
    
    print("=" * 80)
    print("BEDTIME STORY TEST DATA SETUP")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        # Check if test parent exists
        parent_email = "parent@test.com"
        parent_query = select(User).where(User.email == parent_email)
        result = await db.execute(parent_query)
        test_parent = result.scalar_one_or_none()
        
        if not test_parent:
            print("\n1. Creating test parent account...")
            test_parent = User(
                id="test-parent-ui",
                full_name="Test Parent",
                email=parent_email,
                hashed_password=get_password_hash("password123")
            )
            db.add(test_parent)
            await db.flush()
            print(f"   ✓ Created parent: {test_parent.email}")
            print(f"   ✓ Password: password123")
        else:
            print(f"\n1. ✓ Using existing parent: {test_parent.email}")
        
        # Check if test child exists
        child_query = select(Child).where(
            Child.parent_id == test_parent.id,
            Child.name == "小明"
        )
        result = await db.execute(child_query)
        test_child = result.scalar_one_or_none()
        
        if not test_child:
            print("\n2. Creating test child...")
            test_child = Child(
                id="test-child-ui",
                parent_id=test_parent.id,
                name="小明",
                age=4,
                language_preference="CANTONESE"
            )
            db.add(test_child)
            await db.flush()
            print(f"   ✓ Created child: {test_child.name} (age {test_child.age})")
        else:
            print(f"\n2. ✓ Using existing child: {test_child.name}")
        
        # Get some words for testing
        words_query = select(Word).limit(8)
        result = await db.execute(words_query)
        words = result.scalars().all()
        
        if len(words) < 3:
            print("\n❌ ERROR: Not enough words in database!")
            print("   Please run: python seed_cantonese_words.py")
            return
        
        print(f"\n3. Found {len(words)} words in database")
        for word in words[:5]:
            word_text = word.word_cantonese or word.word
            jyutping = f" ({word.jyutping})" if word.jyutping else ""
            print(f"   - {word_text}{jyutping}")
        if len(words) > 5:
            print(f"   ... and {len(words) - 5} more")
        
        # Delete old tracking data for this child
        print("\n4. Cleaning up old daily word tracking...")
        delete_query = delete(DailyWordTracking).where(
            DailyWordTracking.child_id == test_child.id
        )
        result = await db.execute(delete_query)
        deleted_count = result.rowcount
        if deleted_count > 0:
            print(f"   ✓ Removed {deleted_count} old tracking entries")
        
        # Create daily word tracking for TODAY
        print("\n5. Creating daily word tracking for TODAY...")
        today = datetime.now()
        
        for idx, word in enumerate(words[:8]):  # Use up to 8 words
            tracking = DailyWordTracking(
                child_id=test_child.id,
                word_id=word.id,
                date=today,
                exposure_count=idx + 1,
                used_actively=True,
                mastery_confidence=0.7 + (idx * 0.03),  # Varying confidence
                include_in_story=True,
                story_priority=10 - idx  # Higher priority for first words
            )
            db.add(tracking)
            
            word_text = word.word_cantonese or word.word
            print(f"   ✓ Added: {word_text} (priority: {tracking.story_priority})")
        
        await db.commit()
        
        print("\n" + "=" * 80)
        print("✅ TEST DATA SETUP COMPLETE!")
        print("=" * 80)
        
        print("\n📝 TEST INSTRUCTIONS:")
        print("-" * 80)
        print("1. Start the backend server:")
        print("   cd /path/to/backend && python main.py")
        print()
        print("2. Start the frontend:")
        print("   cd /path/to/frontend && npm run dev")
        print()
        print("3. Login to the UI:")
        print(f"   Email: {parent_email}")
        print("   Password: password123")
        print()
        print(f"4. Select child: {test_child.name}")
        print()
        print("5. Navigate to 'Stories' or 'Bedtime Stories' section")
        print()
        print("6. Click 'Generate Story' button")
        print()
        print("7. Select a theme (睡前/冒險/動物/家庭/大自然/友誼)")
        print()
        print("8. Story will be generated using today's learned words!")
        print()
        print("-" * 80)
        print("\n💡 API ENDPOINT:")
        print(f"   POST http://localhost:8000/api/v1/bedtime-stories/generate")
        print("   Headers: Authorization: Bearer <your_jwt_token>")
        print("   Body: {")
        print(f'     "child_id": "{test_child.id}",')
        print('     "theme": "bedtime",')
        print('     "word_count_target": 400,')
        print('     "reading_time_minutes": 5')
        print("   }")
        print()
        print("-" * 80)
        print(f"\n✅ Ready to test! Child '{test_child.name}' has {len(words[:8])} words learned today.")


if __name__ == "__main__":
    print("\n🚀 Setting up test data for bedtime story generation...\n")
    asyncio.run(setup_test_data())
