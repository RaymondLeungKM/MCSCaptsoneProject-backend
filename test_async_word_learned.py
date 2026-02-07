"""
Test async sentence generation in word-learned endpoint
"""
import asyncio
import httpx
import time
from datetime import datetime

async def test_word_learned_performance():
    """
    Test that word-learned API returns quickly without waiting for sentence generation
    """
    base_url = "http://localhost:8000"
    
    # Test data
    word = f"TestWord{int(time.time())}"  # Unique word
    test_data = {
        "word": word,
        "child_id": "test-child-id-123",  # Replace with actual child ID
        "source": "object_detection",
        "timestamp": datetime.now().isoformat() + "Z",
        "confidence": 0.95
    }
    
    print(f"\n🧪 Testing async word-learned endpoint")
    print(f"   Word: {word}")
    print(f"   Expected: API returns in <2 seconds (without waiting for sentence generation)")
    
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/v1/vocabulary/external/word-learned",
            data=test_data
        )
    
    elapsed = time.time() - start_time
    
    print(f"\n📊 Results:")
    print(f"   Status: {response.status_code}")
    print(f"   Response time: {elapsed:.2f} seconds")
    
    if response.status_code == 200:
        result = response.json()
        print(f"   ✓ Word created: {result.get('word_created')}")
        print(f"   ✓ Word ID: {result.get('word_id')}")
        print(f"   ✓ XP awarded: {result.get('xp_awarded')}")
    
    # Performance assessment
    if elapsed < 2.0:
        print(f"\n✅ PASS: API responded quickly ({elapsed:.2f}s)")
        print(f"   Sentence generation is running in background!")
    elif elapsed < 5.0:
        print(f"\n⚠️  MARGINAL: API took {elapsed:.2f}s")
        print(f"   Could be AI enhancement or other processing")
    else:
        print(f"\n❌ FAIL: API took {elapsed:.2f}s")
        print(f"   Sentence generation might still be blocking!")
    
    print(f"\n💡 Check server logs for '[Background Task]' messages")
    print(f"   to confirm sentence generation is running async")

if __name__ == "__main__":
    asyncio.run(test_word_learned_performance())
