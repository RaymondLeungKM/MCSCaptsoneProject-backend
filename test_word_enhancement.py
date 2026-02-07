"""
Test Word Enhancement Service
Test the AI-powered bilingual content generation
"""
import asyncio
from app.services.word_enhancement_service import get_word_enhancement_service


async def test_word_enhancement():
    print("=" * 70)
    print("🧪 Testing Word Enhancement Service")
    print("=" * 70)
    print()
    
    # Test words
    test_words = [
        ("Cat", "object_detection"),
        ("Dog", "object_detection"),
        ("Apple", "object_detection"),
        ("Ball", "physical_activity"),
    ]
    
    service = get_word_enhancement_service()
    
    for word, source in test_words:
        print(f"\n{'─' * 70}")
        print(f"📝 Testing: {word} (source: {source})")
        print(f"{'─' * 70}")
        
        try:
            result = await service.enhance_word(
                word=word,
                source=source
            )
            
            print(f"✅ SUCCESS!")
            print(f"\n**English Content:**")
            print(f"  Word: {result.word_english}")
            print(f"  Definition: {result.definition_english}")
            print(f"  Example: {result.example_english}")
            
            print(f"\n**Cantonese Content:**")
            print(f"  Word: {result.word_cantonese}")
            print(f"  Jyutping: {result.jyutping}")
            print(f"  Definition: {result.definition_cantonese}")
            print(f"  Example: {result.example_cantonese}")
            
            print(f"\n**Metadata:**")
            print(f"  Difficulty: {result.difficulty}")
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'=' * 70}")
    print("✅ Test Complete!")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    print("\n⚠️  Make sure Ollama is running!")
    print("   Run: ollama serve")
    print("   And have a model loaded (e.g., qwen2.5)\n")
    
    input("Press Enter to start test...")
    asyncio.run(test_word_enhancement())
