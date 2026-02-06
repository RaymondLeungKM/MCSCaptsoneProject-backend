#!/usr/bin/env python3
"""
Test script for bedtime story generation with Ollama

This script tests the story generation functionality using a local Ollama model.
Make sure Ollama is running and you have pulled a suitable model.

Usage:
    python test_story_generation_ollama.py

Prerequisites:
    1. Install Ollama: https://ollama.ai/
    2. Start Ollama: ollama serve
    3. Pull a model: ollama pull qwen3:4b (or another model)
"""
import asyncio
import sys
import os
from datetime import datetime
from sqlalchemy import select

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.db.session import AsyncSessionLocal

# Import all models to ensure SQLAlchemy can resolve relationships
from app.models.user import User, Child, ChildInterest
from app.models.vocabulary import Word, Category, WordProgress
from app.models.daily_words import DailyWordTracking, GeneratedStory
from app.models.analytics import LearningSession, DailyStats
from app.models.parent_analytics import DailyLearningStats, LearningInsight, WeeklyReport, ParentalControl
from app.models.content import Story, Mission, Game
from app.models.generated_sentences import GeneratedSentence
from app.services.story_generator import StoryGeneratorService
from app.services.llm_service import LLMProvider
from app.schemas.stories import StoryGenerationRequest


async def create_test_data(db):
    """Create test parent, child, and daily words if they don't exist"""
    
    # Check if test child exists
    child_query = select(Child).where(Child.name == "測試小朋友")
    result = await db.execute(child_query)
    test_child = result.scalar_one_or_none()
    
    if not test_child:
        print("Creating test parent and child...")
        
        # Create test parent
        test_parent = User(
            id="test-parent-ollama",
            full_name="測試家長",
            email=f"test-ollama-{datetime.now().timestamp()}@example.com",
            hashed_password="test"
        )
        db.add(test_parent)
        await db.flush()
        
        # Create test child
        test_child = Child(
            id="test-child-ollama",
            parent_id=test_parent.id,
            name="測試小朋友",
            age=4,
            language_preference="CANTONESE"
        )
        db.add(test_child)
        await db.commit()
        print(f"Created test child: {test_child.id}")
    else:
        print(f"Using existing test child: {test_child.id}")
    
    # Get some words for testing
    words_query = select(Word).limit(5)
    result = await db.execute(words_query)
    words = result.scalars().all()
    
    if len(words) < 3:
        print("Error: Not enough words in database. Please run seed_cantonese_words.py first.")
        return None, []
    
    print(f"\nFound {len(words)} words for story generation:")
    for word in words:
        print(f"  - {word.word_cantonese} ({word.jyutping}): {word.definition_cantonese}")
    
    # Create daily word tracking entries
    print("\nCreating daily word tracking entries...")
    today = datetime.now()
    
    for idx, word in enumerate(words):
        # Check if tracking already exists
        tracking_query = select(DailyWordTracking).where(
            DailyWordTracking.child_id == test_child.id,
            DailyWordTracking.word_id == word.id,
            DailyWordTracking.date >= today.replace(hour=0, minute=0, second=0)
        )
        result = await db.execute(tracking_query)
        existing = result.scalar_one_or_none()
        
        if not existing:
            tracking = DailyWordTracking(
                child_id=test_child.id,
                word_id=word.id,
                date=today,
                exposure_count=idx + 1,
                used_actively=True,
                mastery_confidence=0.7,
                include_in_story=True,
                story_priority=10 - idx
            )
            db.add(tracking)
    
    await db.commit()
    print("Daily word tracking created successfully!")
    
    return test_child, words


async def test_story_generation():
    """Test story generation with Ollama"""
    
    print("=" * 80)
    print("BEDTIME STORY GENERATION TEST (Ollama)")
    print("=" * 80)
    
    # Check if Ollama is accessible
    print("\nChecking Ollama connection...")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{ollama_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]
                print(f"✓ Ollama is running at {ollama_url}")
                print(f"  Available models: {', '.join(model_names)}")
                
                if ollama_model not in model_names:
                    print(f"\n⚠ Warning: Model '{ollama_model}' not found!")
                    print(f"  Please run: ollama pull {ollama_model}")
                    return
            else:
                print(f"✗ Ollama returned status code: {response.status_code}")
                return
    except Exception as e:
        print(f"✗ Cannot connect to Ollama at {ollama_url}")
        print(f"  Error: {e}")
        print("\nPlease ensure:")
        print("  1. Ollama is installed: https://ollama.ai/")
        print("  2. Ollama is running: ollama serve")
        print(f"  3. Model is pulled: ollama pull {ollama_model}")
        return
    
    # Create database session
    async with AsyncSessionLocal() as db:
        # Create test data
        test_child, words = await create_test_data(db)
        
        if not test_child:
            return
        
        # Initialize story generator with Ollama
        print(f"\nInitializing story generator with Ollama (model: {ollama_model})...")
        story_generator = StoryGeneratorService(provider=LLMProvider.OLLAMA)
        
        # Create story generation request
        request = StoryGenerationRequest(
            child_id=test_child.id,
            theme="bedtime",
            word_count_target=400,
            reading_time_minutes=5
        )
        
        print("\n" + "=" * 80)
        print("GENERATING STORY...")
        print("=" * 80)
        print(f"Child: {test_child.name} (age {test_child.age})")
        print(f"Theme: {request.theme}")
        print(f"Target length: {request.word_count_target} characters")
        print(f"Using words: {', '.join([w.word_cantonese or w.word for w in words])}")
        print("\nThis may take 1-2 minutes with local models...\n")
        
        try:
            # Generate story
            story, words_used, generation_time = await story_generator.generate_story(db, request)
            
            print("\n" + "=" * 80)
            print("STORY GENERATED SUCCESSFULLY!")
            print("=" * 80)
            print(f"\nTitle: {story.title}")
            if story.title_english:
                print(f"English Title: {story.title_english}")
            print(f"\nGeneration Time: {generation_time:.2f} seconds")
            print(f"Word Count: {story.word_count} characters")
            print(f"Model: {story.story_generate_model}")
            print(f"Provider: {story.story_generate_provdier}")
            print(f"\nStory ID: {story.id}")
            
            print("\n" + "-" * 80)
            print("STORY CONTENT:")
            print("-" * 80)
            print(story.story_text)
            print("-" * 80)
            
            print("\n" + "-" * 80)
            print("VOCABULARY USAGE:")
            print("-" * 80)
            if story.word_usage:
                for word, usage in story.word_usage.items():
                    print(f"  {word}: {usage}")
            else:
                print("  (No word usage metadata)")
            
            print("\n" + "-" * 80)
            print("WORDS USED IN GENERATION:")
            print("-" * 80)
            for word in words_used:
                word_text = word.word_cantonese or word.word or "Unknown"
                jyutping = word.jyutping or "N/A"
                definition = word.definition_cantonese or word.definition or "No definition"
                print(f"  • {word_text} ({jyutping})")
                print(f"    {definition}")
                print(f"    Exposure: {word.exposure_count}x, Priority: {word.story_priority}")
            
            print("\n" + "=" * 80)
            print("TEST COMPLETED SUCCESSFULLY!")
            print("=" * 80)
            print(f"\nThe story has been saved to the database.")
            print(f"You can view it at: /api/v1/bedtime-stories/{test_child.id}/{story.id}")
            
        except Exception as e:
            print("\n" + "=" * 80)
            print("ERROR GENERATING STORY")
            print("=" * 80)
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("\nStarting story generation test with Ollama...")
    print("Make sure:")
    print("  1. Database is running and populated with Cantonese words")
    print("  2. Ollama is running (ollama serve)")
    print("  3. A suitable model is pulled (e.g., ollama pull qwen3:4b)")
    print()
    
    asyncio.run(test_story_generation())
