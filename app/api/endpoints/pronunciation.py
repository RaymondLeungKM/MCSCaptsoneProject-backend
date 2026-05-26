"""
Pronunciation validation endpoint.
POST /api/v1/audio/validate-pronunciation

Accepts a webm audio blob + target word metadata.
If GROQ_API_KEY is set: transcribes via a selectable Groq speech-to-text model.
If not set: returns 503 so the frontend falls back to Web Speech API scoring.
"""
import os
import re
import tempfile
from time import perf_counter
from typing import Any, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

DEFAULT_TRANSCRIPTION_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "whisper-large-v3"

RECOMMENDED_PRONUNCIATION_MODELS = [
    {
        "provider": "groq",
        "id": "whisper-large-v3",
        "name": "Groq Whisper Large v3",
        "default": True,
        "notes": "Best baseline Cantonese transcription quality.",
    },
    {
        "provider": "groq",
        "id": "whisper-large-v3-turbo",
        "name": "Groq Whisper Large v3 Turbo",
        "default": False,
        "notes": "Lower-latency option for quick comparison testing.",
    },
]

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


def _groq_enabled() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def _available_pronunciation_models() -> list[dict[str, Any]]:
    return [
        {
            **model,
            "enabled": model["provider"] == "groq" and _groq_enabled(),
        }
        for model in RECOMMENDED_PRONUNCIATION_MODELS
    ]


def _resolve_provider(provider: str) -> str:
    return (provider or DEFAULT_TRANSCRIPTION_PROVIDER).strip().lower() or DEFAULT_TRANSCRIPTION_PROVIDER


def _resolve_model(model: str) -> str:
    return (model or DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL


def _build_unavailable_response(provider: str, model: str, detail: str, status_code: int = 503):
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "provider": provider,
            "model": model,
            "available_models": _available_pronunciation_models(),
        },
    )


def _get_segment_avg_logprob(segment: Any) -> float:
    if isinstance(segment, dict):
        return float(segment.get("avg_logprob", -1.0))
    return float(getattr(segment, "avg_logprob", -1.0))


async def _transcribe_with_groq(
    audio_bytes: bytes,
    suffix: str,
    model: str,
    language: str,
) -> tuple[str, float]:
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed")

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        client = Groq(api_key=os.getenv("GROQ_API_KEY", "").strip())
        with open(tmp_path, "rb") as file_handle:
            transcription = client.audio.transcriptions.create(
                file=(f"audio{suffix}", file_handle),
                model=model,
                language=language,
                response_format="verbose_json",
            )

        heard = (getattr(transcription, "text", "") or "").strip()

        confidence: float = 0.0
        segments = getattr(transcription, "segments", []) or []
        if segments:
            import math

            confidence = round(min(1.0, math.exp(_get_segment_avg_logprob(segments[0]))), 3)

        return heard, confidence
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def _run_pronunciation_validation(
    *,
    audio: UploadFile,
    word_cantonese: str,
    jyutping: str,
    word_id: str,
    provider: str,
    model: str,
    language: str,
):
    resolved_provider = _resolve_provider(provider)
    resolved_model = _resolve_model(model)

    if resolved_provider != "groq":
        return _build_unavailable_response(
            resolved_provider,
            resolved_model,
            f"Unsupported transcription provider: {resolved_provider}",
            status_code=400,
        )

    if not _groq_enabled():
        return _build_unavailable_response(
            resolved_provider,
            resolved_model,
            "GROQ_API_KEY not configured — recognition testing unavailable",
        )

    audio_bytes = await audio.read()
    suffix = ".webm"
    original_name = getattr(audio, "filename", "") or ""
    if original_name.endswith(".mp4"):
        suffix = ".mp4"
    elif original_name.endswith(".wav"):
        suffix = ".wav"

    started_at = perf_counter()
    try:
        heard, confidence = await _transcribe_with_groq(
            audio_bytes=audio_bytes,
            suffix=suffix,
            model=resolved_model,
            language=language,
        )
    except RuntimeError as exc:
        return _build_unavailable_response(resolved_provider, resolved_model, str(exc))
    except Exception as exc:
        print(f"[Pronunciation] {resolved_provider} error ({resolved_model}): {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Transcription failed: {str(exc)}",
                "provider": resolved_provider,
                "model": resolved_model,
            },
        )

    target = (word_cantonese or "").strip()
    result = _score(heard, target) if target else None

    return {
        "result": result,
        "heard": heard,
        "confidence": confidence,
        "target": target,
        "jyutping": (jyutping or "").strip(),
        "word_id": (word_id or "").strip(),
        "provider": resolved_provider,
        "model": resolved_model,
        "elapsed_ms": round((perf_counter() - started_at) * 1000, 1),
    }

# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/pronunciation-models")
async def get_pronunciation_models():
    """List configured speech-to-text models that can be tested from the speech tester."""
    return {
        "default_provider": DEFAULT_TRANSCRIPTION_PROVIDER,
        "default_model": DEFAULT_GROQ_MODEL,
        "models": _available_pronunciation_models(),
    }

@router.post("/validate-pronunciation")
async def validate_pronunciation(
    audio: UploadFile = File(...),
    word_cantonese: str = Form(default=""),
    jyutping: str = Form(default=""),
    word_id: str = Form(default=""),
    provider: str = Form(default=DEFAULT_TRANSCRIPTION_PROVIDER),
    model: str = Form(default=DEFAULT_GROQ_MODEL),
    language: str = Form(default="yue"),
):
    """
    Validate child's pronunciation using the configured speech-to-text provider.
    Returns 503 if speech-to-text is not configured so the frontend can use its fallback.
    """
    return await _run_pronunciation_validation(
        audio=audio,
        word_cantonese=word_cantonese,
        jyutping=jyutping,
        word_id=word_id,
        provider=provider,
        model=model,
        language=language,
    )


@router.post("/test-pronunciation")
async def test_pronunciation(
    audio: UploadFile = File(...),
    word_cantonese: str = Form(default=""),
    jyutping: str = Form(default=""),
    word_id: str = Form(default=""),
    provider: str = Form(default=DEFAULT_TRANSCRIPTION_PROVIDER),
    model: str = Form(default=DEFAULT_GROQ_MODEL),
    language: str = Form(default="yue"),
):
    """Test an alternate pronunciation-recognition model without changing game defaults."""
    return await _run_pronunciation_validation(
        audio=audio,
        word_cantonese=word_cantonese,
        jyutping=jyutping,
        word_id=word_id,
        provider=provider,
        model=model,
        language=language,
    )
