"""
AI Tutor Chat API – Epic 8.2.4

A lightweight, parent-supervised conversational tutor that answers
children's questions about Cantonese vocabulary in a safe, encouraging way.

Key safety constraints
-----------------------
* System prompt strongly restricts the model to vocabulary-only topics.
* Conversation history is bounded to the last 10 turns to control cost/latency.
* The endpoint requires a valid parent JWT so parents can supervise.
* All responses are tagged safe_mode=True (content policy enforced via prompt).
"""
import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User, Child
from app.models.vocabulary import Word
from app.core.security import get_current_active_user
from app.schemas.phase8 import TutorChatRequest, TutorChatResponse
from app.services.llm_service import LLMService, LLMProvider, LLMMessage

router = APIRouter()

MAX_HISTORY_TURNS = 10  # keep context window small


def _build_llm_service() -> LLMService:
    if os.getenv("ANTHROPIC_API_KEY"):
        return LLMService(provider=LLMProvider.ANTHROPIC)
    if os.getenv("OPENAI_API_KEY"):
        return LLMService(provider=LLMProvider.OPENAI)
    return LLMService(provider=LLMProvider.OLLAMA)


SYSTEM_PROMPT = """你是「小博士」，一個親切、有耐心的廣東話詞彙學習助手，專門幫助3至6歲的幼兒學習廣東話。

**規則：**
1. 只回答與廣東話詞彙學習有關的問題。若問題超出範圍，請溫和地將話題帶回詞彙學習。
2. 使用簡單、兒童友善的廣東話回答。可以適當加入英文括號解釋。
3. 每個回答中盡量舉一個生動的例句。
4. 語氣要鼓勵性強，多用正面語言（如「做得好！」「很聰明！」）。
5. 如果不確定答案，坦誠地說「我需要查一查，不如問問爸爸媽媽！」
6. 絕對不能討論任何不適合兒童的話題。
7. 回答長度適中，不超過3-4句。
"""


@router.post("/{child_id}/chat", response_model=TutorChatResponse)
async def tutor_chat(
    child_id: str,
    request: TutorChatRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a question to the AI tutor and get a Cantonese vocabulary response.
    Parent authentication required (safe mode).
    """
    # Verify child belongs to requesting parent
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")

    # Optional word context
    word_context = ""
    if request.word_id:
        word_result = await db.execute(select(Word).where(Word.id == request.word_id))
        word_obj = word_result.scalar_one_or_none()
        if word_obj:
            word_context = (
                f"\n\n**當前學習的詞彙：**"
                f"\n廣東話：{word_obj.word_cantonese}（{word_obj.jyutping}）"
                f"\n英文：{word_obj.word}"
                f"\n解釋：{word_obj.definition_cantonese or word_obj.definition}"
                f"\n例句：{word_obj.example_cantonese or word_obj.example}"
            )

    # Build message history (bounded)
    history = request.history[-MAX_HISTORY_TURNS:]
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=SYSTEM_PROMPT + word_context)
    ]
    for turn in history:
        messages.append(LLMMessage(role=turn.role, content=turn.content))
    messages.append(LLMMessage(role="user", content=request.question))

    try:
        llm = _build_llm_service()
        answer = await llm.generate(messages, temperature=0.6, max_tokens=300)
    except Exception as exc:
        # Graceful degradation – return a canned fallback instead of a 500
        answer = (
            "對唔住，我依家唔係好方便回答。請問問爸爸媽媽！😊"
        )
        print(f"[TutorChat] LLM error: {exc}")

    return TutorChatResponse(
        answer=answer,
        referenced_words=[request.word_id] if request.word_id else [],
        safe_mode=True,
    )
