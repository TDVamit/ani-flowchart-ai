"""
Lordicon proxy — forwards requests to lordicon.com API so the browser
never calls lordicon.com directly (avoids CORS / auth issues).

All endpoints are scoped to free, wired/outline icons only.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/lordicon", tags=["lordicon"])

BASE = "https://lordicon.com/api/library"
COMMON = {"family": "wired", "style": "outline", "filter": "free"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AuditDashboard/1.0)",
    "Accept": "application/json",
}


async def _get(url: str, params: dict | None = None) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Upstream error")
        return JSONResponse(content=r.json())
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unreachable: {exc}") from exc


@router.get("/sidebar")
async def sidebar():
    """Return category list."""
    return await _get(f"{BASE}/sidebar", params=COMMON)


@router.get("/icons")
async def icons(categoryId: int = Query(...)):
    """Return icons for a given category ID."""
    return await _get(f"{BASE}/icons", params={**COMMON, "categoryId": categoryId})


@router.get("/search")
async def search(query: str = Query(..., min_length=1)):
    """Search icons by keyword."""
    return await _get(f"{BASE}/search", params={**COMMON, "query": query})


@router.get("/embed/{code:path}")
async def embed(code: str):
    """
    Return embed details for an icon code like '63-home'.
    Response: { lib, icon, key }  — 'icon' is the CDN JSON URL.
    """
    return await _get(f"{BASE}/embed/wired/outline/{code}")
