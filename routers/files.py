"""
Files router — all uploads go to Cloudflare R2, never local disk.
MongoDB stores only metadata (original filename, R2 key, extracted text, annotation).
All blocking I/O (boto3, pypdf) runs in thread-pool via asyncio.to_thread.
"""

import asyncio
import io
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import verify_token
from config import settings
from database import get_db
from services.r2_service import R2Service

router = APIRouter(prefix="/api/files", tags=["files"], dependencies=[Depends(verify_token)])

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".docx", ".txt", ".csv", ".xlsx",
    ".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg",
}


@router.get("/brief/{project_id}")
async def get_brief_files(project_id: str):
    """Return all files attached to brief fields for a project, grouped by field_key."""
    db = get_db()
    cursor = db.files.find(
        {"project_id": project_id, "field_key": {"$exists": True, "$ne": None}},
        {"_id": 0},
    )
    files = []
    async for doc in cursor:
        doc.pop("_id", None)
        files.append(doc)
    # Group by field_key
    grouped: dict = {}
    for f in files:
        key = f.get("field_key", "")
        grouped.setdefault(key, []).append(f)
    return grouped


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    annotation: Optional[str] = Form(None),
    field_key: Optional[str] = Form(None),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    content = await file.read()

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_file_size_mb}MB limit")

    # Upload to R2 (async — runs boto3 in thread pool)
    r2 = R2Service()
    r2_key = await r2.upload_bytes(
        file_bytes=content,
        filename=file.filename,
        project_id=project_id,
        content_type=file.content_type or "application/octet-stream",
    )

    # Extract text without blocking the event loop
    extracted_text: Optional[str] = None
    if ext == ".pdf":
        extracted_text = await asyncio.to_thread(_extract_pdf_text_from_bytes, content)
    elif ext == ".txt":
        extracted_text = content.decode("utf-8", errors="ignore")

    file_id = r2_key.split("/")[-1].rsplit(".", 1)[0]

    db = get_db()
    file_doc = {
        "file_id": file_id,
        "project_id": project_id,
        "original_filename": file.filename,
        "file_type": ext.lstrip("."),
        "r2_key": r2_key,
        "extracted_text": extracted_text,
        "user_annotation": annotation,
        "field_key": field_key,
        "uploaded_at": datetime.utcnow(),
    }
    await db.files.insert_one(file_doc)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "file_type": ext.lstrip("."),
        "has_extracted_text": extracted_text is not None,
    }


@router.get("/download/{file_id}")
async def get_file_url(file_id: str):
    """Returns a presigned R2 URL valid for 1 hour."""
    db = get_db()
    doc = await db.files.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    r2 = R2Service()
    url = await r2.get_presigned_url(doc["r2_key"], expires_in=3600)
    return {"url": url, "expires_in": 3600}


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    db = get_db()
    doc = await db.files.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    r2 = R2Service()
    await r2.delete_file(doc["r2_key"])
    await db.files.delete_one({"file_id": file_id})
    return {"status": "deleted"}


def _extract_pdf_text_from_bytes(content: bytes) -> Optional[str]:
    """Sync — called via asyncio.to_thread from the async route."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        texts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(texts)
    except Exception:
        return None
