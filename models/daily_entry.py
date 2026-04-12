from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class TranscriptSource(str, Enum):
    WHISPER = "whisper"
    MANUAL = "manual"


class AudioRecording(BaseModel):
    file_id: str
    original_filename: str
    duration_seconds: Optional[float] = None
    transcript: Optional[str] = None
    transcript_source: Optional[TranscriptSource] = None
    interviewee_name: Optional[str] = None
    interviewee_role: Optional[str] = None
    notes: Optional[str] = None


class UploadedDocument(BaseModel):
    file_id: str
    original_filename: str
    file_type: str
    extracted_text: Optional[str] = None
    user_annotation: Optional[str] = None


class DailyEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    entry_date: date
    week_number: int
    day_number: int

    typed_findings: str = ""
    user_annotations: str = ""
    previous_plan_review: str = ""

    audio_recordings: List[AudioRecording] = []
    uploaded_documents: List[UploadedDocument] = []

    analysis_triggered: bool = False
    analysis_completed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
