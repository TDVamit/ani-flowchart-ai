"""
Flowcharts router — stores flowchart metas + node/edge data in MongoDB.
"""

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth import verify_token
from database import get_db

router = APIRouter(prefix="/api/flowcharts", tags=["flowcharts"])


class FlowchartCreate(BaseModel):
    name: str


class FlowchartUpdate(BaseModel):
    name: str | None = None
    nodes: list[Any] | None = None
    edges: list[Any] | None = None


# ── Public endpoint (no auth) — must be before {chart_id} routes ─────────────


@router.get("/public/{share_id}")
async def get_public_flowchart(share_id: str):
    """Fetch a flowchart by its public share token — no auth required."""
    db = get_db()
    doc = await db.flowcharts.find_one({"share_id": share_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found or not shared")
    return doc


# ── Protected endpoints ──────────────────────────────────────────────────────


@router.get("/", dependencies=[Depends(verify_token)])
async def list_flowcharts():
    db = get_db()
    cursor = db.flowcharts.find({}, {"_id": 0, "nodes": 0, "edges": 0}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        results.append(doc)
    return results


@router.post("/", dependencies=[Depends(verify_token)])
async def create_flowchart(body: FlowchartCreate):
    db = get_db()
    now = datetime.utcnow().isoformat()
    doc = {
        "id":         f"chart-{int(datetime.utcnow().timestamp() * 1000)}",
        "name":       body.name,
        "created_at": now,
        "updated_at": now,
        "nodes":      [],
        "edges":      [],
        "share_id":   None,
    }
    await db.flowcharts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/{chart_id}/share", dependencies=[Depends(verify_token)])
async def toggle_share(chart_id: str):
    """Toggle sharing on/off. Returns the share_id (or null if disabled)."""
    db = get_db()
    # Use same query as get_flowchart (which works) — no projection filter
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")

    current = doc.get("share_id")
    new_share_id = None if current else secrets.token_urlsafe(12)

    await db.flowcharts.update_one(
        {"id": chart_id},
        {"$set": {"share_id": new_share_id, "updated_at": datetime.utcnow().isoformat()}},
    )
    return {"share_id": new_share_id}


@router.get("/{chart_id}", dependencies=[Depends(verify_token)])
async def get_flowchart(chart_id: str):
    db = get_db()
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return doc


@router.put("/{chart_id}", dependencies=[Depends(verify_token)])
async def update_flowchart(chart_id: str, body: FlowchartUpdate):
    db = get_db()
    patch: dict = {"updated_at": datetime.utcnow().isoformat()}
    if body.name  is not None: patch["name"]  = body.name
    if body.nodes is not None: patch["nodes"] = body.nodes
    if body.edges is not None: patch["edges"] = body.edges

    result = await db.flowcharts.update_one({"id": chart_id}, {"$set": patch})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "ok"}


@router.delete("/{chart_id}", dependencies=[Depends(verify_token)])
async def delete_flowchart(chart_id: str):
    db = get_db()
    result = await db.flowcharts.delete_one({"id": chart_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "deleted"}
