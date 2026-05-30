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
from app.core.child_age import calculate_child_age
from app.schemas.stories import DailyWordSummary, StoryGenerationRequest
from app.core.config import settings
from app.services.llm_service import LLMService, LLMProvider, LLMMessage
from app.services.tts_service import tts_service


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

    @staticmethod
    def _word_label(word: DailyWordSummary) -> str:
        return (word.word_cantonese or word.word or word.word_id).strip()

    @staticmethod
    def _should_use_offline_fallback(error: Exception) -> bool:
        message = str(error).lower()
        fallback_markers = (
            "cannot connect to ollama",
            "ollama request timed out",
            "http://localhost:11434",
            "llm service not initialized",
            "api key required",
            "connection refused",
        )
        return any(marker in message for marker in fallback_markers)

    def _build_offline_story_content(
        self,
        child_name: str,
        theme: Optional[str],
        words: List[DailyWordSummary],
    ) -> tuple[str, str, Dict[str, str]]:
        theme_settings = {
            "adventure": ("冒險", "彩虹小路", "勇敢出發"),
            "family": ("家庭", "溫暖小屋", "互相照顧"),
            "animals": ("動物", "森林草地", "認識新朋友"),
            "nature": ("大自然", "月光花園", "細心觀察"),
            "friendship": ("友誼", "星光公園", "分享快樂"),
            "bedtime": ("睡前", "月亮小鎮", "安心入睡"),
        }
        theme_label, setting_place, closing_mood = theme_settings.get(
            theme or "bedtime",
            (theme or "睡前", "發光小路", "安心休息"),
        )

        vocab_terms = [self._word_label(word) for word in words]
        word_usage = {
            self._word_label(word): (
                word.definition_cantonese
                or word.example_cantonese
                or "在故事裡成為一位溫柔的小主角。"
            )
            for word in words
        }

        story_lines = [
            (
                f"今晚，{child_name}抱住軟綿綿的小被子，準備聽一個{theme_label}故事。"
                f"窗外有柔柔的風，月亮把銀光灑進房間，帶領{child_name}慢慢走進{setting_place}。"
            ),
            (
                f"在{setting_place}入口，{child_name}先看見{vocab_terms[0]}。"
                f"{vocab_terms[0]}輕輕搖一搖，好像在說：「歡迎你呀，我們一起找找今晚的驚喜吧！」"
            ),
        ]

        action_templates = [
            "走前幾步，{child}又遇見{label}，大家停下來聽風聲，心裡覺得安安靜靜又好舒服。",
            "再往前看，{label}就在柔和的光影裡等著，提醒{child}每學會一個新詞語，世界就會亮一點點。",
            "不久之後，{child}把{label}也放進小口袋裡，決定把今天的好奇心同笑容一起帶回家。",
            "最後，{label}陪著{child}抬頭看星星，讓今晚的天空變得更加閃閃發亮。",
        ]

        for index, label in enumerate(vocab_terms[1:5]):
            template = action_templates[index % len(action_templates)]
            story_lines.append(template.format(child=child_name, label=label))

        all_words = "、".join(vocab_terms)
        story_lines.append(
            (
                f"回家的時候，{child_name}輕輕數著今天認識的{all_words}，"
                f"知道它們都會變成心裡的小星星。"
                f"{child_name}笑著鑽進被窩，帶著{closing_mood}的心情，慢慢進入甜甜的夢鄉。"
            )
        )

        title_word = vocab_terms[0] if vocab_terms else "星光"
        title = f"{child_name}和{title_word}的{theme_label}故事"
        story_text = "\n\n".join(story_lines)
        return title, story_text, word_usage

    async def _generate_story_offline(
        self,
        db: AsyncSession,
        request: StoryGenerationRequest,
        child: Child,
        words: List[DailyWordSummary],
        start_time: float,
        prompt: str,
        reason: str,
    ) -> tuple[GeneratedStory, List[DailyWordSummary], float]:
        story_id = str(uuid.uuid4())
        title, story_text, word_usage = self._build_offline_story_content(
            child.name,
            request.theme,
            words,
        )
        vocab_terms = [self._word_label(word) for word in words]
        vocab_used = ", ".join(vocab_terms)
        if len(vocab_used) > 500:
            vocab_used = vocab_used[:497] + "..."

        story = GeneratedStory(
            id=story_id,
            child_id=request.child_id,
            title=title,
            title_english=f"{child.name}'s Cozy Story",
            theme=request.theme,
            generated_at=datetime.utcnow(),
            generated_by="story_generator_offline_fallback",
            content_cantonese=story_text,
            content_english=None,
            jyutping=None,
            vocab_used=vocab_used,
            story_text=story_text,
            story_text_ssml=self._build_story_ssml(story_text),
            story_generate_provdier="offline_fallback",
            story_generate_model="local-template",
            featured_words=vocab_terms,
            word_usage=word_usage,
            audio_url=None,
            audio_duration_seconds=None,
            audio_filename=f"story_{story_id}.mp3",
            audio_generate_provider=None,
            audio_generate_voice_name=None,
            reading_time_minutes=request.reading_time_minutes,
            word_count=len(story_text),
            difficulty_level="easy",
            cultural_references=None,
            ai_model="local-template",
            generation_prompt=f"{prompt}\n\n[fallback_reason] {reason}",
            generation_time_seconds=time.time() - start_time,
        )

        db.add(story)
        await db.commit()
        await db.refresh(story)

        generation_time = time.time() - start_time
        return story, words, generation_time
    
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

        start_time = time.time()

        child_query = select(Child).where(Child.id == request.child_id)
        child_result = await db.execute(child_query)
        child = child_result.scalar_one_or_none()
        if not child:
            raise ValueError(f"Child not found: {request.child_id}")

        words = await self.get_daily_words(db, request.child_id, request.date, limit=10)
        if len(words) == 0:
            raise ValueError("No words learned today to include in story")

        prompt = self._create_story_prompt(
            child_name=child.name,
            child_age=calculate_child_age(
                stored_age=child.age,
                birth_year=child.birth_year,
                birth_month=child.birth_month,
                as_of=request.date.date() if isinstance(request.date, datetime) else None,
            ),
            words=words,
            theme=request.theme,
            word_count_target=request.word_count_target,
        )

        if not self.llm_service:
            print("[StoryGenerator] No LLM service available, using offline fallback story.")
            return await self._generate_story_offline(
                db,
                request,
                child,
                words,
                start_time,
                prompt,
                reason="LLM service not initialized",
            )

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            ai_response = await self.llm_service.generate(
                messages=messages,
                temperature=0.8,
                max_tokens=5000,
            )

            story_data = self._parse_story_json(ai_response)
            story_id = str(uuid.uuid4())

            story_text_raw = story_data.get("content") or ""
            if not story_text_raw:
                raise ValueError("AI response did not contain story content. Please try again.")

            story_text = self._clean_story_content(story_text_raw)
            if len(story_text) < 50 and len(story_text_raw) > 50:
                story_text = story_text_raw.replace('\\n', '\n').replace('\\"', '"')

            vocab_terms = [w.word_cantonese or w.word for w in words]
            vocab_used = ", ".join(vocab_terms)
            if len(vocab_used) > 500:
                vocab_used = vocab_used[:497] + "..."

            valid_word_keys = {(w.word_cantonese or w.word) for w in words}
            ai_word_usage = story_data.get("word_usage") or {}
            if not isinstance(ai_word_usage, dict):
                ai_word_usage = {}

            word_usage_dict = {}
            for word_key, usage in ai_word_usage.items():
                if word_key in valid_word_keys:
                    word_usage_dict[word_key] = usage

            for w in words:
                word_key = w.word_cantonese or w.word
                if word_key not in word_usage_dict:
                    word_usage_dict[word_key] = (
                        w.definition_cantonese
                        or w.example_cantonese
                        or "用於故事中 (Used in the story)"
                    )

            default_audio_setting = settings.STORY_AUDIO_VOICE_SETTINGS[0] if settings.STORY_AUDIO_VOICE_SETTINGS else None

            generated_audio = None
            try:
                generated_audio = tts_service.generate_audio(
                    story_text,
                    language="cantonese",
                    voice_name=(
                        default_audio_setting.get("audio_generate_voice_name")
                        if default_audio_setting
                        else None
                    ),
                    speech_rate=0.85,
                    filename_prefix="story",
                )
            except Exception as audio_error:
                print(f"[StoryGenerator] Warning: story audio generation failed: {audio_error}")

            story = GeneratedStory(
                id=story_id,
                child_id=request.child_id,
                title=story_data.get("title") or "今日的故事",
                title_english=story_data.get("title_english") or "Story",
                theme=request.theme,
                generated_at=datetime.utcnow(),
                generated_by="story_generator",
                content_cantonese=story_text,
                content_english=None,
                jyutping=None,
                vocab_used=vocab_used,
                story_text=story_text,
                story_text_ssml=self._build_story_ssml(story_text),
                story_generate_provdier=str(self.provider),
                story_generate_model=self.llm_service.model if self.llm_service else "unknown",
                featured_words=vocab_terms,
                word_usage=word_usage_dict,
                audio_url=(generated_audio["audio_url"] if generated_audio else None),
                audio_duration_seconds=(generated_audio["audio_duration_seconds"] if generated_audio else None),
                audio_filename=(generated_audio["audio_filename"] if generated_audio else f"story_{story_id}.mp3"),
                audio_generate_provider=(
                    generated_audio["audio_generate_provider"]
                    if generated_audio
                    else (
                        default_audio_setting.get("audio_generate_provider")
                        if default_audio_setting
                        else None
                    )
                ),
                audio_generate_voice_name=(
                    generated_audio["audio_generate_voice_name"]
                    if generated_audio
                    else (
                        default_audio_setting.get("audio_generate_voice_name")
                        if default_audio_setting
                        else None
                    )
                ),
                reading_time_minutes=request.reading_time_minutes,
                word_count=len(story_text),
                difficulty_level="easy",
                cultural_references=None,
                ai_model=self.llm_service.model if self.llm_service else "unknown",
                generation_prompt=prompt,
                generation_time_seconds=time.time() - start_time,
            )

            db.add(story)
            await db.commit()
            await db.refresh(story)

            generation_time = time.time() - start_time
            return story, words, generation_time

        except Exception as e:
            print(f"[StoryGenerator] Error generating story: {str(e)}")
            if self._should_use_offline_fallback(e):
                print("[StoryGenerator] Falling back to offline template story.")
                return await self._generate_story_offline(
                    db,
                    request,
                    child,
                    words,
                    start_time,
                    prompt,
                    reason=str(e),
                )
            raise


# Global instance
story_generator = StoryGeneratorService()
