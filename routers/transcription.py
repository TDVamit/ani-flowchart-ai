"""
Transcription router.

Two endpoints:
  POST /api/transcription/audio/{file_id}  — transcribe a file already uploaded to R2
  POST /api/transcription/manual           — save a manually typed/pasted transcript

Audio never touches the local disk — it is streamed from R2 into memory, then sent to Whisper.
"""

from fastapi import APIRouter, HTTPException, Body, Depends
from typing import Optional
from services.whisper_service import WhisperService
from services.r2_service import R2Service
from database import get_db
from auth import verify_token
from config import settings

router = APIRouter(prefix="/api/transcription", tags=["transcription"], dependencies=[Depends(verify_token)])


@router.post("/audio/{file_id}")
async def transcribe_from_r2(
    file_id: str,
    language: Optional[str] = Body(None),
    context_prompt: Optional[str] = Body(None),
):
    """
    Transcribe an audio file that has already been uploaded to R2.
    Downloads the file bytes from R2 into memory, sends to Whisper — no local disk I/O.
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Use manual transcription instead."
        )

    db = get_db()
    file_doc = await db.files.find_one({"file_id": file_id})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")

    # Download from R2 into memory (async — runs boto3 in thread pool)
    r2 = R2Service()
    audio_bytes = await r2.download_file(file_doc["r2_key"])

    # Transcribe from bytes (no temp file)
    service = WhisperService()
    result = await service.transcribe_bytes(
        audio_bytes=audio_bytes,
        filename=file_doc["original_filename"],
        language=language,
        prompt=context_prompt,
    )

    return {
        "transcript": result["text"],
        "duration_seconds": result["duration"],
        "source": "whisper",
    }


@router.post("/manual")
async def save_manual_transcript(body: dict):
    """Accept a manually typed or pasted transcript — no API call required."""
    transcript = body.get("transcript", "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript text is required")
    return {
        "transcript": transcript,
        "duration_seconds": None,
        "source": "manual",
    }
