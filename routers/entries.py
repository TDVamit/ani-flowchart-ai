from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from models.daily_entry import DailyEntry, AudioRecording, UploadedDocument, TranscriptSource
from auth import verify_token
from datetime import date, datetime
from bson import ObjectId

router = APIRouter(prefix="/api/entries", tags=["entries"], dependencies=[Depends(verify_token)])


@router.post("/")
async def create_entry(entry: DailyEntry):
    db = get_db()
    entry_dict = entry.model_dump(by_alias=True, exclude={"id"})
    entry_dict["entry_date"] = entry_dict["entry_date"].isoformat()
    result = await db.daily_entries.insert_one(entry_dict)
    return {"id": str(result.inserted_id)}


@router.get("/project/{project_id}")
async def list_entries(project_id: str):
    db = get_db()
    cursor = db.daily_entries.find({"project_id": project_id}).sort("entry_date", -1)
    entries = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        entries.append(doc)
    return entries


@router.get("/{entry_id}")
async def get_entry(entry_id: str):
    db = get_db()
    doc = await db.daily_entries.find_one({"_id": ObjectId(entry_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Entry not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.put("/{entry_id}")
async def update_entry(entry_id: str, updates: dict):
    db = get_db()
    updates["updated_at"] = datetime.utcnow()
    await db.daily_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {"$set": updates}
    )
    return {"status": "updated"}


@router.post("/{entry_id}/add-recording")
async def add_recording(entry_id: str, recording: AudioRecording):
    db = get_db()
    await db.daily_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {
            "$push": {"audio_recordings": recording.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return {"status": "added"}


@router.put("/{entry_id}/update-transcript")
async def update_transcript(entry_id: str, body: dict):
    """Update a recording's transcript (from Whisper result or manual input)."""
    recording_index = body.get("recording_index", 0)
    transcript = body.get("transcript", "")
    source = body.get("source", "manual")

    db = get_db()
    field_prefix = f"audio_recordings.{recording_index}"
    await db.daily_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {"$set": {
            f"{field_prefix}.transcript": transcript,
            f"{field_prefix}.transcript_source": source,
            "updated_at": datetime.utcnow()
        }}
    )
    return {"status": "updated"}


@router.post("/{entry_id}/add-document")
async def add_document(entry_id: str, document: UploadedDocument):
    db = get_db()
    await db.daily_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {
            "$push": {"uploaded_documents": document.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return {"status": "added"}
