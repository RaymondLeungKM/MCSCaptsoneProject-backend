"""
Word Enhancement Service
Automatically generate bilingual content (Cantonese + English) for words using AI
"""
from typing import Optional, Dict, Any
import json
from pydantic import BaseModel

from app.services.llm_service import get_llm_service, LLMMessage, LLMProvider


class EnhancedWordContent(BaseModel):
    """Enhanced word content with bilingual support"""
    word_english: str
    word_cantonese: str
    jyutping: str
    definition_english: str
    definition_cantonese: str
    example_english: str
    example_cantonese: str
    difficulty: str = "easy"


class WordEnhancementService:
    """
    Generate complete bilingual word content using AI
    Used for words learned from external sources (object detection, etc.)
    """
    
    def __init__(self, provider: LLMProvider = LLMProvider.OLLAMA):
        self.llm = get_llm_service(provider)
    
    def _build_enhancement_prompt(
        self,
        word: str,
        source: str,
        image_url: Optional[str] = None
    ) -> list[LLMMessage]:
        """Build prompt for word enhancement"""
        
        system_prompt = """你是一位專業的香港幼兒教育專家和雙語詞彙專家。
你的任務是為3-5歲幼兒創建適合他們年齡的詞彙資料，包括粵語和英語兩種語言。

**重要要求：**
1. 定義必須簡單易懂，適合3-5歲幼兒
2. 粵語拼音 (Jyutping) 必須100%正確
3. 例句要貼近香港幼兒的日常生活
4. 例句長度：6-10個字
5. 詞彙難度評估：easy (基本日常詞), medium (需要學習), hard (抽象概念)

**標準粵語拼音參考：**
我=ngo5 你=nei5 佢=keoi5 係=hai6 喺=hai2 見=gin3 到=dou2/dou3
媽=maa1/maa4 爸=baa1/baa4 哥=go1/go4 姐=ze1/ze2 細=sai3
食=sik6 飲=jam2 玩=waan2 睇=tai2 有=jau5 冇=mou5

You are a professional Hong Kong early childhood educator and bilingual vocabulary expert.
Create age-appropriate vocabulary content for 3-5 year old children in both Cantonese and English.

**Requirements:**
1. Definitions must be simple and suitable for preschoolers
2. Cantonese Jyutping must be 100% accurate
3. Example sentences should reflect Hong Kong children's daily life
4. Sentence length: 6-10 characters
5. Difficulty: easy (daily basics), medium (learning required), hard (abstract concepts)"""
        
        context_info = f"這個詞語是透過{source}學習的" if source != "object_detection" else "這個詞語是透過物件識別學習的"
        
        user_prompt = f"""請為以下詞語創建完整的雙語學習資料：

**詞語：** {word}
**來源：** {context_info}

請按照以下JSON格式輸出：

{{
  "word_english": "{word}",
  "word_cantonese": "粵語詞語（繁體中文）",
  "jyutping": "完整正確的粵語拼音",
  "definition_english": "Simple English definition for preschoolers (10-15 words)",
  "definition_cantonese": "簡單的粵語定義，適合幼兒（10-15字）",
  "example_english": "A simple example sentence (8-12 words)",
  "example_cantonese": "一個簡單的粵語例句（6-10字）",
  "difficulty": "easy|medium|hard"
}}

**範例輸出：**
{{
  "word_english": "Cat",
  "word_cantonese": "貓",
  "jyutping": "maau1",
  "definition_english": "A small furry animal that says meow and likes to play",
  "definition_cantonese": "一種會叫喵喵嘅小動物，好鍾意玩",
  "example_english": "I saw a cat in the park",
  "example_cantonese": "我喺公園見到一隻貓",
  "difficulty": "easy"
}}

**重要提醒：**
- 確保粵語拼音正確（每個字一個音節）
- 定義和例句要簡單易懂
- 例句要符合香港幼兒的生活經驗

請直接輸出JSON，不要有其他文字："""
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    async def enhance_word(
        self,
        word: str,
        source: str = "object_detection",
        image_url: Optional[str] = None,
        max_retries: int = 3
    ) -> EnhancedWordContent:
        """
        Generate complete bilingual content for a word
        
        Args:
            word: The word to enhance (e.g., "Cat", "Dog")
            source: Learning source (e.g., "object_detection", "physical_activity")
            image_url: Optional image URL for context
            max_retries: Number of retries if generation fails (default 3)
        
        Returns:
            EnhancedWordContent with all bilingual fields populated
        """
        print(f"[WordEnhancement] Generating content for word: {word}")
        
        # Build prompt
        messages = self._build_enhancement_prompt(word, source, image_url)
        
        last_error = None
        
        # Try up to max_retries times
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"[WordEnhancement] Retry attempt {attempt + 1}/{max_retries}")
            
            try:
                # Call LLM
                response = await self.llm.generate(
                    messages=messages,
                    temperature=0.3,  # Lower temperature for more consistent JSON output
                    max_tokens=1000
                )
                
                print(f"[WordEnhancement] Raw LLM response length: {len(response)}")
                print(f"[WordEnhancement] First 300 chars: {response[:300]}")
                
                # Parse JSON response - try multiple extraction methods
                response_text = response.strip()
                
                # Method 1: Extract JSON from markdown code blocks
                if "```json" in response_text:
                    start = response_text.find("```json") + 7
                    end = response_text.find("```", start)
                    if end != -1:
                        response_text = response_text[start:end].strip()
                elif "```" in response_text:
                    start = response_text.find("```") + 3
                    end = response_text.find("```", start)
                    if end != -1:
                        response_text = response_text[start:end].strip()
                
                # Method 2: Find JSON object boundaries
                if not response_text.startswith("{"):
                    start_idx = response_text.find("{")
                    if start_idx != -1:
                        response_text = response_text[start_idx:]
                
                if not response_text.endswith("}"):
                    end_idx = response_text.rfind("}")
                    if end_idx != -1:
                        response_text = response_text[:end_idx + 1]
                
                response_text = response_text.strip()
                
                print(f"[WordEnhancement] Extracted JSON: {response_text[:200]}...")
                
                # Parse JSON
                data = json.loads(response_text)
                
                # Validate required fields
                required_fields = ["word_english", "word_cantonese", "jyutping", 
                                 "definition_english", "definition_cantonese",
                                 "example_english", "example_cantonese"]
                missing_fields = [f for f in required_fields if f not in data or not data[f]]
                
                if missing_fields:
                    print(f"[WordEnhancement] WARNING: Missing fields: {missing_fields}")
                    raise ValueError(f"Missing required fields: {missing_fields}")
                
                # Create result
                result = EnhancedWordContent(**data)
                
                print(f"[WordEnhancement] ✓ Successfully generated content for: {word}")
                print(f"  - Cantonese: {result.word_cantonese} ({result.jyutping})")
                print(f"  - Definition (EN): {result.definition_english[:50]}...")
                print(f"  - Definition (粵): {result.definition_cantonese[:30]}...")
                
                return result
                
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                print(f"[WordEnhancement] ❌ Attempt {attempt + 1} - Failed to parse JSON: {e}")
                if attempt == 0:  # Only print full details on first attempt
                    print(f"[WordEnhancement] Full response was:\n{response[:500]}")
                    print(f"[WordEnhancement] Extracted text was:\n{response_text[:500]}")
                continue  # Retry
                
            except ValueError as e:
                last_error = f"Validation error: {e}"
                print(f"[WordEnhancement] ❌ Attempt {attempt + 1} - Validation failed: {e}")
                if attempt == 0 and 'data' in locals():
                    print(f"[WordEnhancement] Data received: {data}")
                continue  # Retry
                
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                print(f"[WordEnhancement] ❌ Attempt {attempt + 1} - ERROR: {str(e)}")
                if attempt == 0:
                    import traceback
                    traceback.print_exc()
                continue  # Retry
        
        # All retries failed - use fallback
        print(f"[WordEnhancement] ❌ All {max_retries} attempts failed for word: {word}")
        print(f"[WordEnhancement] Last error: {last_error}")
        print(f"[WordEnhancement] Using fallback content")
        return self._create_fallback_content(word)
    
    def _create_fallback_content(self, word: str) -> EnhancedWordContent:
        """Create basic fallback content if AI generation fails"""
        print(f"[WordEnhancement] Using fallback content for: {word}")
        return EnhancedWordContent(
            word_english=word,
            word_cantonese=word,  # Use English as fallback
            jyutping="",
            definition_english=f"A word learned through observation",
            definition_cantonese=f"透過觀察學習的詞語",
            example_english=f"I learned about {word.lower()}",
            example_cantonese=f"我學習了{word}",
            difficulty="easy"
        )


# Global instance
_enhancement_service: Optional[WordEnhancementService] = None


def get_word_enhancement_service(
    provider: LLMProvider = LLMProvider.OLLAMA
) -> WordEnhancementService:
    """Get or create the word enhancement service singleton"""
    global _enhancement_service
    if _enhancement_service is None:
        _enhancement_service = WordEnhancementService(provider)
    return _enhancement_service
