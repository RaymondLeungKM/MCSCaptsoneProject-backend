"""
Pronunciation validation endpoint.
POST /api/v1/audio/validate-pronunciation

Accepts a webm audio blob + target word metadata.
If GROQ_API_KEY is set: transcribes via Groq Whisper large-v3 (Cantonese).
If not set: returns 503 so the frontend falls back to Web Speech API scoring.
"""
import os
import re
import tempfile
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

# ── Scoring (mirrors frontend scoreTranscript logic) ─────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r'[.,!?。，！？、\s]', '', text).strip().lower()

def _score(heard: str, target: str) -> str:
    h = _normalize(heard)
    t = _normalize(target)
    if not h:
        return "incorrect"

    # Direct match / containment
    if h == t or t in h or h in t:
        return "correct"

    # Character overlap (for CJK)
    target_chars = list(t)
    heard_set = set(h)
    matched = [c for c in target_chars if c in heard_set]
    if not target_chars:
        return "incorrect"
    ratio = len(matched) / len(target_chars)

    if ratio >= 0.75:
        return "correct"
    if ratio >= 0.45:
        return "partial"
    return "incorrect"

# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/validate-pronunciation")
async def validate_pronunciation(
    audio: UploadFile = File(...),
    word_cantonese: str = Form(default=""),
    jyutping: str = Form(default=""),
    word_id: str = Form(default=""),
):
    """
    Validate child's pronunciation using Groq Whisper (Cantonese).
    Returns {"result": "correct"|"partial"|"incorrect", "heard": str, "confidence": float}.
    Returns 503 if GROQ_API_KEY is not configured so the frontend uses its fallback.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        return JSONResponse(
            status_code=503,
            content={"detail": "GROQ_API_KEY not configured — use client-side fallback"},
        )

    try:
        from groq import Groq
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"detail": "groq package not installed"},
        )

    audio_bytes = await audio.read()

    # Write to a named temp file so Groq client can open it
    suffix = ".webm"
    original_name = getattr(audio, "filename", "") or ""
    if original_name.endswith(".mp4"):
        suffix = ".mp4"
    elif original_name.endswith(".wav"):
        suffix = ".wav"

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        client = Groq(api_key=groq_key)
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(f"audio{suffix}", f),
                model="whisper-large-v3",
                language="yue",        # ISO 639-3 code for Cantonese
                response_format="verbose_json",
            )

        # Groq returns verbose_json with .text and segments[].avg_logprob
        heard = (transcription.text or "").strip()
        # Derive a rough confidence from avg_logprob of first segment
        confidence: float = 0.0
        segments = getattr(transcription, "segments", []) or []
        if segments:
            import math
            avg_lp = segments[0].get("avg_logprob", -1.0)
            confidence = round(min(1.0, math.exp(avg_lp)), 3)

        result = _score(heard, word_cantonese)

        return {
            "result": result,
            "heard": heard,
            "confidence": confidence,
            "target": word_cantonese,
        }

    except Exception as exc:
        print(f"[Pronunciation] Groq error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Transcription failed: {str(exc)}"},
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
