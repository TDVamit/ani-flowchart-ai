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
    parallel_nodes: list[Any] | None = None
    parallel_edges: list[Any] | None = None


class SyncScreenRequest(BaseModel):
    screen_id: str


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
    cursor = db.flowcharts.find(
        {},
        {"_id": 0, "nodes": 0, "edges": 0, "parallel_nodes": 0, "parallel_edges": 0},
    ).sort("created_at", -1)
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
        "parallel_nodes": None,
        "parallel_edges": None,
    }
    await db.flowcharts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/{chart_id}/share", dependencies=[Depends(verify_token)])
async def toggle_share(chart_id: str):
    """Toggle sharing on/off. Returns the share_id (or null if disabled)."""
    db = get_db()
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
    if body.parallel_nodes is not None: patch["parallel_nodes"] = body.parallel_nodes
    if body.parallel_edges is not None: patch["parallel_edges"] = body.parallel_edges

    result = await db.flowcharts.update_one({"id": chart_id}, {"$set": patch})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "ok"}


@router.post("/{chart_id}/make-parallel", dependencies=[Depends(verify_token)])
async def make_parallel(chart_id: str):
    """Create a parallel version by deep-copying current nodes/edges into parallel_nodes/parallel_edges."""
    db = get_db()
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")

    import copy
    parallel_nodes = copy.deepcopy(doc.get("nodes", []))
    parallel_edges = copy.deepcopy(doc.get("edges", []))

    await db.flowcharts.update_one(
        {"id": chart_id},
        {"$set": {
            "parallel_nodes": parallel_nodes,
            "parallel_edges": parallel_edges,
            "updated_at": datetime.utcnow().isoformat(),
        }},
    )
    return {"status": "ok", "parallel_nodes": parallel_nodes, "parallel_edges": parallel_edges}


@router.delete("/{chart_id}/parallel", dependencies=[Depends(verify_token)])
async def delete_parallel(chart_id: str):
    """Remove the parallel version."""
    db = get_db()
    result = await db.flowcharts.update_one(
        {"id": chart_id},
        {"$set": {"parallel_nodes": None, "parallel_edges": None, "updated_at": datetime.utcnow().isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "ok"}


@router.post("/{chart_id}/sync-screen", dependencies=[Depends(verify_token)])
async def sync_screen(chart_id: str, body: SyncScreenRequest):
    """Sync a single screen from the original into the parallel version."""
    db = get_db()
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")

    orig_nodes = doc.get("nodes", [])
    orig_edges = doc.get("edges", [])
    par_nodes = doc.get("parallel_nodes") or []
    par_edges = doc.get("parallel_edges") or []

    screen_id = body.screen_id

    # Find the screen in original
    orig_screen = next((n for n in orig_nodes if n.get("id") == screen_id and n.get("type") == "screen"), None)
    if not orig_screen:
        raise HTTPException(status_code=404, detail="Screen not found in original")

    # Find elements inside that screen in original
    sx, sy = orig_screen["position"]["x"], orig_screen["position"]["y"]
    sw = orig_screen.get("width", 534)
    sh = orig_screen.get("height", 300)

    def is_inside(node, scr_x, scr_y, scr_w, scr_h):
        if node.get("type") != "element":
            return False
        cx = node["position"]["x"] + (node.get("width", 120)) / 2
        cy = node["position"]["y"] + (node.get("height", 50)) / 2
        return scr_x <= cx <= scr_x + scr_w and scr_y <= cy <= scr_y + scr_h

    orig_screen_elements = [n for n in orig_nodes if is_inside(n, sx, sy, sw, sh)]
    orig_screen_node_ids = {screen_id} | {n["id"] for n in orig_screen_elements}
    orig_screen_edges = [e for e in orig_edges if e.get("source") in orig_screen_node_ids and e.get("target") in orig_screen_node_ids]

    # Remove existing screen + its elements from the parallel
    par_screen = next((n for n in par_nodes if n.get("id") == screen_id and n.get("type") == "screen"), None)
    remove_ids = set()
    if par_screen:
        remove_ids.add(screen_id)
        psx, psy = par_screen["position"]["x"], par_screen["position"]["y"]
        psw = par_screen.get("width", 534)
        psh = par_screen.get("height", 300)
        for n in par_nodes:
            if is_inside(n, psx, psy, psw, psh):
                remove_ids.add(n["id"])

    new_par_nodes = [n for n in par_nodes if n["id"] not in remove_ids]
    new_par_edges = [e for e in par_edges if e.get("source") not in remove_ids and e.get("target") not in remove_ids]

    import copy as _copy
    new_par_nodes.extend([_copy.deepcopy(orig_screen)] + [_copy.deepcopy(e) for e in orig_screen_elements])
    new_par_edges.extend([_copy.deepcopy(e) for e in orig_screen_edges])

    await db.flowcharts.update_one(
        {"id": chart_id},
        {"$set": {"parallel_nodes": new_par_nodes, "parallel_edges": new_par_edges, "updated_at": datetime.utcnow().isoformat()}},
    )
    return {"status": "ok", "synced_screen": screen_id}


@router.post("/{chart_id}/sync-all", dependencies=[Depends(verify_token)])
async def sync_all(chart_id: str):
    """Add any new screens from the original that don't exist in the parallel. Does NOT overwrite existing."""
    db = get_db()
    doc = await db.flowcharts.find_one({"id": chart_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flowchart not found")

    orig_nodes = doc.get("nodes", [])
    orig_edges = doc.get("edges", [])
    par_nodes = doc.get("parallel_nodes") or []
    par_edges = doc.get("parallel_edges") or []

    par_screen_ids = {n["id"] for n in par_nodes if n.get("type") == "screen"}

    new_screen_ids = set()
    added_nodes = []

    for n in orig_nodes:
        if n.get("type") == "screen" and n["id"] not in par_screen_ids:
            new_screen_ids.add(n["id"])
            added_nodes.append(n)

    # Grab elements inside new screens
    added_element_ids = set()
    for n in orig_nodes:
        if n.get("type") != "element":
            continue
        for sn in [x for x in added_nodes if x.get("type") == "screen"]:
            sx, sy = sn["position"]["x"], sn["position"]["y"]
            sw = sn.get("width", 534)
            sh = sn.get("height", 300)
            cx = n["position"]["x"] + (n.get("width", 120)) / 2
            cy = n["position"]["y"] + (n.get("height", 50)) / 2
            if sx <= cx <= sx + sw and sy <= cy <= sy + sh:
                added_nodes.append(n)
                added_element_ids.add(n["id"])
                break

    all_new_ids = new_screen_ids | added_element_ids
    added_edges = [e for e in orig_edges if e.get("source") in all_new_ids and e.get("target") in all_new_ids]

    if not added_nodes:
        return {"status": "ok", "added_screens": 0}

    import copy as _copy
    new_par_nodes = par_nodes + [_copy.deepcopy(n) for n in added_nodes]
    new_par_edges = par_edges + [_copy.deepcopy(e) for e in added_edges]

    await db.flowcharts.update_one(
        {"id": chart_id},
        {"$set": {"parallel_nodes": new_par_nodes, "parallel_edges": new_par_edges, "updated_at": datetime.utcnow().isoformat()}},
    )
    return {"status": "ok", "added_screens": len(new_screen_ids)}


@router.delete("/{chart_id}", dependencies=[Depends(verify_token)])
async def delete_flowchart(chart_id: str):
    db = get_db()
    result = await db.flowcharts.delete_one({"id": chart_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Flowchart not found")
    return {"status": "deleted"}
