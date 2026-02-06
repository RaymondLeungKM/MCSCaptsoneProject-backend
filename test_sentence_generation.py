"""
Test script for sentence generation
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


async def test_sentence_generation():
    """Test generating sentences for a word"""
    
    # Determine which provider to use
    provider = LLMProvider.OLLAMA  # Default to Ollama
    
    if os.getenv("OPENAI_API_KEY"):
        print("✓ OpenAI API key found")
        use_openai = input("Use OpenAI instead of Ollama? (y/n): ").lower().strip() == 'y'
        if use_openai:
            provider = LLMProvider.OPENAI
    elif os.getenv("ANTHROPIC_API_KEY"):
        print("✓ Anthropic API key found")
        use_anthropic = input("Use Anthropic instead of Ollama? (y/n): ").lower().strip() == 'y'
        if use_anthropic:
            provider = LLMProvider.ANTHROPIC
    
    if provider == LLMProvider.OLLAMA:
        print("\n🦙 Using Ollama (local model)")
        print("   Make sure Ollama is running: ollama serve")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        print(f"   Model: {model}")
        print(f"   Pull model if needed: ollama pull {model}")
        print(f"   Base URL: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        print("\n   Recommended models for Cantonese:")
        print("   - llama3.2 (latest, general purpose)")
        print("   - llama3.1 (good multilingual support)")
        print("   - qwen2.5 (excellent Chinese language model)")
        print("   Set model: export OLLAMA_MODEL=qwen2.5")
        print()
    else:
        print(f"\n🌐 Using {provider.value}")
    
    print("🔍 Looking for a word to test...")
    
    async with AsyncSessionLocal() as db:
        # Get a word (preferably one with Cantonese content)
        result = await db.execute(
            select(Word)
            .options(selectinload(Word.category_rel))
            .where(Word.word_cantonese.isnot(None))
            .limit(1)
        )
        word = result.scalar_one_or_none()
        
        if not word:
            print("❌ No words found in database with Cantonese content")
            return
        
        print(f"\n📝 Testing with word:")
        print(f"   English: {word.word}")
        print(f"   Cantonese: {word.word_cantonese}")
        print(f"   Category: {word.category_rel.name if word.category_rel else 'N/A'}")
        print(f"   Definition: {word.definition_cantonese or word.definition}")
        
        print(f"\n🤖 Generating sentences using {provider.value}...")
        
        try:
            generator = get_sentence_generator(provider=provider)
            result = await generator.generate_sentences(
                word=word,
                num_sentences=3
            )
            
            print(f"\n✅ Successfully generated {result.total_generated} sentences!\n")
            print("=" * 60)
            
            for i, sentence in enumerate(result.sentences, 1):
                print(f"\n句子 {i}:")
                print(f"  Cantonese: {sentence.sentence}")
                if sentence.jyutping:
                    print(f"  Jyutping:  {sentence.jyutping}")
                if sentence.sentence_english:
                    print(f"  English:   {sentence.sentence_english}")
                print(f"  Context:   {sentence.context}")
                print(f"  Difficulty: {sentence.difficulty}")
            
            print("\n" + "=" * 60)
            print("✅ Sentence generation test completed successfully!")
            
        except Exception as e:
            print(f"\n❌ ERROR generating sentences: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_sentence_generation())
