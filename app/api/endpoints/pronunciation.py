"""
Pronunciation validation endpoint.
POST /api/v1/audio/validate-pronunciation

Accepts a webm audio blob + target word metadata.
If OPENAI_API_KEY is set: transcribes via a selectable OpenAI speech-to-text model.
If not set: returns 503 so the frontend falls back to Web Speech API scoring.
"""
import os
import re
import tempfile
from time import perf_counter
from typing import Any, Optional

import httpx
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

DEFAULT_TRANSCRIPTION_PROVIDER = "openai"
DEFAULT_GROQ_MODEL = "whisper-large-v3"
DEFAULT_HUGGINGFACE_MODEL = "openai/whisper-large-v3"
DEFAULT_OPENAI_MODEL = "gpt-4o-transcribe"

SUPPORTED_TRANSCRIPTION_PROVIDERS = {"groq", "huggingface", "openai", "cloudflare"}
PROVIDER_ALIASES = {
    "hf": "huggingface",
    "huggingface-inference": "huggingface",
    "cf": "cloudflare",
    "cloudflare-ai": "cloudflare",
}

RECOMMENDED_PRONUNCIATION_MODELS = [
    # ── HuggingFace models (no API key required beyond HF token, strong Cantonese support) ──
    {
        "provider": "huggingface",
        "id": "openai/whisper-large-v3",
        "name": "openai/whisper-large-v3 via Hugging Face",
        "default": False,
        "notes": "Strong multilingual Whisper baseline. Supports Cantonese (yue) via the Hugging Face Inference API.",
    },
    # ── Cloudflare Workers AI (uses your CLOUDFLARE_AI_API_TOKEN, no OpenAI key needed) ──
    {
        "provider": "cloudflare",
        "id": "@cf/openai/whisper-large-v3-turbo",
        "name": "Cloudflare Whisper Large v3 Turbo",
        "default": False,
        "notes": "Whisper large-v3-turbo via Cloudflare Workers AI. Accepts an explicit language hint (yue for Cantonese), VAD filtering, and hallucination suppression — fixes the English romanisation issue of the older @cf/openai/whisper.",
    },
    {
        "provider": "cloudflare",
        "id": "@cf/openai/whisper",
        "name": "Cloudflare Whisper (legacy — no language control)",
        "default": False,
        "notes": "Legacy Cloudflare Whisper. No language parameter — auto-detects, often romanises Cantonese into English. Prefer whisper-large-v3-turbo above.",
    },
    # ── Groq models (requires GROQ_API_KEY) ──
    {
        "provider": "groq",
        "id": "whisper-large-v3",
        "name": "Groq Whisper Large v3",
        "default": False,
        "notes": "Best baseline Cantonese transcription quality via Groq's fast inference.",
    },
    {
        "provider": "groq",
        "id": "whisper-large-v3-turbo",
        "name": "Groq Whisper Large v3 Turbo",
        "default": False,
        "notes": "Lower-latency Groq option for quick Cantonese comparison testing.",
    },
    # ── OpenAI models (requires OPENAI_API_KEY) ──
    {
        "provider": "openai",
        "id": "gpt-4o-transcribe",
        "name": "OpenAI GPT-4o Transcribe",
        "default": False,
        "notes": "Best-performance managed OpenAI transcription candidate for Cantonese side-by-side testing.",
    },
    {
        "provider": "openai",
        "id": "whisper-1",
        "name": "OpenAI Whisper-1",
        "default": False,
        "notes": "Older managed Whisper baseline from OpenAI.",
    },
]

# ── Scoring (mirrors frontend scoreTranscript logic) ─────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r'[.,!?。，！？、\s]', '', text).strip().lower()


# ── Script-mismatch hallucination filter ─────────────────────────────────────
# Whisper (and other multilingual ASR models) sometimes "hallucinate" in a
# completely wrong script when the audio is short, silent, or ambiguous and no
# language hint is passed.  Common outputs include Thai (โหลโหล…), Arabic,
# Cyrillic, etc.  We detect this by checking whether the transcription contains
# any characters from the script we actually expect, and if not, treat the
# output as a failed transcription.

_CJK_RE     = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\U00020000-\U0002a6df]')
_THAI_RE    = re.compile(r'[\u0e00-\u0e7f]')
_ARAB_RE    = re.compile(r'[\u0600-\u06ff\u0750-\u077f]')
_CYR_RE     = re.compile(r'[\u0400-\u04ff]')
_HANGUL_RE  = re.compile(r'[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]')  # Korean
# Repeated-syllable hallucination: "ndo ndo ndo", "เดิน เดิน", etc.
# Matches 3+ repetitions of the same 1-5 char token separated by spaces.
_REPEAT_RE  = re.compile(r'\b(\S{1,5})(?: \1){2,}\b', re.IGNORECASE)
_LATIN_MOSTLY_RE = re.compile(r'^[a-zA-Z\s.,!?\-\'"0-9]+$')

_CJK_LANGUAGES = {"yue", "zh", "zh-cn", "zh-hk", "zh-tw", "cantonese", "chinese"}
_EN_LANGUAGES  = {"en", "en-us", "en-gb", "english"}

_INVALID_AUDIO_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif",
    ".pdf", ".doc", ".docx", ".txt", ".rtf", ".xlsx", ".csv", ".zip", ".gz",
}

_IMAGE_MAGIC_BYTES = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    # Note: RIFF is also the header of WAV/AVI files. Only reject if bytes 8-11
    # spell "WEBP" (actual WebP container). WAV has "WAVE" there instead.
    (b"%PDF", "PDF document"),
]

# RIFF is NOT in _IMAGE_MAGIC_BYTES because it also prefixes WAV files.
# This check is done separately in _validate_audio_upload below.


def _is_hallucination(heard: str, language: str) -> bool:
    """Return True when the transcription is clearly in the wrong script.

    Only applied when the *expected* language is CJK (Cantonese / Mandarin).
    A result is considered a hallucination when it contains no CJK characters
    at all but does contain characters from a clearly unrelated script.
    """
    if not heard or not language:
        return False
    lang = language.strip().lower()
    if lang not in _CJK_LANGUAGES:
        return False
    text = heard.strip()
    if not text or len(text) < 2:
        return False
    if _CJK_RE.search(text):
        return False   # contains expected CJK characters — not a hallucination
    # No CJK found; check for foreign-script pollution
    if _THAI_RE.search(text) or _ARAB_RE.search(text) or _CYR_RE.search(text):
        return True
    # Korean Hangul output when expecting Cantonese/Mandarin is a Cloudflare
    # Whisper bug (yue language token sometimes maps to Korean in turbo model).
    if _HANGUL_RE.search(text):
        return True
    # Repeated-syllable loops (e.g. "ndo ndo ndo ndo") are a Whisper hallucination
    # pattern on short / near-silent audio.
    if _REPEAT_RE.search(text):
        return True
    return False


def _validate_audio_upload(filename: str, audio_bytes: bytes) -> str | None:
    """Return an error message if the upload is not a valid audio file, or None."""
    import pathlib
    ext = pathlib.Path(filename).suffix.lower() if filename else ""
    if ext in _INVALID_AUDIO_EXTENSIONS:
        return f"Uploaded file \"{filename}\" is not an audio file (.{ext.lstrip('.')}).*"
    for magic, label in _IMAGE_MAGIC_BYTES:
        if audio_bytes.startswith(magic):
            return f"Uploaded file appears to be a {label}, not an audio recording."
    # RIFF header is shared by WAV (bytes 8-11 = b"WAVE") and WebP (bytes 8-11 = b"WEBP").
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WEBP":
        return "Uploaded file appears to be a WebP image, not an audio recording."
    if ext and ext not in {".webm", ".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".oga"}:
        return f"Unsupported audio format \"{ext}\". Please upload a WebM, MP3, MP4, M4A, OGG, or WAV file."
    return None


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


def _huggingface_token() -> str:
    return (
        os.getenv("HUGGINGFACE_API_TOKEN", "").strip()
        or os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGING_FACE_HUB_TOKEN", "").strip()
    )


def _huggingface_enabled() -> bool:
    return bool(_huggingface_token())


def _openai_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _cf_enabled() -> bool:
    return bool(
        os.getenv("CLOUDFLARE_AI_API_TOKEN", "").strip()
        and (
            os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
            or os.getenv("CF_ACCOUNT_ID", "").strip()
        )
    )


def _default_model_for_provider(provider: str) -> str:
    if provider == "huggingface":
        return DEFAULT_HUGGINGFACE_MODEL
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    if provider == "cloudflare":
        return "@cf/openai/whisper"
    return DEFAULT_GROQ_MODEL


def _provider_enabled(provider: str) -> bool:
    if provider == "groq":
        return _groq_enabled()
    if provider == "huggingface":
        return _huggingface_enabled()
    if provider == "openai":
        return _openai_enabled()
    if provider == "cloudflare":
        return _cf_enabled()
    return False


def _provider_unavailable_detail(provider: str) -> str:
    if provider == "groq":
        return "GROQ_API_KEY not configured — legacy Groq recognition testing unavailable"
    if provider == "huggingface":
        return "HUGGINGFACE_API_TOKEN or HF_TOKEN not configured — hosted Hugging Face recognition testing unavailable"
    if provider == "openai":
        return "OPENAI_API_KEY not configured — OpenAI GPT-4o transcription unavailable"
    if provider == "cloudflare":
        return "CLOUDFLARE_AI_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not configured — Cloudflare Workers AI transcription unavailable"
    return f"Unsupported transcription provider: {provider}"


def _known_model(provider: str, model: str) -> Optional[dict[str, Any]]:
    return next(
        (
            candidate
            for candidate in RECOMMENDED_PRONUNCIATION_MODELS
            if candidate["provider"] == provider and candidate["id"] == model
        ),
        None,
    )


def _model_enabled(model: dict[str, Any]) -> bool:
    if model.get("requires_self_hosting"):
        return False
    return _provider_enabled(model["provider"])


def _model_availability_detail(model: dict[str, Any]) -> Optional[str]:
    if model.get("requires_self_hosting"):
        return model.get("availability_detail") or "Model requires a separate deployed inference endpoint"
    if not _provider_enabled(model["provider"]):
        return _provider_unavailable_detail(model["provider"])
    return None


def _available_pronunciation_models() -> list[dict[str, Any]]:
    return [
        {
            **model,
            "enabled": _model_enabled(model),
            "availability": _model_availability_detail(model),
        }
        for model in RECOMMENDED_PRONUNCIATION_MODELS
    ]


def _resolve_provider(provider: str) -> str:
    normalized = (provider or DEFAULT_TRANSCRIPTION_PROVIDER).strip().lower()
    if not normalized:
        return DEFAULT_TRANSCRIPTION_PROVIDER
    return PROVIDER_ALIASES.get(normalized, normalized)


def _resolve_model(model: str, provider: str) -> str:
    return (model or "").strip() or _default_model_for_provider(provider)


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
        print(f"[Pronunciation] → Groq  model={model}  file={tmp_path}  language=yue  size={len(audio_bytes)}B")
        with open(tmp_path, "rb") as file_handle:
            transcription = client.audio.transcriptions.create(
                file=(f"audio{suffix}", file_handle),
                model=model,
                language="yue",  # always Cantonese
                response_format="verbose_json",
            )

        heard = (getattr(transcription, "text", "") or "").strip()
        print(f"[Pronunciation] ← Groq  heard={heard!r}  segments={len(getattr(transcription, 'segments', []) or [])}")

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


def _content_type_for_suffix(suffix: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }.get(suffix, "application/octet-stream")


async def _transcribe_with_openai(
    audio_bytes: bytes,
    suffix: str,
    model: str,
) -> tuple[str, float]:
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '').strip()}",
    }
    files = {
        "file": (f"audio{suffix}", audio_bytes, _content_type_for_suffix(suffix)),
    }
    data = {
        "model": model,
        "language": "yue",  # always Cantonese
    }

    print(f"[Pronunciation] → OpenAI  model={model}  suffix={suffix}  language=yue  size={len(audio_bytes)}B")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        print(f"[Pronunciation] ✗ OpenAI  status={exc.response.status_code}  detail={detail[:120]}")
        raise RuntimeError(f"OpenAI transcription unavailable: {detail}") from exc

    payload = response.json()
    heard = str(payload.get("text") or "").strip()
    print(f"[Pronunciation] ← OpenAI  status={response.status_code}  heard={heard!r}")

    confidence: float = 0.0
    segments = payload.get("segments") or []
    if segments:
        import math

        confidence = round(min(1.0, math.exp(_get_segment_avg_logprob(segments[0]))), 3)

    return heard, confidence


async def _transcribe_with_huggingface(
    audio_bytes: bytes,
    suffix: str,
    model: str,
    language: str = "",
) -> tuple[str, float]:
    token = _huggingface_token()
    content_type = _content_type_for_suffix(suffix)
    resolved_lang = (language or "").strip().lower() or "yue"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    print(f"[Pronunciation] → HuggingFace  url={url}  content-type={content_type}  language={resolved_lang}  size={len(audio_bytes)}B")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                headers=headers,
                content=audio_bytes,
                params={"language": resolved_lang},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"[Pronunciation] ✗ HuggingFace  status={exc.response.status_code}  body={exc.response.text[:200]}")
        if exc.response.status_code == 400 and resolved_lang:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        url,
                        headers=headers,
                        content=audio_bytes,
                    )
                    response.raise_for_status()
            except httpx.HTTPStatusError as fallback_exc:
                detail = fallback_exc.response.text.strip() or str(fallback_exc)
                if "not support image input" in detail or "image" in detail.lower():
                    raise RuntimeError(
                        "Hugging Face received non-audio data (possibly an image file). "
                        "Please upload an audio recording."
                    ) from fallback_exc
                raise RuntimeError(
                    f"Hugging Face transcription unavailable: {fallback_exc}"
                ) from fallback_exc
        else:
            detail = exc.response.text.strip() or str(exc)
            if "not support image input" in detail or "image" in detail.lower():
                raise RuntimeError(
                    "Hugging Face received non-audio data (possibly an image file). "
                    "Please upload an audio recording."
                ) from exc
            raise RuntimeError(
                f"Hugging Face transcription unavailable: {exc}"
            ) from exc

    payload = response.json()
    if isinstance(payload, dict):
        if payload.get("error"):
            raise RuntimeError(f"Hugging Face transcription unavailable: {payload['error']}")
        heard = str(payload.get("text", "") or "").strip()
    else:
        heard = str(payload or "").strip()
    print(f"[Pronunciation] ← HuggingFace  status={response.status_code}  heard={heard!r}")

    return heard, 0.0


# Models that accept the richer JSON input (audio as base64, language param, vad_filter, etc.).
# @cf/openai/whisper only accepts raw binary with no language control.
_CF_JSON_INPUT_MODELS = {
    "@cf/openai/whisper-large-v3-turbo",
}


async def _transcribe_with_cloudflare(
    audio_bytes: bytes,
    suffix: str,
    model: str,
    language: str = "",
) -> tuple[str, float]:
    account_id = (
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        or os.getenv("CF_ACCOUNT_ID", "").strip()
    )
    api_token = os.getenv("CLOUDFLARE_AI_API_TOKEN", "").strip()

    if not account_id or not api_token:
        raise RuntimeError("Cloudflare Workers AI is not configured (missing CLOUDFLARE_ACCOUNT_ID/CF_ACCOUNT_ID or CLOUDFLARE_AI_API_TOKEN)")

    cf_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

    # whisper-large-v3-turbo and similar models accept JSON with base64 audio and
    # an explicit language hint — this is the only way to force Cantonese (yue)
    # and enable VAD to suppress hallucinations on short/silent clips.
    use_json = model in _CF_JSON_INPUT_MODELS
    if use_json:
        import base64 as _b64
        resolved_lang = (language or "").strip() or "yue"
        payload = {
            "audio": _b64.b64encode(audio_bytes).decode(),
            "language": resolved_lang,
            "vad_filter": True,
            "no_speech_threshold": 0.6,
            # Prevents Whisper from conditioning on its own hallucinated output,
            # which causes repeated-syllable loops (e.g. "ndo ndo ndo").
            "condition_on_previous_text": False,
        }
        print(f"[Pronunciation] → Cloudflare  url={cf_url}  format=json  language={resolved_lang}  size={len(audio_bytes)}B")
    else:
        content_type = _content_type_for_suffix(suffix)
        print(f"[Pronunciation] → Cloudflare  url={cf_url}  content-type={content_type}  size={len(audio_bytes)}B")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            if use_json:
                response = await client.post(
                    cf_url,
                    headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                    json=payload,
                )
            else:
                response = await client.post(
                    cf_url,
                    headers={
                        "Authorization": f"Bearer {api_token}",
                        "Content-Type": _content_type_for_suffix(suffix),
                    },
                    content=audio_bytes,
                )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        print(f"[Pronunciation] ✗ Cloudflare  status={exc.response.status_code}  detail={detail[:200]}")
        raise RuntimeError(f"Cloudflare AI transcription unavailable: {detail}") from exc

    payload = response.json()
    if not payload.get("success"):
        errors = payload.get("errors", [])
        error_detail = errors[0].get("message", str(errors)) if errors else str(payload)
        raise RuntimeError(f"Cloudflare AI transcription failed: {error_detail}")

    result = payload.get("result", {}) or {}
    heard = str(result.get("text", "") or "").strip()
    print(f"[Pronunciation] ← Cloudflare  status={response.status_code}  heard={heard!r}")
    return heard, 0.0


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
    resolved_model = _resolve_model(model, resolved_provider)

    if resolved_provider not in SUPPORTED_TRANSCRIPTION_PROVIDERS:
        return _build_unavailable_response(
            resolved_provider,
            resolved_model,
            f"Unsupported transcription provider: {resolved_provider}",
            status_code=400,
        )

    if not _provider_enabled(resolved_provider):
        return _build_unavailable_response(
            resolved_provider,
            resolved_model,
            _provider_unavailable_detail(resolved_provider),
        )

    known_model = _known_model(resolved_provider, resolved_model)
    if known_model and not _model_enabled(known_model):
        return _build_unavailable_response(
            resolved_provider,
            resolved_model,
            _model_availability_detail(known_model) or "Selected model is not available",
        )

    audio_bytes = await audio.read()
    original_name = getattr(audio, "filename", "") or ""

    validation_error = _validate_audio_upload(original_name, audio_bytes)
    if validation_error:
        return JSONResponse(
            status_code=400,
            content={
                "detail": validation_error,
                "provider": resolved_provider,
                "model": resolved_model,
            },
        )

    suffix = ".webm"
    if original_name.endswith(".mp4"):
        suffix = ".mp4"
    elif original_name.endswith(".m4a"):
        suffix = ".m4a"
    elif original_name.endswith(".mp3"):
        suffix = ".mp3"
    elif original_name.endswith(".ogg"):
        suffix = ".ogg"
    elif original_name.endswith(".wav"):
        suffix = ".wav"

    started_at = perf_counter()
    print(f"[Pronunciation] dispatch  provider={resolved_provider}  model={resolved_model}  suffix={suffix}  target={word_cantonese!r}  language={language}")
    try:
        if resolved_provider == "groq":
            heard, confidence = await _transcribe_with_groq(
                audio_bytes=audio_bytes,
                suffix=suffix,
                model=resolved_model,
            )
        elif resolved_provider == "openai":
            heard, confidence = await _transcribe_with_openai(
                audio_bytes=audio_bytes,
                suffix=suffix,
                model=resolved_model,
            )
        elif resolved_provider == "cloudflare":
            heard, confidence = await _transcribe_with_cloudflare(
                audio_bytes=audio_bytes,
                suffix=suffix,
                model=resolved_model,
                language=language,
            )
        else:
            heard, confidence = await _transcribe_with_huggingface(
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

    # Discard hallucinations (wrong-script output from language auto-detection).
    # Keep the raw value in a separate field so the UI can surface it for debugging.
    raw_heard = heard
    if _is_hallucination(heard, language):
        print(f"[Pronunciation] Discarding hallucination ({resolved_provider}/{resolved_model}): {heard!r}")
        heard = ""

    target = (word_cantonese or "").strip()
    result = _score(heard, target) if target else None

    response: dict[str, Any] = {
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
    if raw_heard != heard:
        response["raw_heard"] = raw_heard
        response["hallucination_discarded"] = True
    return response

# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/pronunciation-models")
async def get_pronunciation_models():
    """List configured speech-to-text models that can be tested from the speech tester."""
    available = _available_pronunciation_models()
    enabled = [m for m in available if m.get("enabled")]

    # Pick the best default: first enabled model, or fall back to openai
    if enabled:
        effective_default_provider = enabled[0]["provider"]
        effective_default_model = enabled[0]["id"]
    else:
        effective_default_provider = DEFAULT_TRANSCRIPTION_PROVIDER
        effective_default_model = DEFAULT_OPENAI_MODEL

    return {
        "default_provider": effective_default_provider,
        "default_model": effective_default_model,
        "provider_defaults": {
            "groq": DEFAULT_GROQ_MODEL,
            "huggingface": DEFAULT_HUGGINGFACE_MODEL,
            "openai": DEFAULT_OPENAI_MODEL,
            "cloudflare": "@cf/openai/whisper",
        },
        "models": available,
    }

@router.post("/validate-pronunciation")
async def validate_pronunciation(
    audio: UploadFile = File(...),
    word_cantonese: str = Form(default=""),
    jyutping: str = Form(default=""),
    word_id: str = Form(default=""),
    provider: str = Form(default=DEFAULT_TRANSCRIPTION_PROVIDER),
    model: str = Form(default=DEFAULT_OPENAI_MODEL),
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
    model: str = Form(default=DEFAULT_OPENAI_MODEL),
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
