# Story Generation Error Fix

## Problem

Error: `"object of type 'NoneType' has no len()"`

## Root Causes

### 1. **NoneType Error in Story Content** (PRIMARY ISSUE - FIXED ✅)

The `_parse_story_json()` function could return a dictionary with `None` values for fields like `content`, `title`, etc. When the code tried to call `len()` on these None values, it crashed.

**Location:** `app/services/story_generator.py` lines 414-423

**Problem:**

```python
story_text_raw = story_data.get("content", "")  # Returns None if content is explicitly null
print(f"Raw content length: {len(story_text_raw)}")  # ❌ Crashes if None
```

The `.get(key, default)` method only returns the default when the key is _missing_, NOT when the value is explicitly `None`.

**Fix Applied:**

```python
# Use 'or' operator to handle None values
story_text_raw = story_data.get("content") or ""

if not story_text_raw:
    raise ValueError("AI response did not contain story content. Please try again.")

print(f"Raw content length: {len(story_text_raw)}")  # ✅ Now safe
```

### 2. **Invalid Child ID** (USER ERROR)

The child ID `44624173-4b69-42a7-a135-b0e035be436a` doesn't exist in your database.

**Available child IDs:**

- `test-child-ollama` - 測試小朋友 (Age 4)
- `test-child-ui` - 小明 (Age 4)
- `2a2e0b85-dd89-4ae3-90d4-c58ce0d488e0` - Elon (Age 4)
- `4e44eb00-7c10-44b1-8775-4f62d0e30ed8` - Elon (Age 4)

### 3. **Authentication Required**

The `/bedtime-stories/generate` endpoint requires user authentication. You need to:

1. Login via `/auth/login` first
2. Get the JWT token
3. Include it in the Authorization header: `Bearer <token>`

## Fixes Applied

### Fix 1: Robust None Handling in Story Generator ✅

**Files Changed:**

- `app/services/story_generator.py`

**Changes:**

1. Changed `story_data.get("content", "")` to `story_data.get("content") or ""`
2. Added validation to check if content is empty before proceeding
3. Updated type hints: `_clean_story_content(content: Optional[str])`
4. Fixed `word_usage` handling: `ai_word_usage = story_data.get("word_usage") or {}`
5. Fixed title handling: `title=story_data.get("title") or "今日的故事"`
6. Fixed title_english: `title_english=story_data.get("title_english") or "Story"`
7. Fixed word_count: Use `len(story_text)` instead of `len(story_data.get("content", ""))`

### Fix 2: Better Error Messages ✅

**Before:**

```
"Failed to generate story: object of type 'NoneType' has no len()"
```

**After:**

```
"AI response did not contain story content. Please try again."
```

## How to Test the Fix

### Option 1: Use Existing Test Child

```bash
# 1. Start backend (if not running)
cd /Users/raymondleung/Desktop/CapstoneProject/WebsiteWorkspace/preschool-vocabulary-platform-backend
uvicorn main:app --reload

# 2. Run the test script
python3.12 test_story_fix.py
```

### Option 2: Use Correct Child ID with Authentication

```bash
# First, login to get token
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "test-parent-ollama", "password": "your-password"}'

# Use the token in the story generation request
curl -X POST "http://localhost:8000/api/v1/bedtime-stories/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token-here>" \
  -d '{
    "child_id": "test-child-ollama",
    "theme": "bedtime",
    "word_count_target": 400,
    "reading_time_minutes": 5,
    "include_english": false,
    "include_jyutping": true
  }'
```

### Option 3: Track Some Words First

If you get "No words learned today" error, you need to track some words first:

```bash
curl -X POST "http://localhost:8000/api/v1/bedtime-stories/track-word" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token-here>" \
  -d '{
    "child_id": "test-child-ollama",
    "word_id": "some-word-id",
    "date": "2026-02-07T10:00:00Z",
    "exposure_count": 1,
    "used_actively": true,
    "mastery_confidence": 0.8,
    "learned_context": "learning",
    "include_in_story": true,
    "story_priority": 10
  }'
```

## Additional Improvements Made

1. **Type Safety:** Updated function signatures to properly handle `Optional[str]`
2. **Validation:** Added early validation for empty content
3. **Logging:** Added debug logging to help diagnose issues
4. **Robust Defaults:** All fields now have safe defaults instead of relying on `.get()` alone

## Model Configuration

The system is now configured to use **qwen2.5:1.5b** as specified. Make sure:

1. Ollama is running: `ollama serve`
2. Model is pulled: `ollama pull qwen2.5:1.5b`
3. Backend is restarted after .env changes

## Summary

✅ **Fixed:** NoneType error in story generation
✅ **Fixed:** Better None handling for all fields
✅ **Fixed:** Better error messages
✅ **Configured:** qwen2.5:1.5b model
⚠️ **User Action Required:** Use valid child ID and authentication token
