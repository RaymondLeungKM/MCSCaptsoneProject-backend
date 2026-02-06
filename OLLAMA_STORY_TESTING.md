# Testing Story Generation with Ollama (Local LLM)

This guide shows you how to test bedtime story generation locally using Ollama, **completely free** without requiring OpenAI or Anthropic API keys.

## What is Ollama?

[Ollama](https://ollama.ai/) allows you to run large language models (LLMs) locally on your computer. This is perfect for:

- 🆓 **Free testing** - No API costs
- 🔒 **Privacy** - Data never leaves your machine
- ⚡ **Fast iteration** - No API rate limits
- 🧪 **Development** - Test without burning through API credits

## Prerequisites

1. **Computer Requirements**
   - **Minimum**: 8GB RAM, modern CPU
   - **Recommended**: 16GB+ RAM, Apple Silicon or modern GPU
2. **Operating System**
   - macOS, Linux, or Windows (WSL2)

## Installation Steps

### 1. Install Ollama

**macOS:**

```bash
# Download from https://ollama.ai/download
# Or use Homebrew:
brew install ollama
```

**Linux:**

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**Windows:**

- Use WSL2 and follow Linux instructions
- Or download Windows preview from https://ollama.ai/download

### 2. Start Ollama Server

```bash
ollama serve
```

Leave this terminal window open. Ollama will run in the background on `http://localhost:11434`.

### 3. Pull a Language Model

Open a **new terminal** and pull a model suitable for Cantonese/Chinese text generation:

**Option 1: Lightweight Model (Recommended for testing)**

```bash
# Qwen 2.5 1.7B - Fast, good for testing (1.3GB)
ollama pull qwen3:4b
```

**Option 2: Better Quality**

```bash
# Qwen 2.5 7B - Better quality, slower (4.7GB)
ollama pull qwen2.5:7b

# Qwen 2.5 14B - High quality, requires more RAM (9GB)
ollama pull qwen2.5:14b
```

**Option 3: General Purpose**

```bash
# Llama 3.1 8B - Good general model (4.7GB)
ollama pull llama3.1:8b
```

> **Note**: Qwen models are specifically trained on Chinese text and work better for Cantonese story generation.

### 4. Verify Installation

```bash
# List installed models
ollama list

# Test the model
ollama run qwen3:4b "請用繁體中文講一個故事"
```

## Configuration

### 1. Update Your `.env` File

Create a `.env` file (copy from `.env.example` if needed) and set:

```bash
# Use Ollama as the LLM provider
LLM_PROVIDER=ollama

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b

# Optional: Keep API keys empty for Ollama-only testing
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

### 2. Database Setup

Make sure your database is set up and populated with Cantonese vocabulary:

```bash
# Create database (if not already created)
python create_db.py

# Seed Cantonese vocabulary
python seed_cantonese_words.py
```

## Testing Story Generation

### Run the Test Script

```bash
cd /path/to/preschool-vocabulary-platform-backend
python test_story_generation_ollama.py
```

The script will:

1. ✅ Check Ollama connection
2. ✅ Verify model availability
3. ✅ Create test child and daily word data
4. ✅ Generate a bedtime story using learned words
5. ✅ Display the generated story and metadata

### Expected Output

```
================================================================================
BEDTIME STORY GENERATION TEST (Ollama)
================================================================================

Checking Ollama connection...
✓ Ollama is running at http://localhost:11434
  Available models: qwen3:4b, llama3.1:8b

Found 5 words for story generation:
  - 蘋果 (ping4 gwo2): 一種紅色或綠色的水果
  - 狗 (gau2): 一種忠心的寵物
  - 太陽 (taai3 joeng4): 天空中發光發熱的星球
  ...

Initializing story generator with Ollama (model: qwen3:4b)...

================================================================================
GENERATING STORY...
================================================================================
Child: 測試小朋友 (age 4)
Theme: bedtime
Using words: 蘋果, 狗, 太陽, 樹, 公園

This may take 1-2 minutes with local models...

================================================================================
STORY GENERATED SUCCESSFULLY!
================================================================================

Title: 小明的公園冒險
English Title: Siu Ming's Park Adventure

Generation Time: 45.23 seconds
Word Count: 387 characters
Model: qwen3:4b
Provider: ollama

--------------------------------------------------------------------------------
STORY CONTENT:
--------------------------------------------------------------------------------
小明今日好開心，因為媽媽帶佢去公園玩。天氣好好，太陽暖暖地照住大地...
(Full story content)
--------------------------------------------------------------------------------
```

## Testing via API Endpoint

You can also test story generation through the API:

### 1. Start the Backend Server

```bash
# In one terminal
uvicorn main:app --reload --port 8000
```

### 2. Call the Story Generation Endpoint

```bash
# Create a test request
curl -X POST "http://localhost:8000/api/v1/bedtime-stories/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "child_id": "test-child-id",
    "theme": "bedtime",
    "word_count_target": 400,
    "reading_time_minutes": 5
  }'
```

## Model Comparison

| Model       | Size  | Speed       | Quality            | Chinese Support | Recommended For |
| ----------- | ----- | ----------- | ------------------ | --------------- | --------------- |
| qwen3:4b    | 1.3GB | ⚡⚡⚡ Fast | ⭐⭐ Good          | ✅ Excellent    | Quick testing   |
| qwen2.5:7b  | 4.7GB | ⚡⚡ Medium | ⭐⭐⭐ Very Good   | ✅ Excellent    | Development     |
| qwen2.5:14b | 9GB   | ⚡ Slow     | ⭐⭐⭐⭐ Excellent | ✅ Excellent    | Production-like |
| llama3.1:8b | 4.7GB | ⚡⚡ Medium | ⭐⭐⭐ Very Good   | ⚠️ Okay         | General purpose |

## Switching Between Providers

You can easily switch between Ollama, OpenAI, and Anthropic:

### Use Ollama (Local, Free)

```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:4b
```

### Use OpenAI (Cloud, Paid)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

### Use Anthropic Claude (Cloud, Paid)

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Troubleshooting

### Error: "Cannot connect to Ollama"

**Solution:**

```bash
# Make sure Ollama is running
ollama serve

# Check if it's accessible
curl http://localhost:11434/api/tags
```

### Error: "Model not found"

**Solution:**

```bash
# Pull the model
ollama pull qwen3:4b

# Verify it's installed
ollama list
```

### Story generation is too slow

**Solutions:**

1. Use a smaller model: `qwen3:4b` instead of larger models
2. Reduce `word_count_target` in the request (e.g., 200-300 instead of 400)
3. Use fewer words in the story (modify daily word tracking limit)
4. If you have a GPU, ensure Ollama is using it

### Story quality is poor

**Solutions:**

1. Upgrade to a larger model: `qwen2.5:7b` or `qwen2.5:14b`
2. Adjust the prompt in `story_generator.py` for better instructions
3. For production, consider using OpenAI GPT-4 or Claude 3.5 Sonnet

### Out of memory errors

**Solutions:**

1. Use a smaller model (qwen3:4b uses only ~2GB RAM)
2. Close other applications
3. Reduce `max_tokens` in the generation config

## Performance Benchmarks

Typical generation times on different hardware:

| Hardware             | Model             | Time    | Quality   |
| -------------------- | ----------------- | ------- | --------- |
| M1 MacBook Air       | qwen3:4b          | 30-45s  | Good      |
| M2 MacBook Pro       | qwen2.5:7b        | 45-60s  | Very Good |
| M3 Max               | qwen2.5:14b       | 60-90s  | Excellent |
| Intel i7 (no GPU)    | qwen3:4b          | 90-120s | Good      |
| Cloud (OpenAI GPT-4) | gpt-4o            | 10-20s  | Excellent |
| Cloud (Claude 3.5)   | claude-3-5-sonnet | 15-25s  | Excellent |

## Best Practices

### For Development & Testing

- ✅ Use Ollama with `qwen3:4b` for **rapid iteration**
- ✅ Test story prompts and logic locally first
- ✅ **Save API costs** during development

### For Production

- ✅ Use **OpenAI GPT-4o** or **Claude 3.5 Sonnet** for best quality
- ✅ Cache generated stories to reduce API calls
- ✅ Monitor generation costs and set rate limits

### Hybrid Approach

- Development: Ollama (free, fast iteration)
- Staging: Smaller cloud model (e.g., GPT-4o-mini)
- Production: Premium cloud model (GPT-4o, Claude 3.5)

## Next Steps

1. **Test the basic flow**: Run `test_story_generation_ollama.py`
2. **Experiment with prompts**: Edit `story_generator.py` to improve story quality
3. **Try different models**: Test various Ollama models to find the best balance
4. **Integrate with frontend**: Connect frontend to call the story generation API
5. **Add caching**: Cache generated stories to speed up repeated requests
6. **Implement audio**: Add text-to-speech for story narration

## Resources

- **Ollama Documentation**: https://github.com/ollama/ollama
- **Available Models**: https://ollama.ai/library
- **Qwen Models**: https://ollama.ai/library/qwen (Best for Chinese)
- **Llama Models**: https://ollama.ai/library/llama3.1 (General purpose)

## Support

If you encounter issues:

1. Check Ollama logs: Terminal where `ollama serve` is running
2. Verify model installation: `ollama list`
3. Test model directly: `ollama run qwen3:4b "測試"`
4. Check the backend logs for detailed error messages

---

**Happy Story Generating! 🎉📚✨**
