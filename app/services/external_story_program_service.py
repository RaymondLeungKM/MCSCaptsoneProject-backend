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
import psycopg2
from psycopg2.extras import RealDictCursor


class ExternalStoryProgramError(RuntimeError):
    """Raised when invoking the external story program fails."""


@dataclass
class ExternalStoryInvocationResult:
    story_text: str
    story_text_ssml: str
    vocab_used: str
    audio_url: str
    audio_filename: str
    external_audio_path: str
    external_story_id: Optional[str]
    llm_model: Optional[str]
    tts_provider: Optional[str]
    voice_name: Optional[str]
    generated_at: datetime


class ExternalStoryProgramService:
    """Run the external story program as a subprocess and normalize outputs."""

    STORY_BLOCK_PATTERN = re.compile(r"Generated Story:\s*(.*?)\n={10,}", re.DOTALL)
    SSML_BLOCK_PATTERN = re.compile(r"Generated SSML:\s*(.*?)\n={10,}", re.DOTALL)
    AUDIO_PATH_PATTERN = re.compile(r"Success!\s*Audio saved to:\s*(.+)")
    STORY_ID_PATTERN = re.compile(r"Story record saved to database \(ID:\s*([^)]+)\)")
    MODEL_PATTERN = re.compile(r"Using model:\s*(.+)")
    TTS_PROVIDER_PATTERN = re.compile(r"Using (Google Cloud TTS|AWS Polly|Azure TTS)\.\.\.")
    VOICE_NAME_PATTERN = re.compile(r"Voice used:\s*(.+)")

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

            # Avoid PATH-dependent resolution when backend runs inside a venv
            # that may miss standalone dependencies (e.g. boto3 for AWS Polly).
            system_python = Path("/usr/bin/python3")
            if system_python.is_file():
                return str(system_python)

        return configured_bin



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
    def _extract_story_ssml(cls, stdout: str) -> str:
        match = cls.SSML_BLOCK_PATTERN.search(stdout)
        if not match:
            return ""
        return match.group(1).strip()

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

    def _run_program(
        self,
        program_dir: Path,
        env: dict[str, str],
        command: list[str],
        timeout_seconds: int,
    ) -> tuple[str, str]:
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
            python_bin = command[0] if command else "python3"
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

        return stdout, stderr

    def _copy_external_audio(self, external_audio_path: Path, prefix: str) -> tuple[str, str]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        copied_filename = f"{prefix}_{timestamp}_{external_audio_path.name}"
        copied_path = self.backend_audio_dir / copied_filename
        shutil.copy2(external_audio_path, copied_path)
        return copied_filename, str(copied_path)

    def invoke(self, child_id: str, gen_date: str, story_category: str) -> ExternalStoryInvocationResult:
        program_dir = self._resolve_program_dir()
        python_bin = self._resolve_python_bin(program_dir)
        timeout_seconds = max(30, int(settings.EXTERNAL_STORY_TIMEOUT_SECONDS))
        env = os.environ.copy()

        command = [python_bin, str(program_dir / "main.py"), child_id, gen_date, story_category]

        stdout, _ = self._run_program(
            program_dir=program_dir,
            env=env,
            command=command,
            timeout_seconds=timeout_seconds,
        )

        # Try to extract story text from stdout first. If it's not present
        # but the external program printed a DB record id, fetch the story
        # from the database instead.
        external_story_id = self._extract_optional(self.STORY_ID_PATTERN, stdout)
        vocab_from_db = None
        llm_model_from_db = None
        try:
            story_text = self._extract_story_text(stdout)
            story_text_ssml = self._extract_story_ssml(stdout)
            external_audio_path = self._extract_audio_path(stdout, program_dir)
        except ExternalStoryProgramError:
            if not external_story_id:
                # No story block and no record id — cannot continue
                raise

            # Query the backend DB for the generated story record
            story_text = ""
            story_text_ssml = ""
            external_audio_path = None
            try:
                # Connect using sync psycopg2 to the configured DATABASE_URL
                with psycopg2.connect(settings.DATABASE_URL) as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(
                            "SELECT story_text, story_text_ssml, audio_filename, vocab_used, story_generate_model_story1 "
                            "FROM generated_stories_log WHERE story_id = %s",
                            (external_story_id,)
                        )
                        row = cur.fetchone()
                        if row:
                            story_text = row.get("story_text") or ""
                            story_text_ssml = row.get("story_text_ssml") or ""
                            audio_filename = row.get("audio_filename") or ""
                            vocab_from_db = row.get("vocab_used") or ""
                            llm_model_from_db = row.get("story_generate_model_story1") or None
                            # Resolve audio path: try absolute, then program dir, then audio-output,
                            # then try the sibling story-generation-output/audio-output directory
                            candidate = Path(audio_filename)
                            if not candidate.is_absolute():
                                candidate = (program_dir / audio_filename).resolve()

                            if not candidate.is_file():
                                candidate = (program_dir / "audio-output" / audio_filename).resolve()

                            if not candidate.is_file():
                                # external program may write to a configured output dir (project root or absolute)
                                configured_out = (settings.EXTERNAL_STORY_OUTPUT_DIR or "").strip() or "../story-generation-output"
                                out_dir = Path(configured_out).expanduser()
                                if not out_dir.is_absolute():
                                    out_dir = (program_dir / out_dir).resolve()

                                candidate = (out_dir / "audio-output" / audio_filename).resolve()

                            if not candidate.is_file():
                                # also try the output dir root (in case audio_filename includes subpath)
                                configured_out = (settings.EXTERNAL_STORY_OUTPUT_DIR or "").strip() or "../story-generation-output"
                                out_dir = Path(configured_out).expanduser()
                                if not out_dir.is_absolute():
                                    out_dir = (program_dir / out_dir).resolve()

                                candidate = (out_dir / audio_filename).resolve()

                            if candidate.is_file():
                                external_audio_path = candidate
                            else:
                                external_audio_path = None
                        else:
                            raise ExternalStoryProgramError(
                                f"External story record {external_story_id} not found in database."
                            )
            except Exception as db_err:
                raise ExternalStoryProgramError(
                    f"Failed to fetch story from DB for id {external_story_id}: {db_err}"
                ) from db_err
        llm_model = self._extract_optional(self.MODEL_PATTERN, stdout) or llm_model_from_db
        tts_provider_label = self._extract_optional(self.TTS_PROVIDER_PATTERN, stdout)
        tts_provider = self._provider_alias(tts_provider_label)
        voice_name = self._extract_optional(self.VOICE_NAME_PATTERN, stdout)

        if not external_audio_path:
            raise ExternalStoryProgramError("External audio file path not found in stdout or database record.")

        copied_filename, _ = self._copy_external_audio(external_audio_path, "external_story")

        # Extract vocab_used from the stdout or DB result if available
        try:
            vocab_used = self._extract_optional(re.compile(r"Vocab used:\s*(.+)"), stdout) or vocab_from_db or ""
        except Exception:
            vocab_used = ""
        
        return ExternalStoryInvocationResult(
            story_text=story_text,
            story_text_ssml=story_text_ssml,
            vocab_used=vocab_used,
            audio_url=f"/uploads/audio/{copied_filename}",
            audio_filename=copied_filename,
            external_audio_path=str(external_audio_path),
            external_story_id=external_story_id,
            llm_model=llm_model,
            tts_provider=tts_provider,
            voice_name=voice_name,
            generated_at=datetime.now(timezone.utc),
        )

    def invoke_from_story_text(self, story_text: str) -> ExternalStoryInvocationResult:
        normalized_story_text = (story_text or "").strip()
        if not normalized_story_text:
            raise ExternalStoryProgramError("Story text is required to generate SSML and audio.")

        program_dir = self._resolve_program_dir()
        python_bin = self._resolve_python_bin(program_dir)
        timeout_seconds = max(30, int(settings.EXTERNAL_STORY_TIMEOUT_SECONDS))
        env = os.environ.copy()
        env["STORY_PROGRAM_STORY_TEXT"] = normalized_story_text

        command = [python_bin, str(program_dir / "main.py")]

        stdout, _ = self._run_program(
            program_dir=program_dir,
            env=env,
            command=command,
            timeout_seconds=timeout_seconds,
        )

        story_text_ssml = self._extract_story_ssml(stdout)
        external_audio_path = self._extract_audio_path(stdout, program_dir)
        llm_model = self._extract_optional(self.MODEL_PATTERN, stdout)
        tts_provider_label = self._extract_optional(self.TTS_PROVIDER_PATTERN, stdout)
        tts_provider = self._provider_alias(tts_provider_label)
        voice_name = self._extract_optional(self.VOICE_NAME_PATTERN, stdout)
        copied_filename, _ = self._copy_external_audio(external_audio_path, "curated_story")

        return ExternalStoryInvocationResult(
            story_text=normalized_story_text,
            story_text_ssml=story_text_ssml,
            vocab_used="",
            audio_url=f"/uploads/audio/{copied_filename}",
            audio_filename=copied_filename,
            external_audio_path=str(external_audio_path),
            external_story_id=None,
            llm_model=llm_model,
            tts_provider=tts_provider,
            voice_name=voice_name,
            generated_at=datetime.now(timezone.utc),
        )


external_story_program_service = ExternalStoryProgramService()
