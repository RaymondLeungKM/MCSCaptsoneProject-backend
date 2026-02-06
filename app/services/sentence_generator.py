"""
Sentence Generation Service
Generate age-appropriate Cantonese sentences for vocabulary words
"""
from typing import List, Optional, Dict, Any
import json
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.services.llm_service import get_llm_service, LLMMessage, LLMProvider
from app.models.vocabulary import Word
from app.models.generated_sentences import GeneratedSentence as GeneratedSentenceModel


class GeneratedSentence(BaseModel):
    """A generated example sentence"""
    sentence: str  # Cantonese Traditional Chinese sentence
    sentence_english: Optional[str] = None  # English translation
    jyutping: Optional[str] = None  # Romanization
    context: str  # Context/scenario (e.g., "at home", "in park")
    difficulty: str = "easy"  # easy, medium, hard


class SentenceGenerationResult(BaseModel):
    """Result of sentence generation"""
    word: str
    word_cantonese: str
    sentences: List[GeneratedSentence]
    total_generated: int


class SentenceGenerator:
    """
    Generate contextual example sentences for vocabulary words
    """
    
    # Common contexts for Hong Kong preschoolers
    CONTEXTS = [
        {"id": "home", "name": "家", "name_en": "At Home", "description": "家庭環境"},
        {"id": "school", "name": "學校", "name_en": "At School", "description": "學校活動"},
        {"id": "park", "name": "公園", "name_en": "In the Park", "description": "戶外玩耍"},
        {"id": "supermarket", "name": "超市", "name_en": "Supermarket", "description": "購物環境"},
        {"id": "playground", "name": "遊樂場", "name_en": "Playground", "description": "玩耍時間"},
        {"id": "meal_time", "name": "食飯時間", "name_en": "Meal Time", "description": "用餐場景"},
        {"id": "bedtime", "name": "睡覺時間", "name_en": "Bedtime", "description": "睡前時間"},
    ]
    
    def __init__(self, provider: LLMProvider = LLMProvider.OLLAMA):
        self.llm = get_llm_service(provider)
    
    def _build_generation_prompt(
        self,
        word_text: str,
        word_en: str,
        word_jyutping: str,
        category: str,
        num_sentences: int = 3,
        contexts: Optional[List[str]] = None
    ) -> List[LLMMessage]:
        """
        Build prompt for sentence generation
        
        Args:
            word_text: Cantonese word text
            word_en: English word text
            word_jyutping: Jyutping romanization
            category: Word category
            num_sentences: Number of sentences to generate
            contexts: Specific contexts to use (defaults to varied contexts)
        """
        
        # Select contexts
        if contexts:
            selected_contexts = [c for c in self.CONTEXTS if c["id"] in contexts]
        else:
            # Use varied contexts
            selected_contexts = self.CONTEXTS[:num_sentences]
        
        context_descriptions = ", ".join([f"{c['name']} ({c['name_en']})" for c in selected_contexts])
        
        system_prompt = """你是一位專業的香港幼兒教育專家和粵語拼音專家。
你的任務是為詞彙創作簡單例句，並提供100%正確的粵語拼音 (Jyutping)。

**核心要求 - 粵語拼音正確性：**
這是最重要的要求！每個漢字必須有對應的正確粵語拼音。

**標準粵語拼音對照表（必須使用）：**
我 = ngo5 | 你 = nei5 | 佢 = keoi5 | 係 = hai6 | 喺 = hai2 | 在 = zoi6
媽 = maa1/maa4 | 爸 = baa1/baa4 | 哥 = go1/go4 | 姐 = ze1/ze2 | 細 = sai3
見 = gin3 | 到 = dou2/dou3 | 有 = jau5 | 冇 = mou5 | 要 = jiu1/jiu3
食 = sik6 | 飲 = jam2 | 煮 = zyu2 | 玩 = waan2/waan4 | 睇 = tai2
屋 = uk1 | 企 = kei5 | 家 = gaa1 | 廚 = cyu4 | 房 = fong2/fong4
學 = hok6 | 校 = haau6 | 書 = syu1 | 教 = gaau1/gaau3 | 讀 = duk6
公 = gung1 | 園 = jyun4 | 波 = bo1 | 球 = kau4 | 車 = ce1
一 = jat1 | 兩 = loeng5 | 三 = saam1 | 隻 = zek3 | 個 = go3

**絕對禁止的錯誤：**
❌ 少字：如果句子有7個字，jyutping必須有7個音節
❌ 多字：不要憑空添加不存在的字的拼音
❌ 亂配：不要用其他字的拼音來代替（如：老 ≠ gaa4，應該是 lou5）
❌ 英文字母拼錯：如 zoi6 (在) 不是 zai4

You are a professional Hong Kong Cantonese educator and Jyutping expert.
Your task is to create simple sentences with 100% accurate Cantonese Jyutping romanization.

**CRITICAL: Jyutping Accuracy is #1 Priority**
Every Chinese character MUST have its correct corresponding Jyutping syllable."""
        
        user_prompt = f"""為詞彙「{word_text}」創作 {num_sentences} 個簡單例句。

**目標詞彙資訊：**
- 粵語：{word_text}
- English: {word_en}
- 粵語拼音：{word_jyutping}
- 類別：{category}
- 語境：{context_descriptions}

**創作步驟（必須按順序）：**

步驟1：先寫出簡單的粵語句子（8-12字，日常場景）
步驟2：數清楚句子有多少個漢字
步驟3：為每個漢字寫出正確的粵語拼音
步驟4：檢查拼音數量是否等於漢字數量
步驟5：如果不相等，重新檢查並修正

**範例1（正確）：**
句子：我見到一隻貓 (共7個字)
拆解：我/見/到/一/隻/貓
Jyutping: ngo5 gin3 dou2 jat1 zek3 maau1 (7個音節 ✓)

**範例2（正確）：**
句子：媽媽在廚房煮飯 (共7個字)
拆解：媽/媽/在/廚/房/煮/飯
Jyutping: maa4 maa1 zoi6 cyu4 fong2 zyu2 faan6 (7個音節 ✓)

**範例3（正確）：**
句子：哥哥去公園玩 (共6個字)  
拆解：哥/哥/去/公/園/玩
Jyutping: go4 go1 heoi3 gung1 jyun4 waan2 (6個音節 ✓)

**錯誤範例（絕對不可以）：**
❌ 句子有7個字，但只有4個拼音
❌ 拼音用錯字（如：老師 應該是 lou5 si1，不是 gaa4 gaa1）
❌ 憑空添加不存在的拼音
❌ 荒謬的句子（如：媽媽養大象）

**JSON 格式輸出：**
{{
  "sentences": [
    {{
      "sentence": "簡短粵語句子",
      "sentence_english": "English translation", 
      "jyutping": "每個字對應一個拼音 用空格分隔",
      "context": "home",
      "difficulty": "easy"
    }}
  ]
}}

**最終檢查清單：**
✓ 句子合理、日常場景
✓ 包含目標詞彙「{word_text}」
✓ 漢字數量 = 拼音音節數量
✓ 適合3-5歲幼兒
✓ 語境不同 ({context_descriptions})
"""

        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
    
    async def generate_sentences(
        self,
        word: Word,
        num_sentences: int = 3,
        contexts: Optional[List[str]] = None,
        temperature: float = 0.8,
        db: Optional[AsyncSession] = None,
        save_to_db: bool = False
    ) -> SentenceGenerationResult:
        """
        Generate example sentences for a vocabulary word
        
        Args:
            word: The Word model instance
            num_sentences: Number of sentences to generate (default 3)
            contexts: Specific contexts to use (optional)
            temperature: LLM creativity level (0.0-1.0)
            db: Database session (required if save_to_db=True)
            save_to_db: Whether to save generated sentences to database
            
        Returns:
            SentenceGenerationResult with generated sentences
        """
        # Extract all word attributes at the start to avoid lazy loading during async operations
        word_id = word.id
        word_text = word.word
        word_cantonese = word.word_cantonese or word.word
        word_jyutping = word.jyutping or ""
        word_example = word.example
        word_example_cantonese = word.example_cantonese
        category = word.category_rel.name if word.category_rel else "general"
        
        # Build prompt
        messages = self._build_generation_prompt(
            word_text=word_cantonese,
            word_en=word_text,
            word_jyutping=word_jyutping,
            category=category,
            num_sentences=num_sentences,
            contexts=contexts
        )
        
        # Generate from LLM
        response = await self.llm.generate(
            messages=messages,
            temperature=temperature,
            max_tokens=1500
        )
        
        # Parse JSON response
        try:
            # Extract JSON from response (handle markdown code blocks)
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            data = json.loads(response_clean)
            sentences = [GeneratedSentence(**s) for s in data["sentences"]]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[SentenceGenerator] Failed to parse LLM response: {e}")
            print(f"[SentenceGenerator] Raw response: {response}")
            # Fallback: create basic sentences using pre-extracted attributes
            sentences = [
                GeneratedSentence(
                    sentence=word_example_cantonese or word_example or f"我見到{word_cantonese}。",
                    sentence_english=word_example or f"I see a {word_text}.",
                    context="general",
                    difficulty="easy"
                )
            ]
        
        # Save to database if requested
        if save_to_db and db is not None:
            try:
                # Delete existing sentences for this word
                await db.execute(
                    delete(GeneratedSentenceModel).where(
                        GeneratedSentenceModel.word_id == word_id
                    )
                )
                
                # Save new sentences
                for sent in sentences:
                    db_sentence = GeneratedSentenceModel(
                        word_id=word_id,
                        sentence=sent.sentence,
                        sentence_english=sent.sentence_english,
                        jyutping=sent.jyutping,
                        context=sent.context,
                        difficulty=sent.difficulty
                    )
                    db.add(db_sentence)
                
                await db.commit()
                print(f"[SentenceGenerator] Saved {len(sentences)} sentences to DB for word: {word_text}")
            except Exception as e:
                print(f"[SentenceGenerator] Error saving sentences to DB: {e}")
                import traceback
                traceback.print_exc()
                await db.rollback()
        
        return SentenceGenerationResult(
            word=word_text,
            word_cantonese=word_cantonese,
            sentences=sentences,
            total_generated=len(sentences)
        )
    
    async def generate_contextual_sentences(
        self,
        word: Word,
        context_id: str
    ) -> List[GeneratedSentence]:
        """
        Generate sentences for a specific context
        
        Args:
            word: The Word model
            context_id: Context identifier (e.g., "home", "park")
            
        Returns:
            List of generated sentences for that context
        """
        result = await self.generate_sentences(
            word=word,
            num_sentences=2,
            contexts=[context_id]
        )
        return result.sentences


# Singleton instance
_sentence_generator: Optional[SentenceGenerator] = None


def get_sentence_generator(provider: LLMProvider = LLMProvider.OLLAMA) -> SentenceGenerator:
    """Get or create SentenceGenerator instance"""
    global _sentence_generator
    if _sentence_generator is None:
        _sentence_generator = SentenceGenerator(provider=provider)
    return _sentence_generator
