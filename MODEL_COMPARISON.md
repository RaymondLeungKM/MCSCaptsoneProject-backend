# AI Model Comparison for Cantonese Word Enhancement

## Problem with qwen3 Models

qwen3:4b outputs "thinking process" instead of direct JSON answers. This is a model design feature that cannot be disabled.

## Solution Options

### Option 1: qwen2.5:7b (Recommended for Ollama)

**Best free local option**

```bash
ollama pull qwen2.5:7b
```

**Pros:**

- ✅ 7B parameters = much better instruction following
- ✅ Direct JSON output (no thinking mode)
- ✅ Excellent Cantonese + Jyutping
- ✅ Free and local (no API costs)
- ✅ Good for batch processing

**Cons:**

- ⚠️ 4.7GB model size
- ⚠️ Slower than smaller models
- ⚠️ Still not as good as GPT-4

**Usage:**

```bash
# Update .env
OLLAMA_MODEL=qwen2.5:7b

# Restart backend
pkill -f "python.*main.py"
python main.py
```

### Option 2: OpenAI GPT-4o (Recommended for Production)

**Best quality, minimal setup**

```bash
# Get API key from: https://platform.openai.com/api-keys
```

**Pros:**

- ✅ Excellent Cantonese + Jyutping accuracy
- ✅ Perfect JSON format every time
- ✅ Fast and reliable
- ✅ No local resources needed
- ✅ Best for production

**Cons:**

- 💰 Costs ~$0.0025 per word (very cheap)
- 💰 ~$2.50 for 1000 words

**Usage:**

```bash
# Update .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-actual-key-here

# Restart backend
pkill -f "python.*main.py"
python main.py
```

### Option 3: Anthropic Claude (Premium Alternative)

**Highest quality for complex content**

```bash
# Get API key from: https://console.anthropic.com/
```

**Pros:**

- ✅ Best reasoning and understanding
- ✅ Excellent Cantonese quality
- ✅ Long context (200K tokens)
- ✅ Very reliable

**Cons:**

- 💰 Costs ~$0.003 per word
- 💰 ~$3 for 1000 words

**Usage:**

```bash
# Update .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here

# Restart backend
pkill -f "python.*main.py"
python main.py
```

## Cost Comparison (1000 words)

| Model      | Cost  | Quality            | Speed  | Local |
| ---------- | ----- | ------------------ | ------ | ----- |
| qwen2.5:7b | FREE  | Good (7/10)        | Slow   | ✅    |
| GPT-4o     | $2.50 | Excellent (9/10)   | Fast   | ❌    |
| Claude 3.5 | $3.00 | Excellent (9.5/10) | Fast   | ❌    |
| qwen3:4b   | FREE  | Poor (3/10)        | Medium | ✅    |

## Recommendation by Use Case

### Development & Testing

**Use: qwen2.5:7b**

- Free for unlimited testing
- Good enough for development
- No API key setup needed

### Production (Small Scale)

**Use: OpenAI GPT-4o**

- Best quality/price ratio
- $2.50 per 1000 words
- Fast and reliable

### Production (High Quality)

**Use: Anthropic Claude**

- Best quality
- Worth the extra $0.50/1000 words
- Superior reasoning

### Batch Processing 10,000+ words

**Use: qwen2.5:7b first, then OpenAI for quality check**

- Process bulk with free model
- Spot-check quality with GPT-4
- Fix any errors with paid API

## Quick Setup Guide

### OpenAI Setup (5 minutes)

1. Get API key: https://platform.openai.com/api-keys
2. Add $5-10 to your account (lasts a long time)
3. Update .env:
   ```
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-proj-...your-key...
   ```
4. Restart backend
5. Test: `python test_improved_prompt.py`

### qwen2.5:7b Setup (10 minutes)

1. Download model: `ollama pull qwen2.5:7b` (wait ~5 min)
2. Update .env:
   ```
   OLLAMA_MODEL=qwen2.5:7b
   ```
3. Restart backend
4. Test: `python test_improved_prompt.py`

## Expected Results

### qwen2.5:7b Output

```json
{
  "word_english": "Dog",
  "word_cantonese": "狗",
  "jyutping": "gau2",
  "definition_english": "A friendly animal with four legs that barks",
  "definition_cantonese": "一種會吠嘅動物，有四隻腳",
  "example_english": "I see a dog in the park",
  "example_cantonese": "我喺公園見到一隻狗",
  "difficulty": "easy"
}
```

### GPT-4o Output (Better)

```json
{
  "word_english": "Dog",
  "word_cantonese": "狗",
  "jyutping": "gau2",
  "definition_english": "A friendly pet with four legs that wags its tail and says woof",
  "definition_cantonese": "一種友善嘅寵物，有四隻腳，會搖尾巴同埋吠",
  "example_english": "My dog likes to play fetch in the park",
  "example_cantonese": "我隻狗好鍾意喺公園玩拋波",
  "difficulty": "easy"
}
```

## Current Problem

Your qwen3:4b outputs thinking process instead of JSON:

```
首先，任務是為詞語 "Dog" 創建完整的雙語學習資料...
我需要參考提供的範例格式...
```

This is unfixable in qwen3 models. Switch to qwen2.5:7b or OpenAI.
