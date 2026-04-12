"""
Flowcharts router — stores flowchart metas + node/edge data in MongoDB.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth import verify_token
from database import get_db

router = APIRouter(prefix="/api/flowcharts", tags=["flowcharts"], dependencies=[Depends(verify_token)])


class FlowchartCreate(BaseModel):
    name: str


class FlowchartUpdate(BaseModel):
    name: str | None = None
    nodes: list[Any] | None = None
    edges: list[Any] | None = None


@router.get("/")
async def list_flowcharts():
    db = get_db()
    cursor = db.flowcharts.find({}, {"_id": 0, "nodes": 0, "edges": 0}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        results.append(doc)
    return results


@router.post("/")
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
    }
    await db.flowcharts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/{chart_id}")
async def get_flowchart(chart_id: str):
    db = get_db()
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return doc


@router.put("/{chart_id}")
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


@router.delete("/{chart_id}")
async def delete_flowchart(chart_id: str):
    db = get_db()
    result = await db.flowcharts.delete_one({"id": chart_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "deleted"}
