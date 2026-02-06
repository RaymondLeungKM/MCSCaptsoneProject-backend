# Ollama Setup Guide for Local LLM Testing

## What is Ollama?

Ollama allows you to run large language models locally on your machine, perfect for:

- Testing without API costs
- Privacy (no data sent to external services)
- Offline development
- Faster iteration

## Installation

### macOS

```bash
brew install ollama
```

Or download from: https://ollama.com/download/mac

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Windows

Download from: https://ollama.com/download/windows

## Starting Ollama

```bash
ollama serve
```

This starts the Ollama server on `http://localhost:11434`

## Recommended Models for Cantonese

### 1. Qwen2.5 (BEST for Chinese/Cantonese)

```bash
ollama pull qwen2.5
```

- Excellent Chinese language understanding
- Great for Traditional Chinese
- 7B parameters, fast inference
- Set as default: `export OLLAMA_MODEL=qwen2.5`

### 2. Llama 3.2 (Latest, Good General Purpose)

```bash
ollama pull llama3.2
```

- Latest Llama model
- Good multilingual support
- 3B parameters, very fast

### 3. Llama 3.1 (Solid Multilingual)

```bash
ollama pull llama3.1
```

- Proven multilingual capabilities
- Good balance of quality and speed
- 8B parameters

## Environment Configuration

Add to your `.env` file or export in terminal:

```bash
# Use Ollama by default (no API key needed)
OLLAMA_BASE_URL=http://localhost:11434

# Choose your model (recommended: qwen2.5 for Cantonese)
OLLAMA_MODEL=qwen2.5

# Optional: If you want to use cloud APIs instead
# OPENAI_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here
```

## Testing Sentence Generation

```bash
# Make sure Ollama is running in one terminal
ollama serve

# In another terminal, run the test
cd /path/to/preschool-vocabulary-platform-backend
python test_sentence_generation.py
```

## Model Comparison

| Model       | Size | Speed     | Chinese Quality | Use Case               |
| ----------- | ---- | --------- | --------------- | ---------------------- |
| **qwen2.5** | 7B   | Fast      | ⭐⭐⭐⭐⭐      | **BEST for Cantonese** |
| llama3.2    | 3B   | Very Fast | ⭐⭐⭐          | Quick testing          |
| llama3.1    | 8B   | Medium    | ⭐⭐⭐⭐        | Good alternative       |

## Switching Between Providers

The application defaults to Ollama but supports all three:

```python
# In your code
from app.services.llm_service import LLMProvider, get_llm_service

# Use Ollama (default)
llm = get_llm_service(LLMProvider.OLLAMA)

# Use OpenAI
llm = get_llm_service(LLMProvider.OPENAI)

# Use Anthropic
llm = get_llm_service(LLMProvider.ANTHROPIC)
```

## API Endpoint Configuration

The sentence generation endpoint will automatically use Ollama:

```bash
POST /api/v1/vocabulary/{word_id}/generate-sentences
```

No changes needed - it works with whatever provider is configured!

## Troubleshooting

### Connection Error

```
Cannot connect to Ollama at http://localhost:11434
```

**Solution:** Make sure Ollama is running: `ollama serve`

### Model Not Found

```
Model 'qwen2.5' not found
```

**Solution:** Pull the model: `ollama pull qwen2.5`

### Slow Generation

**Solution:**

- Use a smaller model (llama3.2 instead of llama3.1)
- Check CPU/RAM usage
- Close other applications

### Poor Cantonese Quality

**Solution:** Use qwen2.5 - it's specifically trained for Chinese languages

## Performance Tips

1. **First Generation is Slow**: Models load into memory on first use
2. **Subsequent Calls Are Fast**: Model stays in memory
3. **RAM Usage**: 7B models need ~8GB RAM
4. **GPU Acceleration**: Ollama automatically uses GPU if available

## Advanced Configuration

### Custom Ollama Port

```bash
export OLLAMA_BASE_URL=http://localhost:8080
ollama serve --port 8080
```

### Multiple Models

```bash
# Pull multiple models
ollama pull qwen2.5
ollama pull llama3.2

# Switch between them
export OLLAMA_MODEL=qwen2.5  # For Cantonese work
export OLLAMA_MODEL=llama3.2 # For quick testing
```

## Cloud APIs (Optional)

If you prefer cloud APIs for production:

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The test script will prompt you to choose when both are available.
