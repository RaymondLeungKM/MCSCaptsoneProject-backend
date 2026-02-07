"""
AI-powered bedtime story generation service
"""
import os
import time
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.daily_words import DailyWordTracking, GeneratedStory
from app.models.vocabulary import Word
from app.models.user import Child
from app.schemas.stories import DailyWordSummary, StoryGenerationRequest
from app.core.config import settings
from app.services.llm_service import LLMService, LLMProvider, LLMMessage


class StoryGeneratorService:
    """Service for generating AI-powered bedtime stories"""
    
    def __init__(self, provider: Optional[LLMProvider] = None):
        # Determine which LLM provider to use
        # Priority: config setting > environment variable > Ollama (for local testing)
        if provider:
            self.provider = provider
        elif hasattr(settings, 'LLM_PROVIDER') and settings.LLM_PROVIDER:
            self.provider = LLMProvider(settings.LLM_PROVIDER)
        elif os.getenv("ANTHROPIC_API_KEY"):
            self.provider = LLMProvider.ANTHROPIC
        elif os.getenv("OPENAI_API_KEY"):
            self.provider = LLMProvider.OPENAI
        else:
            # Default to Ollama for local testing
            self.provider = LLMProvider.OLLAMA
            print("[StoryGenerator] Using Ollama for local story generation")
        
        try:
            self.llm_service = LLMService(provider=self.provider)
            print(f"[StoryGenerator] Initialized with provider: {self.provider}")
        except Exception as e:
            print(f"[StoryGenerator] Warning: Could not initialize LLM service: {e}")
            self.llm_service = None
    
    async def get_daily_words(
        self,
        db: AsyncSession,
        child_id: str,
        target_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[DailyWordSummary]:
        """Get words learned today for story generation"""
        if target_date is None:
            target_date = datetime.now()
        
        # Get start and end of day
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Query daily word tracking
        query = (
            select(DailyWordTracking, Word)
            .join(Word, DailyWordTracking.word_id == Word.id)
            .where(
                and_(
                    DailyWordTracking.child_id == child_id,
                    DailyWordTracking.date >= start_of_day,
                    DailyWordTracking.date <= end_of_day,
                    DailyWordTracking.include_in_story == True
                )
            )
            .order_by(DailyWordTracking.story_priority.desc(), DailyWordTracking.exposure_count.desc())
            .limit(limit)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Convert to DailyWordSummary
        summaries = []
        for tracking, word in rows:
            summaries.append(DailyWordSummary(
                word_id=word.id,
                word=word.word,
                word_cantonese=word.word_cantonese or word.word,
                jyutping=word.jyutping or "",
                definition_cantonese=word.definition_cantonese or word.definition or "",
                example_cantonese=word.example_cantonese or word.example or "",
                category=word.category,
                exposure_count=tracking.exposure_count,
                used_actively=tracking.used_actively,
                mastery_confidence=tracking.mastery_confidence,
                story_priority=tracking.story_priority
            ))
        
        return summaries

    def _build_story_ssml(self, text: str) -> str:
        """Create simple SSML from story text"""
        if not text:
            return "<speak></speak>"
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return f"<speak>{text}</speak>"
        ssml_paragraphs = "".join([f"<p>{p}</p>" for p in paragraphs])
        return f"<speak>{ssml_paragraphs}</speak>"
    
    def _parse_story_json(self, ai_response: str) -> dict:
        """Parse JSON response from AI with error handling and auto-fixes"""
        import json
        import re
        
        # Log the full response for debugging
        print(f"[StoryGenerator] AI Response Length: {len(ai_response)}")
        print(f"[StoryGenerator] AI Response Preview (first 1000 chars):")
        print(ai_response[:1000])
        print(f"[StoryGenerator] AI Response End (last 500 chars):")
        print(ai_response[-500:])
        
        # Extract JSON from markdown code blocks if present
        original_response = ai_response
        if "```json" in ai_response:
            ai_response = ai_response.split("```json")[1].split("```")[0].strip()
        elif "```" in ai_response:
            # Try to get the first code block
            parts = ai_response.split("```")
            if len(parts) >= 3:
                ai_response = parts[1].strip()
                # Remove language identifier if present
                if ai_response.startswith(('json', 'JSON')):
                    ai_response = ai_response[4:].strip()
        
        # Try to parse JSON directly first
        try:
            parsed = json.loads(ai_response)
            print(f"[StoryGenerator] Successfully parsed JSON on first attempt")
            return parsed
        except json.JSONDecodeError as e:
            print(f"[StoryGenerator] Initial JSON parse failed: {str(e)}")
            print(f"[StoryGenerator] Error position: line {e.lineno}, column {e.colno}")
            print(f"[StoryGenerator] Attempting to fix common JSON issues...")
            
            # Try common fixes
            fixed_response = ai_response
            
            # Fix 1: Remove trailing commas before } or ]
            fixed_response = re.sub(r',\s*([}\]])', r'\1', fixed_response)
            
            # Fix 2: Remove any trailing commas at the end
            fixed_response = fixed_response.rstrip().rstrip(',')
            
            # Fix 3: Try to find and extract just the JSON object
            json_match = re.search(r'\{.*\}', fixed_response, re.DOTALL)
            if json_match:
                fixed_response = json_match.group(0)
            
            try:
                parsed = json.loads(fixed_response)
                print(f"[StoryGenerator] Successfully parsed JSON after fixes")
                return parsed
            except json.JSONDecodeError as e2:
                print(f"[StoryGenerator] JSON parse still failed after fixes")
                print(f"[StoryGenerator] Error: {str(e2)}")
                print(f"[StoryGenerator] Error position: line {e2.lineno}, column {e2.colno}")
                
                # Last resort: try to extract just the essential fields using multiple patterns
                print(f"[StoryGenerator] Attempting regex extraction as last resort...")
                
                try:
                    # Try to extract title
                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', ai_response)
                    if not title_match:
                        title_match = re.search(r"'title'\s*:\s*'([^']+)'", ai_response)
                    
                    # Try multiple patterns for content
                    content_match = None
                    
                    # Pattern 1: Match until next JSON field
                    content_match = re.search(
                        r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]',
                        ai_response,
                        re.DOTALL
                    )
                    
                    if not content_match:
                        # Pattern 2: Match with escaped quotes
                        content_match = re.search(
                            r'"content"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
                            ai_response,
                            re.DOTALL
                        )
                    
                    if not content_match:
                        # Pattern 3: More aggressive - match everything between "content": " and next "
                        content_match = re.search(
                            r'"content"\s*:\s*"(.*?)"(?:\s*[,}])',
                            ai_response,
                            re.DOTALL
                        )
                    
                    # Try to extract word_usage as well
                    word_usage = {}
                    word_usage_match = re.search(
                        r'"word_usage"\s*:\s*\{([^}]*)\}',
                        ai_response,
                        re.DOTALL
                    )
                    if word_usage_match:
                        word_usage_str = word_usage_match.group(1)
                        # Parse word usage entries
                        for entry in re.finditer(r'"([^"]+)"\s*:\s*"([^"]*)"', word_usage_str):
                            word_usage[entry.group(1)] = entry.group(2)
                    
                    if title_match and content_match:
                        print(f"[StoryGenerator] Successfully extracted essential fields using regex")
                        extracted_content = content_match.group(1)
                        # Basic unescape
                        extracted_content = extracted_content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                        
                        result = {
                            "title": title_match.group(1),
                            "title_english": "Story",
                            "content": extracted_content,
                            "word_usage": word_usage
                        }
                        print(f"[StoryGenerator] Extracted: title={result['title'][:30]}..., content_length={len(result['content'])}, word_usage_count={len(word_usage)}")
                        return result
                    else:
                        print(f"[StoryGenerator] Regex extraction failed - title_match={title_match is not None}, content_match={content_match is not None}")
                        
                except Exception as regex_error:
                    print(f"[StoryGenerator] Regex extraction exception: {str(regex_error)}")
                    import traceback
                    traceback.print_exc()
                
                # Re-raise the original error with more context
                print(f"[StoryGenerator] All parsing attempts failed. Full response:")
                print(ai_response)
                raise ValueError(
                    f"Failed to parse AI response as JSON. Error: {str(e2)}. "
                    f"Please check the backend logs for the full response."
                )
    
    def _clean_story_content(self, content: Optional[str]) -> str:
        """Clean story content by removing JSON artifacts and fixing escape sequences"""
        if not content:
            return ""
        
        import re
        
        # Remove any JSON structure that leaked into content
        # Look for patterns like: \n\nword_usage": { or },\n"moral":
        content = re.sub(r'\\n\\n\s*["\']?\w+["\']?\s*:\s*\{.*$', '', content, flags=re.DOTALL)
        content = re.sub(r'\}\s*,\s*["\']?\w+["\']?\s*:.*$', '', content, flags=re.DOTALL)
        
        # Fix escaped newlines and quotes
        content = content.replace('\\n', '\n')
        content = content.replace('\\"', '"')
        content = content.replace("\\'", "'")
        
        # Remove any trailing JSON fragments
        content = re.sub(r'\s*[,\}\]]+\s*$', '', content)
        
        # Clean up multiple consecutive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Strip whitespace
        content = content.strip()
        
        return content
    
    def _create_story_prompt(
        self,
        child_name: str,
        child_age: int,
        words: List[DailyWordSummary],
        theme: Optional[str] = None,
        word_count_target: int = 400
    ) -> str:
        """Create prompt for AI story generation"""
        
        # Build word list for the prompt
        word_list = []
        for w in words:
            word_list.append(f"- {w.word_cantonese} ({w.jyutping}): {w.definition_cantonese}")
        
        words_text = "\n".join(word_list)
        
        theme_instruction = ""
        if theme:
            theme_map = {
                "adventure": "冒險故事，充滿探索和驚喜",
                "family": "家庭故事，溫馨有愛",
                "animals": "動物故事，可愛有趣",
                "nature": "大自然故事，探索戶外",
                "friendship": "友誼故事，關於朋友",
                "bedtime": "睡前故事，平靜舒適"
            }
            theme_instruction = f"\n主題: {theme_map.get(theme, theme)}"
        
        prompt = f"""請用繁體中文（Traditional Chinese）為香港學前兒童創作一個溫馨的睡前故事。

**要求：**
1. 故事長度：約{word_count_target}字
2. 主角名字：{child_name}（{child_age}歲）{theme_instruction}
3. 必須自然地使用以下所有詞彙（今天學到的詞語）：

{words_text}

4. 語言風格：
   - 使用簡單、適合3-5歲幼兒的句子
   - 重複關鍵詞語幫助記憶
   - 正面、鼓勵性的語氣
   - 溫馨、適合睡前閱讀的氛圍

5. 文化元素：
   - 融入香港本地元素（如：公園、茶餐廳、巴士、海洋公園等）
   - 貼近香港家庭生活

6. 故事結構：
   - 開頭：介紹主角和情境
   - 發展：簡單的情節，融入所學詞彙
   - 結尾：溫馨、正面的結局，適合入睡

**輸出格式：**
請直接輸出JSON，不要先解釋或思考過程。立即開始輸出JSON格式的故事（不要有多餘的文字說明），包含以下字段：
```json
{{
  "title": "故事標題（繁體中文）",
  "title_english": "Story Title (English)",
  "content": "完整故事內容（繁體中文，使用\\n表示段落分隔）",
  "word_usage": {{
    "詞彙1": "在故事中如何使用（簡短說明）",
    "詞彙2": "在故事中如何使用（簡短說明）"
  }},
  "moral": "故事寓意（可選）"
}}
```

**重要提醒：**
1. 確保輸出的JSON格式正確，沒有語法錯誤
2. 字符串中的引號要正確轉義
3. 不要在最後一個字段後面加逗號
4. 確保所有括號完整配對
"""
        
        return prompt
    
    async def generate_story(
        self,
        db: AsyncSession,
        request: StoryGenerationRequest
    ) -> tuple[Optional[GeneratedStory], List[DailyWordSummary], float]:
        """Generate a bedtime story using AI"""
        
        if not self.llm_service:
            raise ValueError("LLM service not initialized. Please configure an API key or run Ollama locally.")
        
        start_time = time.time()
        
        # Get child information
        child_query = select(Child).where(Child.id == request.child_id)
        child_result = await db.execute(child_query)
        child = child_result.scalar_one_or_none()
        
        if not child:
            raise ValueError(f"Child not found: {request.child_id}")
        
        # Get daily words
        words = await self.get_daily_words(
            db, 
            request.child_id,
            request.date,
            limit=10
        )
        
        if len(words) == 0:
            raise ValueError("No words learned today to include in story")
        
        # Create prompt
        prompt = self._create_story_prompt(
            child_name=child.name,
            child_age=child.age,
            words=words,
            theme=request.theme,
            word_count_target=request.word_count_target
        )
        
        # Call AI API using unified LLM service
        try:
            if not self.llm_service:
                raise ValueError("LLM service not initialized. Please configure an API key or run Ollama locally.")
            
            # Create messages for the LLM
            messages = [
                LLMMessage(role="user", content=prompt)
            ]
            
            # Generate story using LLM service
            # Note: qwen3:4b uses Chain-of-Thought and needs more tokens for thinking + output
            ai_response = await self.llm_service.generate(
                messages=messages,
                temperature=0.8,
                max_tokens=5000
            )
            
            # Parse JSON response with robust error handling
            story_data = self._parse_story_json(ai_response)

            story_id = str(uuid.uuid4())
            
            # Extract and clean story content
            # Ensure we always get a string, not None (use 'or' to handle None values)
            story_text_raw = story_data.get("content") or ""
            
            if not story_text_raw:
                print(f"[StoryGenerator] ERROR: AI did not return any content!")
                print(f"[StoryGenerator] Full response keys: {list(story_data.keys())}")
                raise ValueError("AI response did not contain story content. Please try again.")
            
            print(f"[StoryGenerator] Raw content length: {len(story_text_raw)}")
            print(f"[StoryGenerator] Raw content preview (first 200 chars): {story_text_raw[:200]}")
            
            story_text = self._clean_story_content(story_text_raw)
            print(f"[StoryGenerator] Cleaned content length: {len(story_text)}")
            print(f"[StoryGenerator] Cleaned content preview (first 200 chars): {story_text[:200]}")
            
            # If cleaning removed too much, use raw (but still fix escape sequences)
            if len(story_text) < 50 and len(story_text_raw) > 50:
                print(f"[StoryGenerator] Warning: Cleaning removed too much content, using raw with basic fixes")
                story_text = story_text_raw.replace('\\n', '\n').replace('\\"', '"')
            
            vocab_terms = [w.word_cantonese or w.word for w in words]
            vocab_used = ", ".join(vocab_terms)
            if len(vocab_used) > 500:
                vocab_used = vocab_used[:497] + "..."

            # Filter and ensure word_usage only contains words that were actually learned
            # Create a set of valid word keys from the words list
            valid_word_keys = {(w.word_cantonese or w.word) for w in words}
            
            # Get AI's word_usage and filter to only include valid words
            ai_word_usage = story_data.get("word_usage") or {}
            if not isinstance(ai_word_usage, dict):
                print(f"[StoryGenerator] Warning: word_usage is not a dict, got {type(ai_word_usage)}")
                ai_word_usage = {}
            
            word_usage_dict = {}
            
            # First, add words from AI's response that match our learned words
            for word_key, usage in ai_word_usage.items():
                if word_key in valid_word_keys:
                    word_usage_dict[word_key] = usage
            
            # Then, add any missing words from our learned list with default descriptions
            for w in words:
                word_key = w.word_cantonese or w.word
                if word_key not in word_usage_dict:
                    # Add missing word with default description
                    word_usage_dict[word_key] = w.definition_cantonese or w.example_cantonese or f"用於故事中 (Used in the story)"
            
            print(f"[StoryGenerator] Words learned today: {len(words)}")
            print(f"[StoryGenerator] Words in AI response: {len(ai_word_usage)}")
            print(f"[StoryGenerator] Final word_usage count: {len(word_usage_dict)}")

            default_audio_setting = None
            if settings.STORY_AUDIO_VOICE_SETTINGS:
                default_audio_setting = settings.STORY_AUDIO_VOICE_SETTINGS[0]
            
            # Create story record
            story = GeneratedStory(
                id=story_id,
                child_id=request.child_id,
                title=story_data.get("title") or "今日的故事",
                title_english=story_data.get("title_english") or "Story",
                theme=request.theme,
                generated_at=datetime.utcnow(),
                generated_by="story_generator",
                content_cantonese=story_text,
                content_english=None,  # TODO: Add translation if requested
                jyutping=None,  # TODO: Add jyutping for difficult words
                vocab_used=vocab_used,
                story_text=story_text,
                story_text_ssml=self._build_story_ssml(story_text),
                story_generate_provdier=str(self.provider),
                story_generate_model=self.llm_service.model if self.llm_service else "unknown",
                featured_words=[w.word_id for w in words],
                word_usage=word_usage_dict,
                audio_url=None,  # TODO: Generate TTS audio
                reading_time_minutes=request.reading_time_minutes,
                word_count=len(story_text),  # Use cleaned text length, not raw AI response
                difficulty_level="easy",
                cultural_references=None,  # TODO: Extract cultural references
                ai_model=self.llm_service.model if self.llm_service else "unknown",
                generation_prompt=prompt,
                generation_time_seconds=time.time() - start_time,
                audio_filename=f"story_{story_id}.mp3",
                audio_generate_provider=(
                    default_audio_setting.get("audio_generate_provider")
                    if default_audio_setting
                    else None
                ),
                audio_generate_voice_name=(
                    default_audio_setting.get("audio_generate_voice_name")
                    if default_audio_setting
                    else None
                )
            )
            
            # Save to database
            db.add(story)
            await db.commit()
            await db.refresh(story)
            
            generation_time = time.time() - start_time
            return story, words, generation_time
            
        except Exception as e:
            print(f"[StoryGenerator] Error generating story: {str(e)}")
            raise


# Global instance
story_generator = StoryGeneratorService()
