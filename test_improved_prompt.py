"""
Test the improved word enhancement prompt
Run this after restarting the backend with qwen3:4b model
"""
import asyncio
import sys
import os
sys.path.append('.')

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from app.services.word_enhancement_service import WordEnhancementService


async def test_enhancement():
    """Test word enhancement with improved prompt"""
    
    print("="*60)
    print("Testing Improved Word Enhancement")
    print("="*60)
    
    service = WordEnhancementService()
    
    # Test with a simple word
    test_word = "Dog"
    
    print(f"\n🔍 Testing word: {test_word}")
    print("="*60)
    
    try:
        result = await service.enhance_word(
            word=test_word,
            source="object_detection"
        )
        
        print("\n✅ SUCCESS! Generated content:")
        print("="*60)
        print(f"📝 English: {result.word_english}")
        print(f"📝 Cantonese: {result.word_cantonese}")
        print(f"🔊 Jyutping: {result.jyutping}")
        print(f"📖 Definition (EN): {result.definition_english}")
        print(f"📖 Definition (粵): {result.definition_cantonese}")
        print(f"💬 Example (EN): {result.example_english}")
        print(f"💬 Example (粵): {result.example_cantonese}")
        print(f"📊 Difficulty: {result.difficulty}")
        
        # Check if we still have placeholder text
        placeholders = [
            "粵語詞語（繁體中文）",
            "完整正確的粵語拼音",
            "簡單的粵語定義",
            "一個簡單的粵語例句"
        ]
        
        found_placeholders = []
        for field_name, field_value in result.dict().items():
            for placeholder in placeholders:
                if placeholder in str(field_value):
                    found_placeholders.append(f"{field_name}: {placeholder}")
        
        if found_placeholders:
            print("\n⚠️  WARNING: Still found placeholder text:")
            for fp in found_placeholders:
                print(f"  - {fp}")
            print("\nThis means the model is still struggling. Consider:")
            print("  1. Using a larger model (try qwen3:8b or qwen2.5:7b)")
            print("  2. Or use OpenAI/Anthropic for better quality")
        else:
            print("\n✅ No placeholder text found - prompt fix worked!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure Ollama is running (ollama serve)")
        print("  2. Check you've pulled qwen3:4b (ollama pull qwen3:4b)")
        print("  3. Restart backend server to pick up new model")


if __name__ == "__main__":
    print("\n⚙️  Current configuration:")
    print(f"  - Model from .env: {os.getenv('OLLAMA_MODEL', 'NOT SET')}")
    print("  - Expected: qwen3:4b (or larger)")
    print("\n🔄 Make sure you've restarted the backend server!\n")
    
    asyncio.run(test_enhancement())
