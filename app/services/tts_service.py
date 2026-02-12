"""
Text-to-Speech service for Cantonese/English audio generation.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from gtts import gTTS


class TTSService:
    """Generate audio files and return public URLs for playback."""

    def __init__(self) -> None:
        self.audio_dir = Path("uploads/audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)  # strip SSML/HTML tags
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _estimate_duration_seconds(text: str, speech_rate: float = 0.9) -> int:
        # Rough estimate for child-friendly pace.
        # ~2.8 chars/sec at 0.9 rate for CJK-heavy content.
        cps = 2.8 * max(0.5, min(2.0, speech_rate))
        return max(1, int(len(text) / cps))

    @staticmethod
    def _resolve_language_candidates(language: str) -> list[tuple[str, Optional[str]]]:
        lang = (language or "cantonese").lower()

        if lang in {"cantonese", "yue", "zh-hk"}:
            return [("yue", "com.hk"), ("zh-tw", "com.tw"), ("zh-cn", "com")]
        if lang in {"english", "en"}:
            return [("en", "com"), ("en", "co.uk")]
        if lang in {"mandarin", "zh", "zh-cn", "zh-tw"}:
            return [("zh-tw", "com.tw"), ("zh-cn", "com")]

        return [("en", "com")]

    def _synthesize_mp3(self, text: str, language: str, output_path: Path) -> None:
        candidates = self._resolve_language_candidates(language)
        last_error: Exception | None = None

        for lang_code, tld in candidates:
            try:
                tts = gTTS(text=text, lang=lang_code, tld=tld or "com")
                tts.save(str(output_path))
                return
            except Exception as error:  # pragma: no cover - provider errors vary by env
                last_error = error
                continue

        if last_error:
            raise last_error

    def generate_audio(
        self,
        text: str,
        *,
        language: str = "cantonese",
        voice_name: Optional[str] = None,
        speech_rate: float = 0.9,
        filename_prefix: str = "tts",
    ) -> Dict[str, Any]:
        cleaned_text = self._clean_text(text)
        if not cleaned_text:
            raise ValueError("Text cannot be empty for audio generation")

        file_id = uuid.uuid4().hex
        filename = f"{filename_prefix}_{file_id}.mp3"
        output_path = self.audio_dir / filename

        self._synthesize_mp3(cleaned_text, language, output_path)

        return {
            "audio_url": f"/uploads/audio/{filename}",
            "audio_filename": filename,
            "audio_duration_seconds": self._estimate_duration_seconds(cleaned_text, speech_rate),
            "audio_generate_provider": "gtts",
            "audio_generate_voice_name": voice_name or language,
        }


tts_service = TTSService()
