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
import anthropic
import openai

from app.models.daily_words import DailyWordTracking, GeneratedStory
from app.models.vocabulary import Word
from app.models.user import Child
from app.schemas.stories import DailyWordSummary, StoryGenerationRequest


class StoryGeneratorService:
    """Service for generating AI-powered bedtime stories"""
    
    def __init__(self):
        # Try to use Claude (Anthropic) first, fallback to OpenAI
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        
        if self.anthropic_key:
            self.client = anthropic.Anthropic(api_key=self.anthropic_key)
            self.ai_model = "claude-3-5-sonnet-20241022"
            self.provider = "anthropic"
        elif self.openai_key:
            self.client = openai.OpenAI(api_key=self.openai_key)
            self.ai_model = "gpt-4o"
            self.provider = "openai"
        else:
            self.client = None
            self.ai_model = None
            self.provider = None
            print("[StoryGenerator] Warning: No AI API keys found. Story generation will be disabled.")
    
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
請只輸出JSON格式，包含以下字段：
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

請確保JSON格式正確，可以被解析。"""
        
        return prompt
    
    async def generate_story(
        self,
        db: AsyncSession,
        request: StoryGenerationRequest
    ) -> tuple[Optional[GeneratedStory], List[DailyWordSummary], float]:
        """Generate a bedtime story using AI"""
        
        if not self.client:
            raise ValueError("No AI API key configured. Please set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.")
        
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
        
        # Call AI API
        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.ai_model,
                    max_tokens=2000,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                )
                ai_response = response.content[0].text
            else:  # openai
                response = self.client.chat.completions.create(
                    model=self.ai_model,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }],
                    temperature=0.8,
                    max_tokens=2000
                )
                ai_response = response.choices[0].message.content
            
            # Parse JSON response
            import json
            # Extract JSON from markdown code blocks if present
            if "```json" in ai_response:
                ai_response = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                ai_response = ai_response.split("```")[1].split("```")[0].strip()
            
            story_data = json.loads(ai_response)
            
            # Create story record
            story = GeneratedStory(
                id=str(uuid.uuid4()),
                child_id=request.child_id,
                title=story_data.get("title", "今日的故事"),
                title_english=story_data.get("title_english"),
                theme=request.theme,
                content_cantonese=story_data.get("content", ""),
                content_english=None,  # TODO: Add translation if requested
                jyutping=None,  # TODO: Add jyutping for difficult words
                featured_words=[w.word_id for w in words],
                word_usage=story_data.get("word_usage", {}),
                audio_url=None,  # TODO: Generate TTS audio
                reading_time_minutes=request.reading_time_minutes,
                word_count=len(story_data.get("content", "")),
                difficulty_level="easy",
                cultural_references=None,  # TODO: Extract cultural references
                ai_model=self.ai_model,
                generation_prompt=prompt,
                generation_time_seconds=time.time() - start_time
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
