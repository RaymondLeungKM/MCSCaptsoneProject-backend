"""
Quick test of complete sentence generation flow
"""
import asyncio
import sys
from datetime import datetime
from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.vocabulary import Word
from app.models.generated_sentences import GeneratedSentence as GeneratedSentenceModel
from app.services.sentence_generator import get_sentence_generator


async def test_complete_flow():
    """Test the complete flow: create word -> generate sentences -> save to DB -> retrieve"""
    
    print("\n" + "="*60)
    print("Testing Complete Sentence Generation Flow")
    print("="*60 + "\n")
    
    async with AsyncSessionLocal() as db:
        # Step 1: Get a child ID for testing (using raw SQL to avoid model loading issues)
        result = await db.execute(text("SELECT id, name FROM children LIMIT 1"))
        child_row = result.first()
        
        if not child_row:
            print("❌ No child found in database. Please create a child first.")
            print("\nYou can create one via the API or run: python seed_data.py")
            return False
        
        child_id, child_name = child_row
        print(f"✅ Found test child: {child_name} (ID: {child_id})\n")
        
        # Step 2: Get or create a test word
        test_word_text = "Penguin"
        result = await db.execute(
            select(Word).where(Word.word.ilike(test_word_text))
        )
        word = result.scalar_one_or_none()
        
        if not word:
            print(f"⚠️  Word '{test_word_text}' not found. Use the mobile integration endpoint to create it.")
            print(f"\nRun this curl command:")
            print(f"""
curl -X POST "http://localhost:8000/api/v1/vocabulary/external-learning" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "word": "{test_word_text}",
    "child_id": "{child_id}",
    "timestamp": "{datetime.utcnow().isoformat()}Z",
    "source": "object_detection",
    "confidence": 0.95
  }}'
""")
            return False
        
        print(f"✅ Found test word: {word.word} (ID: {word.id})\n")
        
        # Step 3: Generate sentences
        print("🤖 Generating AI sentences...")
        generator = get_sentence_generator()
        
        try:
            result = await generator.generate_sentences(
                word=word,
                num_sentences=3,
                contexts=["home", "school"],
                db=db,
                save_to_db=True
            )
            
            print(f"✅ Generated {result.total_generated} sentences:\n")
            
            for i, sent in enumerate(result.sentences, 1):
                print(f"Sentence {i}:")
                print(f"  Cantonese: {sent.sentence}")
                print(f"  Jyutping:  {sent.jyutping}")
                print(f"  English:   {sent.sentence_english}")
                print(f"  Context:   {sent.context}")
                
                # Validate Jyutping
                char_count = len(sent.sentence)
                jyutping_count = len(sent.jyutping.split())
                
                if char_count == jyutping_count:
                    print(f"  ✅ Jyutping valid ({char_count} chars = {jyutping_count} syllables)")
                else:
                    print(f"  ⚠️  Jyutping mismatch ({char_count} chars ≠ {jyutping_count} syllables)")
                print()
            
        except Exception as e:
            print(f"❌ Error generating sentences: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Step 4: Verify database storage
        print("\n📊 Verifying database storage...")
        result = await db.execute(
            select(GeneratedSentenceModel)
            .where(GeneratedSentenceModel.word_id == word.id)
            .where(GeneratedSentenceModel.is_active == True)
        )
        db_sentences = result.scalars().all()
        
        print(f"✅ Found {len(db_sentences)} sentences in database\n")
        
        if len(db_sentences) > 0:
            print("Database records:")
            for i, sent in enumerate(db_sentences, 1):
                print(f"  {i}. {sent.sentence[:30]}... (ID: {sent.id})")
        
        # Step 5: Test retrieval
        print("\n🔍 Testing sentence retrieval...")
        print(f"GET /api/v1/vocabulary/{word.id}/sentences")
        print(f"\nYou can test this with:")
        print(f'curl http://localhost:8000/api/v1/vocabulary/{word.id}/sentences')
        
        print("\n" + "="*60)
        print("✅ COMPLETE FLOW TEST PASSED!")
        print("="*60)
        print("\nNext steps:")
        print("1. Start the backend: python main.py")
        print(f"2. Test API: curl http://localhost:8000/api/v1/vocabulary/{word.id}/sentences")
        print("3. Integrate into frontend to display sentences")
        print()
        
        return True


if __name__ == "__main__":
    success = asyncio.run(test_complete_flow())
    sys.exit(0 if success else 1)
