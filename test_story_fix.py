"""Test the fixed story generation with a valid child"""
import asyncio
import httpx
import json

async def test_story_generation():
    # Use a child that exists in the database
    child_id = "test-child-ollama"  # This child exists!
    
    url = "http://localhost:8000/api/v1/bedtime-stories/generate"
    
    payload = {
        "child_id": child_id,
        "theme": "bedtime",
        "word_count_target": 400,
        "reading_time_minutes": 5,
        "include_english": False,
        "include_jyutping": True
    }
    
    print(f"Testing story generation with child: {child_id}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    # First, check if we need authentication
    print("Note: This endpoint requires authentication.")
    print("If you get a 401 error, you need to login first and pass the token.")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload)
            
            print(f"Status Code: {response.status_code}")
            print()
            
            if response.status_code == 200:
                data = response.json()
                print("✅ SUCCESS! Story generated:")
                print(f"Title: {data.get('story', {}).get('title')}")
                print(f"Words used: {len(data.get('words_used', []))}")
                print(f"Generation time: {data.get('generation_time_seconds')}s")
            else:
                print(f"❌ Error: {response.status_code}")
                print(response.text)
                
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_story_generation())
