# Complete API Flow Testing Guide: AI Sentence Generation

## Overview

This guide walks you through testing the complete flow from mobile integration → sentence generation → database storage → frontend display.

## Architecture Flow

```
Mobile App/Object Detection
    ↓
POST /api/v1/vocabulary/external-learning
    ↓
    ├─ Create/Find Word
    ├─ Track Progress
    ├─ Award XP
    └─ Generate AI Sentences (auto-triggered) ✨
            ↓
    Save to generated_sentences table
            ↓
GET /api/v1/vocabulary/{word_id}/sentences
            ↓
    Frontend displays sentences to users
```

## Prerequisites

### 1. Start Ollama (for local LLM)

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Ensure model is available
ollama list
# If qwen3:4b not available:
ollama pull qwen3:4b
```

### 2. Start Backend

```bash
cd /Users/raymondleung/Desktop/CapstoneProject/WebsiteWorkspace/preschool-vocabulary-platform-backend

# Set environment variables
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen3:4b

# Start server
python main.py
```

Server should be running at: `http://localhost:8000`

### 3. Get Test IDs

You'll need a `child_id` from your database. Get one using:

```bash
# Using psql
psql -d preschool_vocab -U user -c "SELECT id, name FROM children LIMIT 1;"

# Or using Python
python -c "from app.db.session import SessionLocal; from app.models.user import Child; db = SessionLocal(); child = db.query(Child).first(); print(f'Child ID: {child.id}'); print(f'Name: {child.name}'); db.close()"
```

Example output:

```
Child ID: 550e8400-e29b-41d4-a716-446655440000
Name: Tommy
```

---

## Step-by-Step Testing

### Test 1: Mobile Integration Endpoint (Triggers Sentence Generation)

This endpoint simulates a mobile app detecting a word via object detection and automatically generates AI sentences.

#### Request

```bash
curl -X POST "http://localhost:8000/api/v1/vocabulary/external-learning" \
  -H "Content-Type: application/json" \
  -d '{
    "word": "Elephant",
    "child_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-02-06T12:00:00Z",
    "source": "object_detection",
    "confidence": 0.95,
    "image_url": "https://example.com/elephant.jpg"
  }'
```

#### Expected Response

```json
{
  "success": true,
  "word": "Elephant",
  "word_id": "new-word-uuid-123",
  "word_created": true,
  "child_id": "550e8400-e29b-41d4-a716-446655440000",
  "exposure_count": 1,
  "xp_awarded": 10,
  "new_level": 1,
  "current_xp": 10,
  "word_data": {
    "id": "new-word-uuid-123",
    "word": "Elephant",
    "category": "general-category-id",
    "category_name": "general",
    "definition": "A word learned from object_detection",
    "image_url": "https://example.com/elephant.jpg",
    "...": "..."
  }
}
```

#### Backend Logs to Watch For

```
[External Word Learning] Creating new word: 'Elephant'
[External Word Learning] New word created: Elephant (ID: new-word-uuid-123)
[External Word Learning] Generating AI sentences for new word: Elephant
[SentenceGenerator] Saved 3 sentences to DB for word: Elephant
[External Word Learning] AI sentences generated and saved for: Elephant
[External Word Learning] SUCCESS: Elephant learned by child ...
```

**✅ Success Indicators:**

- `word_created: true`
- Backend logs show "Generating AI sentences"
- Backend logs show "Saved 3 sentences to DB"
- No errors in terminal

---

### Test 2: Retrieve Generated Sentences

After the mobile endpoint creates the word and generates sentences, retrieve them:

#### Request

```bash
# Replace {word_id} with the word_id from Test 1 response
curl -X GET "http://localhost:8000/api/v1/vocabulary/{word_id}/sentences"
```

Example:

```bash
curl -X GET "http://localhost:8000/api/v1/vocabulary/new-word-uuid-123/sentences"
```

#### Expected Response

```json
[
  {
    "id": 1,
    "sentence": "大笨象在動物園玩",
    "sentence_english": "The big elephant is playing at the zoo",
    "jyutping": "daai6 ban6 zoeng6 zoi6 dung6 mat6 jyun4 waan2",
    "context": "home",
    "difficulty": "easy",
    "created_at": "2026-02-06T12:00:05.123Z"
  },
  {
    "id": 2,
    "sentence": "我見到大笨象",
    "sentence_english": "I see a big elephant",
    "jyutping": "ngo5 gin3 dou2 daai6 ban6 zoeng6",
    "context": "school",
    "difficulty": "easy",
    "created_at": "2026-02-06T12:00:05.456Z"
  },
  {
    "id": 3,
    "sentence": "大笨象好大隻",
    "sentence_english": "The elephant is very big",
    "jyutping": "daai6 ban6 zoeng6 hou2 daai6 zek3",
    "context": "home",
    "difficulty": "easy",
    "created_at": "2026-02-06T12:00:05.789Z"
  }
]
```

**✅ Success Indicators:**

- Returns array of 3 sentences
- Each sentence has Cantonese, English, and Jyutping
- Character count matches Jyutping syllable count
- `context` and `difficulty` are populated

---

### Test 3: Direct Sentence Generation (Manual Trigger)

You can also manually generate sentences for existing words:

#### Request

```bash
# Get a word ID first
curl -X GET "http://localhost:8000/api/v1/vocabulary/words" | grep '"id"' | head -1

# Generate sentences for that word
curl -X POST "http://localhost:8000/api/v1/vocabulary/{word_id}/generate-sentences?num_sentences=3" \
  -H "Content-Type: application/json"
```

Example for "爸爸" (Dad):

```bash
curl -X POST "http://localhost:8000/api/v1/vocabulary/dad-word-id/generate-sentences?num_sentences=3"
```

#### Expected Response

```json
{
  "word": "Dad",
  "word_cantonese": "爸爸",
  "sentences": [
    {
      "sentence": "爸爸在廚房煮飯",
      "sentence_english": "Dad is cooking in the kitchen",
      "jyutping": "baa4 baa1 zoi6 cyu4 fong2 zyu2 faan6",
      "context": "home",
      "difficulty": "easy"
    },
    {
      "sentence": "爸爸在學校教書",
      "sentence_english": "Dad is teaching at school",
      "jyutping": "baa4 baa1 zoi6 hok6 haau6 gaau3 syu1",
      "context": "school",
      "difficulty": "easy"
    },
    {
      "sentence": "爸爸在公園玩球",
      "sentence_english": "Dad is playing with a ball in the park",
      "jyutping": "baa4 baa1 zoi6 gung1 jyun4 waan2 kau4",
      "context": "park",
      "difficulty": "easy"
    }
  ],
  "total_generated": 3
}
```

---

### Test 4: Verify Database Storage

Check that sentences are actually saved in the database:

```bash
# Using psql
psql -d preschool_vocab -U user -c "
  SELECT
    gs.id,
    w.word,
    gs.sentence,
    gs.jyutping,
    gs.context,
    gs.created_at
  FROM generated_sentences gs
  JOIN words w ON gs.word_id = w.id
  ORDER BY gs.created_at DESC
  LIMIT 5;
"
```

#### Expected Output

```
 id |   word    |       sentence        |         jyutping          | context |       created_at
----+-----------+-----------------------+---------------------------+---------+------------------------
  3 | Elephant  | 大笨象好大隻           | daai6 ban6 zoeng6 hou2... | home    | 2026-02-06 12:00:05.789
  2 | Elephant  | 我見到大笨象           | ngo5 gin3 dou2 daai6...   | school  | 2026-02-06 12:00:05.456
  1 | Elephant  | 大笨象在動物園玩       | daai6 ban6 zoeng6 zoi6... | home    | 2026-02-06 12:00:05.123
```

---

## Frontend Integration Testing

### Option 1: Update Frontend to Display Sentences

You'll need to modify the frontend to fetch and display generated sentences. Here's the API call:

```typescript
// In your frontend code
const fetchWordSentences = async (wordId: string) => {
  const response = await fetch(
    `http://localhost:8000/api/v1/vocabulary/${wordId}/sentences`,
  );
  const sentences = await response.json();

  // Display sentences in UI
  sentences.forEach((sent) => {
    console.log(`${sent.sentence} (${sent.jyutping})`);
    console.log(`English: ${sent.sentence_english}`);
  });
};
```

### Option 2: Test with Browser

Open browser console and test directly:

```javascript
// Get sentences for a word
fetch("http://localhost:8000/api/v1/vocabulary/your-word-id/sentences")
  .then((r) => r.json())
  .then((data) => console.table(data));
```

---

## Troubleshooting

### Issue: "No sentences returned"

**Check:**

1. Word ID is correct: `curl http://localhost:8000/api/v1/vocabulary/words | grep word_id`
2. Sentences were generated: Check backend logs for "Saved X sentences to DB"
3. Database has records: Run SQL query from Test 4

**Fix:**

```bash
# Manually trigger generation
curl -X POST "http://localhost:8000/api/v1/vocabulary/{word_id}/generate-sentences?num_sentences=3"
```

---

### Issue: "Ollama connection refused"

**Check:**

```bash
# Is Ollama running?
ps aux | grep ollama

# Can you reach it?
curl http://localhost:11434/api/tags
```

**Fix:**

```bash
ollama serve
```

---

### Issue: "Jyutping is incorrect"

**Check:**

- Look at the actual output - count characters vs syllables
- Example: "爸爸在廚房煮飯" (7 chars) should have 7 Jyutping syllables

**Fix:**
The prompts have been updated with explicit examples. If still incorrect:

1. Try `qwen2.5` model: `export OLLAMA_MODEL=qwen2.5`
2. Or use OpenAI: `export LLM_PROVIDER=openai`

---

### Issue: "Database migration failed"

**Check:**

```bash
alembic current  # Check current migration
alembic history  # See all migrations
```

**Fix:**

```bash
# Run migration
alembic upgrade head

# If already applied
alembic downgrade -1
alembic upgrade head
```

---

## Complete End-to-End Test Script

Save this as `test_complete_flow.sh`:

```bash
#!/bin/bash

# Configuration
BACKEND_URL="http://localhost:8000"
CHILD_ID="550e8400-e29b-41d4-a716-446655440000"  # Replace with your child ID
TEST_WORD="Giraffe"

echo "=== Complete AI Sentence Generation Flow Test ==="
echo ""

# Step 1: Simulate mobile app learning
echo "Step 1: Simulating mobile object detection..."
RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/vocabulary/external-learning" \
  -H "Content-Type: application/json" \
  -d "{
    \"word\": \"${TEST_WORD}\",
    \"child_id\": \"${CHILD_ID}\",
    \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"source\": \"object_detection\",
    \"confidence\": 0.95
  }")

echo "$RESPONSE" | jq '.'
WORD_ID=$(echo "$RESPONSE" | jq -r '.word_id')
echo ""
echo "✅ Word ID: $WORD_ID"
echo ""

# Step 2: Wait for sentence generation
echo "Step 2: Waiting 5 seconds for AI sentence generation..."
sleep 5

# Step 3: Retrieve generated sentences
echo "Step 3: Fetching generated sentences..."
SENTENCES=$(curl -s -X GET "${BACKEND_URL}/api/v1/vocabulary/${WORD_ID}/sentences")
echo "$SENTENCES" | jq '.'
echo ""

# Step 4: Validate
SENTENCE_COUNT=$(echo "$SENTENCES" | jq 'length')
echo "✅ Generated sentences count: $SENTENCE_COUNT"

if [ "$SENTENCE_COUNT" -gt 0 ]; then
  echo ""
  echo "🎉 SUCCESS! Complete flow working:"
  echo "   1. Mobile integration ✅"
  echo "   2. Sentence generation ✅"
  echo "   3. Database storage ✅"
  echo "   4. API retrieval ✅"
else
  echo ""
  echo "⚠️  No sentences found. Check backend logs."
fi
```

Run with:

```bash
chmod +x test_complete_flow.sh
./test_complete_flow.sh
```

---

## Next Steps

1. **Frontend Display**: Update your frontend to call `/vocabulary/{word_id}/sentences` and display the generated sentences
2. **Speech Synthesis**: Integrate with your existing speech synthesis to read sentences aloud
3. **User Feedback**: Add ability for users to mark sentences as helpful (updates `helpful_count`)
4. **Quality Improvements**: Monitor `quality_score` and regenerate poor sentences

---

## API Documentation

- **POST** `/api/v1/vocabulary/external-learning` - Mobile integration (auto-generates sentences)
- **POST** `/api/v1/vocabulary/{word_id}/generate-sentences` - Manual sentence generation
- **GET** `/api/v1/vocabulary/{word_id}/sentences` - Retrieve saved sentences
- **GET** `/api/v1/vocabulary/words` - List all words

OpenAPI docs: http://localhost:8000/docs
