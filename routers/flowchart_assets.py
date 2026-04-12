"""
Flowchart Assets — custom arrowhead images uploaded by users.
Stored in R2 under the 'flowchart-assets/' prefix.
MongoDB collection: flowchart_assets
The /serve endpoint proxies the file directly from R2 so the URL is stable.
"""

import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from auth import verify_token
from database import get_db
from services.r2_service import R2Service

router = APIRouter(
    prefix="/api/flowchart-assets",
    tags=["flowchart-assets"],
    dependencies=[Depends(verify_token)],
)

ALLOWED = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@router.post("/upload")
async def upload_asset(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "img")[1].lower() or ".png"
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB")

    r2 = R2Service()
    r2_key = await asyncio.to_thread(_upload_with_key, r2, content, ext, file.content_type or "image/png")

    file_id = r2_key.split("/")[-1].rsplit(".", 1)[0]
    serve_url = f"{BASE_URL}/api/flowchart-assets/{file_id}/serve"

    db = get_db()
    await db.flowchart_assets.insert_one({
        "file_id": file_id,
        "filename": file.filename or f"arrow{ext}",
        "r2_key": r2_key,
        "uploaded_at": datetime.utcnow(),
    })

    return {"file_id": file_id, "url": serve_url, "filename": file.filename or f"arrow{ext}"}


@router.get("/list")
async def list_assets():
    db = get_db()
    docs = []
    async for doc in db.flowchart_assets.find({}, {"_id": 0}):
        docs.append({
            "file_id": doc["file_id"],
            "filename": doc.get("filename", doc["file_id"]),
            "url": f"{BASE_URL}/api/flowchart-assets/{doc['file_id']}/serve",
        })
    return docs


@router.get("/{file_id}/serve")
async def serve_asset(file_id: str):
    db = get_db()
    doc = await db.flowchart_assets.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Asset not found")

    r2 = R2Service()
    data = await r2.download_file(doc["r2_key"])
    ext = os.path.splitext(doc["r2_key"])[1].lower()
    content_type = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/{file_id}")
async def delete_asset(file_id: str):
    db = get_db()
    doc = await db.flowchart_assets.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Asset not found")

    r2 = R2Service()
    await r2.delete_file(doc["r2_key"])
    await db.flowchart_assets.delete_one({"file_id": file_id})
    return {"status": "deleted"}


def _upload_with_key(r2: R2Service, content: bytes, ext: str, content_type: str) -> str:
    import uuid
    file_id = str(uuid.uuid4())
    key = f"flowchart-assets/{file_id}{ext}"
    r2._put_object(key, content, content_type)
    return key
