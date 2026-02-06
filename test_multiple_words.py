"""
Test sentence generation for multiple words to validate Jyutping accuracy
"""
import asyncio
import os
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models import user, vocabulary, content, analytics, daily_words, parent_analytics
from app.models.vocabulary import Word
from app.services.sentence_generator import get_sentence_generator
from app.services.llm_service import LLMProvider

async def test_multiple_words():
    """Test sentence generation for different words"""
    
    # Determine which LLM provider to use
    provider = LLMProvider.OLLAMA  # Default to Ollama
    
    if os.getenv("LLM_PROVIDER", "").lower() == "openai":
        provider = LLMProvider.OPENAI
    elif os.getenv("LLM_PROVIDER", "").lower() == "anthropic":
        provider = LLMProvider.ANTHROPIC
    
    print(f"\n{'='*60}")
    if provider == LLMProvider.OLLAMA:
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
        print(f"🦙 Using Ollama (local model)")
        print(f"   Model: {ollama_model}")
        print(f"   Recommended for Cantonese: qwen2.5")
    elif provider == LLMProvider.OPENAI:
        print(f"🤖 Using OpenAI GPT-4o")
    else:
        print(f"🤖 Using Anthropic Claude 3.5 Sonnet")
    print(f"{'='*60}\n")
    
    async with AsyncSessionLocal() as session:
        # Get words from different categories
        result = await session.execute(
            select(Word)
            .where(Word.word_cantonese.isnot(None))
            .options(selectinload(Word.category_rel))
            .limit(5)  # Test 5 different words
        )
        words = result.scalars().all()
        
        if not words:
            print("❌ No Cantonese words found in database")
            return
        
        print(f"🔍 Found {len(words)} words to test\n")
        
        generator = get_sentence_generator()
        
        for idx, word in enumerate(words, 1):
            print(f"\n{'='*60}")
            print(f"Test {idx}/{len(words)}")
            print(f"{'='*60}")
            print(f"📝 Word: {word.word} / {word.word_cantonese}")
            print(f"   Category: {word.category}")
            
            try:
                # Generate 2 sentences for each word
                result = await generator.generate_sentences(
                    word=word,
                    num_sentences=2,
                    contexts=["home", "school"]
                )
                
                sentences = result.sentences
                
                print(f"\n✅ Generated {len(sentences)} sentences:\n")
                
                for i, sent in enumerate(sentences, 1):
                    print(f"句子 {i}:")
                    print(f"  Cantonese: {sent.sentence}")
                    print(f"  Jyutping:  {sent.jyutping}")
                    print(f"  English:   {sent.sentence_english}")
                    print(f"  Context:   {sent.context}")
                    
                    # Verify character count matches Jyutping syllable count
                    char_count = len(sent.sentence)
                    jyutping_parts = sent.jyutping.split()
                    jyutping_count = len(jyutping_parts)
                    
                    if char_count == jyutping_count:
                        print(f"  ✅ Character count ({char_count}) matches Jyutping count ({jyutping_count})")
                    else:
                        print(f"  ⚠️  WARNING: Character count ({char_count}) != Jyutping count ({jyutping_count})")
                    print()
                
            except Exception as e:
                print(f"❌ Error generating sentences: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print("✅ Multi-word test completed!")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(test_multiple_words())
