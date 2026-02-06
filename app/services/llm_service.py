"""
LLM Service for AI-powered content generation
Supports multiple providers: OpenAI, Anthropic Claude, Ollama
"""
from typing import Optional, List, Dict, Any
import os
from enum import Enum
import httpx
from pydantic import BaseModel


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class LLMService:
    """
    Unified interface for LLM providers
    """
    
    def __init__(
        self, 
        provider: LLMProvider = LLMProvider.OLLAMA,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.api_key = api_key or self._get_default_api_key()
        self.model = model or self._get_default_model()
        self.base_url = base_url or self._get_default_base_url()
        
        if self.provider != LLMProvider.OLLAMA and not self.api_key:
            raise ValueError(f"API key required for {provider}. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
    
    def _get_default_base_url(self) -> str:
        """Get default base URL for the provider"""
        if self.provider == LLMProvider.OLLAMA:
            return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ""
    
    def _get_default_api_key(self) -> Optional[str]:
        if self.provider == LLMProvider.OPENAI:
            return os.getenv("OPENAI_API_KEY")
        elif self.provider == LLMProvider.ANTHROPIC:
            return os.getenv("ANTHROPIC_API_KEY")
        return None
    
    def _get_default_model(self) -> str:
        if self.provider == LLMProvider.OPENAI:
            return "gpt-4o"  # or "gpt-4o-mini" for cheaper
        elif self.provider == LLMProvider.ANTHROPIC:
            return "claude-3-5-sonnet-20241022"
        elif self.provider == LLMProvider.OLLAMA:
            # Default to qwen3:4b, check OLLAMA_MODEL env var
            return os.getenv("OLLAMA_MODEL", "qwen3:4b")
        return "gpt-4o"
    
    async def generate(
        self, 
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """
        Generate text from LLM
        
        Args:
            messages: List of conversation messages
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum response length
            
        Returns:
            Generated text content
        """
        if self.provider == LLMProvider.OPENAI:
            return await self._generate_openai(messages, temperature, max_tokens, **kwargs)
        elif self.provider == LLMProvider.ANTHROPIC:
            return await self._generate_anthropic(messages, temperature, max_tokens, **kwargs)
        elif self.provider == LLMProvider.OLLAMA:
            return await self._generate_ollama(messages, temperature, max_tokens, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    async def _generate_openai(
        self, 
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """Generate using OpenAI API"""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def _generate_anthropic(
        self, 
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """Generate using Anthropic Claude API"""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        # Extract system message if present
        system_message = None
        user_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                user_messages.append({"role": msg.role, "content": msg.content})
        
        payload = {
            "model": self.model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        if system_message:
            payload["system"] = system_message
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    
    async def _generate_ollama(
        self, 
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """Generate using Ollama (local models)"""
        
        print(f"[LLMService] Ollama request to: {self.base_url}")
        print(f"[LLMService] Model: {self.model}")
        print(f"[LLMService] Temperature: {temperature}, Max tokens: {max_tokens}")
        print(f"[LLMService] Number of messages: {len(messages)}")
        
        # Try using the /api/chat endpoint first (more modern, better for conversational models)
        chat_url = f"{self.base_url}/api/chat"
        
        # Format messages for chat API
        chat_messages = []
        for msg in messages:
            chat_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        chat_payload = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        try:
            print(f"[LLMService] Trying /api/chat endpoint...")
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(chat_url, json=chat_payload)
                print(f"[LLMService] Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"[LLMService] Response keys: {list(data.keys())}")
                    
                    # Chat API returns message in data["message"]["content"]
                    if "message" in data and "content" in data["message"]:
                        generated_text = data["message"]["content"]
                        
                        # Check if content is empty but there's a 'thinking' field (qwen3 models)
                        if (not generated_text or len(generated_text.strip()) == 0):
                            # Check in the message object
                            if "thinking" in data["message"]:
                                print(f"[LLMService] Chat content empty, using message.thinking field")
                                generated_text = data["message"]["thinking"]
                            # Or at the top level
                            elif "thinking" in data:
                                print(f"[LLMService] Chat content empty, using top-level thinking field")
                                generated_text = data["thinking"]
                        
                        print(f"[LLMService] Generated text length: {len(generated_text)} chars")
                        print(f"[LLMService] Generated text preview (first 200 chars): {generated_text[:200]}")
                        
                        if not generated_text or len(generated_text.strip()) == 0:
                            print(f"[LLMService] ERROR: Chat API returned empty content!")
                            raise ValueError("Empty response from chat API")
                        
                        return generated_text
                    else:
                        print(f"[LLMService] Chat API response missing expected format")
                        print(f"[LLMService] Full response: {data}")
                        raise ValueError(f"Unexpected chat API response format: {list(data.keys())}")
                        
        except Exception as chat_error:
            print(f"[LLMService] Chat API failed: {str(chat_error)}")
            print(f"[LLMService] Falling back to /api/generate endpoint...")
            
            # Fallback to generate endpoint
            prompt_parts = []
            for msg in messages:
                if msg.role == "system":
                    prompt_parts.append(f"System: {msg.content}")
                elif msg.role == "user":
                    prompt_parts.append(f"User: {msg.content}")
                elif msg.role == "assistant":
                    prompt_parts.append(f"Assistant: {msg.content}")
            
            prompt = "\n\n".join(prompt_parts) + "\n\nAssistant:"
            print(f"[LLMService] Prompt length: {len(prompt)} chars")
            
            generate_url = f"{self.base_url}/api/generate"
            
            generate_payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            }
            
            try:
                print(f"[LLMService] Sending request to /api/generate...")
                async with httpx.AsyncClient(timeout=180.0) as client:
                    response = await client.post(generate_url, json=generate_payload)
                    print(f"[LLMService] Response status: {response.status_code}")
                    response.raise_for_status()
                    
                    data = response.json()
                    print(f"[LLMService] Response keys: {list(data.keys())}")
                    
                    if "response" not in data:
                        print(f"[LLMService] ERROR: No 'response' key in Ollama response!")
                        print(f"[LLMService] Full response: {data}")
                        raise ValueError(f"Ollama returned invalid response format. Keys: {list(data.keys())}")
                    
                    generated_text = data["response"]
                    
                    # Check if response is empty but there's a 'thinking' field (qwen3 models)
                    if (not generated_text or len(generated_text.strip()) == 0) and "thinking" in data:
                        print(f"[LLMService] Response is empty but 'thinking' field exists")
                        print(f"[LLMService] Using 'thinking' field content instead")
                        generated_text = data["thinking"]
                    
                    print(f"[LLMService] Generated text length: {len(generated_text)} chars")
                    print(f"[LLMService] Generated text preview (first 200 chars): {generated_text[:200]}")
                    
                    if not generated_text or len(generated_text.strip()) == 0:
                        print(f"[LLMService] ERROR: Generate API returned empty response!")
                        print(f"[LLMService] Full data: {data}")
                        
                        # Check if model actually exists
                        print(f"[LLMService] Checking if model exists...")
                        try:
                            tags_response = await client.get(f"{self.base_url}/api/tags")
                            models = tags_response.json().get("models", [])
                            model_names = [m.get("name") for m in models]
                            print(f"[LLMService] Available models: {model_names}")
                            
                            if self.model not in model_names:
                                raise ValueError(
                                    f"Model '{self.model}' not found. Available models: {model_names}\n"
                                    f"Run: ollama pull {self.model}"
                                )
                        except Exception as check_error:
                            print(f"[LLMService] Could not check available models: {str(check_error)}")
                        
                        raise ValueError(
                            f"Ollama returned an empty response. This may happen if:\n"
                            f"1. The model is not properly loaded\n"
                            f"2. The prompt is too long\n"
                            f"3. The model needs more time (current timeout: 180s)\n"
                            f"Try: ollama pull {self.model}"
                        )
                    
                    return generated_text
                    
            except httpx.ConnectError as e:
                print(f"[LLMService] Connection error: {str(e)}")
                raise ValueError(
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Make sure Ollama is running (ollama serve) and the model is pulled "
                    f"(ollama pull {self.model})"
                )
            except httpx.TimeoutException as e:
                print(f"[LLMService] Timeout error: {str(e)}")
                raise ValueError(
                    f"Ollama request timed out after 180 seconds. "
                    f"The model '{self.model}' may be too large or slow. "
                    f"Try using a smaller model like 'qwen3:1.7b' or increase the timeout."
                )
            except httpx.HTTPStatusError as e:
                print(f"[LLMService] HTTP status error: {e.response.status_code}")
                print(f"[LLMService] Response text: {e.response.text}")
                raise ValueError(f"Ollama HTTP error {e.response.status_code}: {e.response.text}")
            except Exception as e:
                print(f"[LLMService] Unexpected error: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise ValueError(f"Ollama error: {str(e)}")


# Singleton instances
_openai_service: Optional[LLMService] = None
_anthropic_service: Optional[LLMService] = None
_ollama_service: Optional[LLMService] = None


def get_llm_service(provider: LLMProvider = LLMProvider.OLLAMA) -> LLMService:
    """
    Get or create LLM service instance (singleton pattern)
    """
    global _openai_service, _anthropic_service, _ollama_service
    
    if provider == LLMProvider.OPENAI:
        if _openai_service is None:
            _openai_service = LLMService(provider=LLMProvider.OPENAI)
        return _openai_service
    elif provider == LLMProvider.ANTHROPIC:
        if _anthropic_service is None:
            _anthropic_service = LLMService(provider=LLMProvider.ANTHROPIC)
        return _anthropic_service
    elif provider == LLMProvider.OLLAMA:
        if _ollama_service is None:
            _ollama_service = LLMService(provider=LLMProvider.OLLAMA)
        return _ollama_service
    else:
        raise ValueError(f"Unsupported provider: {provider}")
