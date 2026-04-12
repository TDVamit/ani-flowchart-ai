"""
Whisper transcription service.
Accepts audio bytes (downloaded from R2) and sends to OpenAI Whisper API.
No local disk I/O — everything stays in memory.
"""

import io
import os
import openai
from typing import Optional
from config import settings


class WhisperService:

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.whisper_model  # "whisper-1"

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> dict:
        """
        Transcribe audio from raw bytes (downloaded from R2).

        Args:
            audio_bytes: raw audio file content
            filename: original filename including extension (e.g. "interview.m4a")
                      — Whisper uses this to detect the format
            language: ISO 639-1 code hint e.g. "en", "hi" — improves accuracy
            prompt: optional context to guide transcription style

        Returns:
            {"text": str, "duration": float|None, "segments": list}
        """
        supported = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
        ext = os.path.splitext(filename)[1].lower()
        if ext not in supported:
            raise ValueError(f"Unsupported audio format: {ext}")

        file_obj = io.BytesIO(audio_bytes)
        file_obj.name = filename  # required by openai SDK for format detection

        kwargs: dict = {
            "model": self.model,
            "file": file_obj,
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt
        else:
            kwargs["prompt"] = "This is an interview about organizational processes and project management."

        response = await self.client.audio.transcriptions.create(**kwargs)

        return {
            "text": response.text,
            "duration": getattr(response, "duration", None),
            "segments": getattr(response, "segments", []),
        }
