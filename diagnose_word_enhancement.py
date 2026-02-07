"""
Diagnostic Script for Word Enhancement Issues
Run this to check why batch enhancement is failing
"""
import asyncio
import sys
from app.services.word_enhancement_service import get_word_enhancement_service
from app.services.llm_service import get_llm_service, LLMProvider


async def test_llm_basic():
    """Test if LLM is responding at all"""
    print("=" * 70)
    print("1. Testing Basic LLM Connectivity")
    print("=" * 70)
    
    llm = get_llm_service(LLMProvider.OLLAMA)
    
    try:
        response = await llm.generate(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in one word."}
            ],
            temperature=0.5,
            max_tokens=50
        )
        print(f"✅ LLM is responding!")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"❌ LLM Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_json_generation():
    """Test if LLM can generate valid JSON"""
    print("\n" + "=" * 70)
    print("2. Testing JSON Generation")
    print("=" * 70)
    
    llm = get_llm_service(LLMProvider.OLLAMA)
    
    prompt = """Generate a JSON object about a cat. Format:

{
  "animal": "cat",
  "sound": "meow",
  "color": "orange"
}

Output only valid JSON, no other text:"""
    
    try:
        response = await llm.generate(
            messages=[
                {"role": "system", "content": "You are a JSON generator. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        print(f"✅ LLM Response received")
        print(f"Raw response:\n{response}")
        print()
        
        # Try to parse it
        import json
        response_text = response.strip()
        
        # Extract JSON
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            if start_idx != -1:
                response_text = response_text[start_idx:]
        
        if not response_text.endswith("}"):
            end_idx = response_text.rfind("}")
            if end_idx != -1:
                response_text = response_text[:end_idx + 1]
        
        data = json.loads(response_text)
        print(f"✅ JSON parsed successfully!")
        print(f"Parsed data: {data}")
        return True
        
    except Exception as e:
        print(f"❌ JSON Test Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_word_enhancement():
    """Test actual word enhancement"""
    print("\n" + "=" * 70)
    print("3. Testing Word Enhancement Service")
    print("=" * 70)
    
    service = get_word_enhancement_service()
    test_word = "Dog"
    
    try:
        result = await service.enhance_word(
            word=test_word,
            source="diagnostic_test"
        )
        
        print(f"✅ Enhancement succeeded!")
        print(f"\n**Results:**")
        print(f"  English: {result.word_english}")
        print(f"  Cantonese: {result.word_cantonese}")
        print(f"  Jyutping: {result.jyutping}")
        print(f"  Definition (EN): {result.definition_english}")
        print(f"  Definition (粵): {result.definition_cantonese}")
        print(f"  Example (EN): {result.example_english}")
        print(f"  Example (粵): {result.example_cantonese}")
        print(f"  Difficulty: {result.difficulty}")
        
        # Check if it's fallback content
        if "learned through observation" in result.definition_english.lower():
            print(f"\n⚠️  WARNING: This is FALLBACK content, not AI-generated!")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Enhancement Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n" + "🔍" * 35)
    print("WORD ENHANCEMENT DIAGNOSTIC TOOL")
    print("🔍" * 35)
    print()
    
    # Check 1: Basic LLM
    llm_ok = await test_llm_basic()
    if not llm_ok:
        print("\n❌ DIAGNOSIS: Ollama is not running or not responding")
        print("   Fix: Run 'ollama serve' in a terminal")
        sys.exit(1)
    
    # Check 2: JSON generation
    json_ok = await test_json_generation()
    if not json_ok:
        print("\n⚠️  DIAGNOSIS: LLM is not generating valid JSON")
        print("   This might be a model issue or prompt issue")
    
    # Check 3: Word enhancement
    enhance_ok = await test_word_enhancement()
    if not enhance_ok:
        print("\n❌ DIAGNOSIS: Word enhancement is failing")
        print("   Check the logs above for specific errors")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print("\nWord enhancement should be working correctly.")
    print("If you're still seeing fallback content, check:")
    print("  1. Are you using the right API endpoint?")
    print("  2. Is the batch-enhance finding the right words?")
    print("  3. Check server logs for specific errors")
    print()


if __name__ == "__main__":
    print("\n⚠️  Prerequisites:")
    print("   - Ollama must be running: ollama serve")
    print("   - A model must be loaded: ollama pull qwen2.5")
    print()
    
    asyncio.run(main())
