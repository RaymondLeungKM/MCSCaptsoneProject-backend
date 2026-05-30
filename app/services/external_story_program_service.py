"""
Adapter service for invoking the external story-generation-program.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings


class ExternalStoryProgramError(RuntimeError):
    """Raised when invoking the external story program fails."""


@dataclass
class ExternalStoryInvocationResult:
    story_text: str
    vocab_used: str
    audio_url: str
    audio_filename: str
    external_audio_path: str
    external_story_id: Optional[str]
    llm_model: Optional[str]
    tts_provider: Optional[str]
    generated_at: datetime


class ExternalStoryProgramService:
    """Run the external story program as a subprocess and normalize outputs."""

    STORY_BLOCK_PATTERN = re.compile(r"Generated Story:\s*(.*?)\n={10,}", re.DOTALL)
    AUDIO_PATH_PATTERN = re.compile(r"Success!\s*Audio saved to:\s*(.+)")
    STORY_ID_PATTERN = re.compile(r"Story record saved to database \(ID:\s*([^)]+)\)")
    MODEL_PATTERN = re.compile(r"Using model:\s*(.+)")
    TTS_PROVIDER_PATTERN = re.compile(r"Using (Google Cloud TTS|AWS Polly|Azure TTS)\.\.\.")

    def __init__(self) -> None:
        self.backend_audio_dir = Path("uploads/audio")
        self.backend_audio_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _backend_root() -> Path:
        # app/services -> app -> backend root
        return Path(__file__).resolve().parents[2]

    def _resolve_program_dir(self) -> Path:
        configured_dir = (settings.EXTERNAL_STORY_PROGRAM_DIR or "").strip() or "../story-generation-program"

        program_dir = Path(configured_dir).expanduser()
        if not program_dir.is_absolute():
            program_dir = (self._backend_root() / program_dir).resolve()

        if not (program_dir / "main.py").is_file():
            raise ExternalStoryProgramError(
                f"External story program not found at '{program_dir}'. "
                "Set EXTERNAL_STORY_PROGRAM_DIR correctly."
            )

        return program_dir

    def availability_error(self) -> Optional[str]:
        """Return a human-readable availability error, if any."""
        try:
            self._resolve_program_dir()
        except ExternalStoryProgramError as error:
            return str(error)

        return None

    @staticmethod
    def _resolve_python_bin(program_dir: Path) -> str:
        configured_bin = (settings.EXTERNAL_STORY_PYTHON_BIN or "").strip() or "python3"

        # When the backend runs inside its own virtualenv, a generic `python3`
        # may resolve to that backend interpreter instead of the story program's
        # environment. Prefer the story program venv automatically when present.
        if configured_bin in {"python", "python3"}:
            for candidate in (
                program_dir / "venv" / "bin" / "python",
                program_dir / "venv" / "bin" / "python3",
            ):
                if candidate.is_file():
                    return str(candidate)

        return configured_bin

    @staticmethod
    def _sanitize_words(vocab_words: list[str]) -> list[str]:
        words = [w.strip() for w in vocab_words if isinstance(w, str) and w.strip()]
        if not words:
            raise ExternalStoryProgramError("At least one non-empty vocabulary word is required.")
        return words

    @classmethod
    def _extract_story_text(cls, stdout: str) -> str:
        story_match = cls.STORY_BLOCK_PATTERN.search(stdout)
        if story_match:
            return story_match.group(1).strip()

        fallback_match = re.search(
            r"Generated Story:\s*(.*?)\nSaving audio file\.\.\.",
            stdout,
            re.DOTALL,
        )
        if fallback_match:
            return fallback_match.group(1).strip()

        raise ExternalStoryProgramError(
            "Story generation succeeded but story text could not be parsed from external output."
        )

    @classmethod
    def _extract_audio_path(cls, stdout: str, program_dir: Path) -> Path:
        match = cls.AUDIO_PATH_PATTERN.search(stdout)
        if not match:
            raise ExternalStoryProgramError(
                "Audio generation succeeded but output file path was not found in external output."
            )

        raw_path = match.group(1).strip()
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (program_dir / candidate).resolve()

        if not candidate.is_file():
            raise ExternalStoryProgramError(
                f"External audio file was reported but not found: {candidate}"
            )
        return candidate

    @staticmethod
    def _extract_optional(pattern: re.Pattern, stdout: str) -> Optional[str]:
        match = pattern.search(stdout)
        if not match:
            return None
        value = match.group(1).strip()
        return value or None

    @staticmethod
    def _provider_alias(provider_label: Optional[str]) -> Optional[str]:
        if not provider_label:
            return None
        provider_map = {
            "AWS Polly": "aws",
            "Google Cloud TTS": "google",
            "Azure TTS": "azure",
        }
        return provider_map.get(provider_label)

    def invoke(self, vocab_words: list[str]) -> ExternalStoryInvocationResult:
        words = self._sanitize_words(vocab_words)
        vocab_csv = ", ".join(words)
        program_dir = self._resolve_program_dir()
        python_bin = self._resolve_python_bin(program_dir)
        timeout_seconds = max(30, int(settings.EXTERNAL_STORY_TIMEOUT_SECONDS))
        env = os.environ.copy()
        env["STORY_PROGRAM_SKIP_DB_INSERT"] = "1"

        command = [python_bin, str(program_dir / "main.py"), vocab_csv]

        try:
            completed = subprocess.run(
                command,
                cwd=str(program_dir),
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as error:
            raise ExternalStoryProgramError(
                f"Python executable '{python_bin}' was not found. "
                "Set EXTERNAL_STORY_PYTHON_BIN to a valid interpreter."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ExternalStoryProgramError(
                f"External story program timed out after {timeout_seconds} seconds."
            ) from error

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        if completed.returncode != 0:
            stderr_tail = "\n".join(stderr.strip().splitlines()[-20:]).strip()
            stdout_tail = "\n".join(stdout.strip().splitlines()[-20:]).strip()
            detail = stderr_tail or stdout_tail or "No output captured."
            raise ExternalStoryProgramError(
                f"External story program failed with exit code {completed.returncode}. {detail}"
            )

        story_text = self._extract_story_text(stdout)
        external_audio_path = self._extract_audio_path(stdout, program_dir)
        external_story_id = self._extract_optional(self.STORY_ID_PATTERN, stdout)
        llm_model = self._extract_optional(self.MODEL_PATTERN, stdout)
        tts_provider_label = self._extract_optional(self.TTS_PROVIDER_PATTERN, stdout)
        tts_provider = self._provider_alias(tts_provider_label)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        copied_filename = f"external_story_{timestamp}_{external_audio_path.name}"
        copied_path = self.backend_audio_dir / copied_filename
        shutil.copy2(external_audio_path, copied_path)

        return ExternalStoryInvocationResult(
            story_text=story_text,
            vocab_used=vocab_csv,
            audio_url=f"/uploads/audio/{copied_filename}",
            audio_filename=copied_filename,
            external_audio_path=str(external_audio_path),
            external_story_id=external_story_id,
            llm_model=llm_model,
            tts_provider=tts_provider,
            generated_at=datetime.now(timezone.utc),
        )


external_story_program_service = ExternalStoryProgramService()
