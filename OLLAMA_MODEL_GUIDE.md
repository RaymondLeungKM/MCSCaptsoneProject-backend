# How to Change Ollama Models

The system is configured to make changing Ollama models easy through environment variables. No code changes needed!

## Quick Change Guide

### 1. Choose Your Model

Available models (ordered by size):

- **qwen2.5:1.5b** ⚡ (Recommended for testing, ~1GB, excellent Cantonese)
- **qwen3:4b** (Good quality, ~2.6GB, excellent Cantonese)
- **qwen2.5:7b** (High quality, ~4.7GB, excellent Cantonese)
- **qwen2.5:14b** (Production quality, ~9GB, excellent Cantonese)
- **llama3.1:8b** (Alternative, ~4.7GB, decent but weaker Chinese)

> 💡 **Tip**: The qwen2.5 models are specifically optimized for Chinese/Cantonese content!

### 2. Update Configuration

Edit your `.env` file and change the `OLLAMA_MODEL` line:

```bash
# Change this line to your chosen model
OLLAMA_MODEL=qwen2.5:1.5b
```

### 3. Pull the Model

Before using a new model, you need to download it:

```bash
ollama pull qwen2.5:1.5b
```

### 4. Restart Backend

Restart your FastAPI backend server for the changes to take effect:

```bash
# If running with uvicorn
pkill -f uvicorn && uvicorn main:app --reload
```

## Configuration Files

The Ollama model configuration is managed in three places:

1. **`.env`** - Your active configuration (change this to switch models)

   ```bash
   OLLAMA_MODEL=qwen2.5:1.5b
   ```

2. **`app/core/config.py`** - Default configuration (fallback if .env not set)

   ```python
   OLLAMA_MODEL: str = "qwen2.5:1.5b"
   ```

3. **`app/services/llm_service.py`** - Service layer (automatically reads from env)
   ```python
   return os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
   ```

## Verify Current Model

To check which model is currently in use:

```bash
# Check your .env file
grep OLLAMA_MODEL .env

# Check available models
ollama list

# Test the connection (optional)
python test_sentence_generation.py
```

## Troubleshooting

### Model Not Found Error

If you get a "model not found" error:

1. Make sure you pulled the model: `ollama pull qwen2.5:1.5b`
2. Check Ollama is running: `ps aux | grep ollama`
3. Verify the model name in .env matches exactly

### Changing Provider (OpenAI/Anthropic)

To switch to a commercial provider instead of Ollama:

1. Update `.env`:

   ```bash
   LLM_PROVIDER=openai  # or "anthropic"
   OPENAI_API_KEY=sk-your-key-here
   ```

2. Restart backend

## Model Comparison

| Model        | Size  | Speed  | Quality    | Cantonese    | Best For                   |
| ------------ | ----- | ------ | ---------- | ------------ | -------------------------- |
| qwen2.5:1.5b | 1GB   | ⚡⚡⚡ | ⭐⭐       | ✅ Excellent | Quick testing, development |
| qwen3:4b     | 2.6GB | ⚡⚡   | ⭐⭐⭐     | ✅ Excellent | Balanced testing           |
| qwen2.5:7b   | 4.7GB | ⚡     | ⭐⭐⭐⭐   | ✅ Excellent | Quality > Speed            |
| qwen2.5:14b  | 9GB   | 🐌     | ⭐⭐⭐⭐⭐ | ✅ Excellent | Production-like            |

## Example: Switching from qwen3:4b to qwen2.5:1.5b

```bash
# 1. Pull the new model
ollama pull qwen2.5:1.5b

# 2. Edit .env file (change OLLAMA_MODEL line)
nano .env
# Change: OLLAMA_MODEL=qwen2.5:1.5b

# 3. Restart backend
# (Ctrl+C in terminal running uvicorn, then restart)
uvicorn main:app --reload

# 4. Test it
python test_sentence_generation.py
```

That's it! No code changes required. 🎉
