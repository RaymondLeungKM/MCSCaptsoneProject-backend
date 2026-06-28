"""
Application configuration
"""
from typing import List, Dict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "Preschool Vocabulary Platform"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://your-frontend-domain.com"
    ]
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/preschool_vocab"
    ASYNC_DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/preschool_vocab"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Optional MongoDB (camera capture store + pre-generated images)
    MONGODB_ENABLED: bool = False
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "preschool_vocab"
    MONGODB_CAMERA_COLLECTION: str = "camera_captures"
    MONGODB_IMAGES_COLLECTION: str = "word_images"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # AI/LLM Configuration
    # LLM_PROVIDER: "openai", "openrouter", "anthropic", or "ollama"
    LLM_PROVIDER: str = "openrouter"  # Default to OpenRouter for hosted generation
    
    # OpenAI
    OPENAI_API_KEY: str = ""

    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_EMBEDDING_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"

    # External bedtime story program adapter
    EXTERNAL_STORY_PROGRAM_DIR: str = "../story-generation-program"
    EXTERNAL_STORY_PYTHON_BIN: str = "python3"
    #EXTERNAL_STORY_TIMEOUT_SECONDS: int = 300
    EXTERNAL_STORY_TIMEOUT_SECONDS: int = 1200 #vvn:20260618
    # Directory where the external story program writes its outputs (audio, logs)
    # By default this is a sibling folder next to the program dir
    EXTERNAL_STORY_OUTPUT_DIR: str = "../story-generation-output"
    
    # Anthropic Claude
    ANTHROPIC_API_KEY: str = ""
    
    # Ollama (for local testing)
    # To change model: Update OLLAMA_MODEL in .env file and run: ollama pull <model-name>
    # Recommended: qwen2.5:1.5b (fast, excellent Cantonese)
    # Alternatives: qwen3:4b, qwen2.5:7b, qwen2.5:14b
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:1.5b"  # Default model for Cantonese content

    # Hugging Face (image generation via FLUX.1)
    HF_API_TOKEN: str = ""
    HF_IMAGE_MODEL: str = "stabilityai/stable-diffusion-xl-base-1.0"

    # Silicon Flow (image generation via Kolors)
    SILICONFLOW_API_KEY: str = ""

    # Cloudflare Workers AI (transcription, image generation)
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CF_ACCOUNT_ID: str = ""
    CLOUDFLARE_AI_API_TOKEN: str = ""

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "preschool-vocab-media"
    AWS_REGION: str = "us-east-1"

    # Story audio defaults (temporary sample settings)
    STORY_AUDIO_VOICE_SETTINGS: List[Dict[str, str]] = [
        {"audio_generate_provider": "aws", "audio_generate_voice_name": "Hiujin"},
        {"audio_generate_provider": "google", "audio_generate_voice_name": "yue-HK-Standard-A"},
        {"audio_generate_provider": "azure", "audio_generate_voice_name": "zh-HK-HiuGaaiNeural"},
        {"audio_generate_provider": "aws", "audio_generate_voice_name": "Hiujin"},
        {"audio_generate_provider": "aws", "audio_generate_voice_name": "Hiujin"},
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
