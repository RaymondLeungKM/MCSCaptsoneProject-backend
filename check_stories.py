#!/usr/bin/env python3
"""
Check generated stories in the database
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import select, text
from app.db.session import AsyncSessionLocal
from app.models.daily_words import GeneratedStory


async def check_stories():
    """Check stories in the database"""
    
    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("CHECKING GENERATED_STORIES TABLE")
        print("=" * 80)
        
        # Check if table exists
        try:
            result = await db.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'generated_stories'
                ORDER BY ordinal_position;
            """))
            columns = result.all()
            
            if not columns:
                print("❌ Table 'generated_stories' does not exist!")
                return
            
            print("\n✓ Table 'generated_stories' exists with columns:")
            for col in columns:
                nullable = "NULL" if col.is_nullable == "YES" else "NOT NULL"
                print(f"  - {col.column_name}: {col.data_type} ({nullable})")
            
        except Exception as e:
            print(f"❌ Error checking table structure: {e}")
            return
        
        # Check if there are any stories using raw SQL to avoid relationship issues
        try:
            result = await db.execute(text("SELECT COUNT(*) FROM generated_stories"))
            count = result.scalar()
            
            print(f"\n📊 Total stories in database: {count}")
            
            if count == 0:
                print("\n⚠️  No stories found in the database!")
                print("\nPossible reasons:")
                print("  1. Story generation test didn't complete successfully")
                print("  2. Database transaction wasn't committed")
                print("  3. Story generation code has an issue")
                print("  4. Migration wasn't run (but table exists, so unlikely)")
                return
            
            # Get all stories
            result = await db.execute(text("""
                SELECT id, title, child_id, generated_at, theme, 
                       story_generate_provdier, story_generate_model, 
                       word_count, LEFT(story_text, 100) as preview
                FROM generated_stories
                ORDER BY generated_at DESC
            """))
            stories = result.all()
            
            print("\n" + "=" * 80)
            print("STORIES IN DATABASE:")
            print("=" * 80)
            
            for idx, story in enumerate(stories, 1):
                print(f"\n{idx}. Story ID: {story.id}")
                print(f"   Title: {story.title}")
                print(f"   Child ID: {story.child_id}")
                print(f"   Generated: {story.generated_at}")
                print(f"   Theme: {story.theme}")
                print(f"   Provider: {story.story_generate_provdier}")
                print(f"   Model: {story.story_generate_model}")
                print(f"   Word Count: {story.word_count}")
                print(f"   Story Preview: {story.preview}...")
                
        except Exception as e:
            print(f"❌ Error querying stories: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_stories())
