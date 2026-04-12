"""
AI-powered flowchart generation.

Flow:
1. Fetch Lordicon icon inventory from key categories (cached for 1 h)
2. Build a comprehensive system prompt describing the full flowchart schema
3. Call Claude to generate the chart spec as JSON
4. Post-process: resolve lottieCode → actual CDN URL via embed API
5. Return the completed spec to the frontend
"""

import asyncio
import json
import logging
import re
import time
from typing import Any

import anthropic
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flowchart-ai", tags=["flowchart-ai"])

# ── Lordicon icon cache ───────────────────────────────────────────────────────

_ICON_CACHE: dict[str, Any] = {}   # {"data": [...], "ts": float}
_CACHE_TTL  = 3600                  # 1 hour

# Categories most relevant for flowchart / UI diagrams
PRIORITY_CATS = [3, 137, 8, 9, 12, 50, 82, 175, 19, 110, 6, 68, 69, 180, 173]

LORDICON_BASE   = "https://lordicon.com/api/library"
LORDICON_COMMON = {"family": "wired", "style": "outline", "filter": "free"}
LORDICON_HDRS   = {
    "User-Agent": "Mozilla/5.0 (compatible; AuditDashboard/1.0)",
    "Accept": "application/json",
}


async def _fetch_category_icons(client: httpx.AsyncClient, cat_id: int) -> list[dict]:
    try:
        r = await client.get(
            f"{LORDICON_BASE}/icons",
            params={**LORDICON_COMMON, "categoryId": cat_id},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json() or []
    except Exception:
        pass
    return []


async def _fetch_category_names(client: httpx.AsyncClient) -> dict[int, str]:
    try:
        r = await client.get(
            f"{LORDICON_BASE}/sidebar",
            params=LORDICON_COMMON,
            timeout=10,
        )
        if r.status_code == 200:
            cats = r.json().get("categories", [])
            return {c["id"]: c["title"] for c in cats}
    except Exception:
        pass
    return {}


async def get_icon_inventory() -> str:
    """Return a compact string listing all available icons, grouped by category."""
    now = time.time()
    if _ICON_CACHE.get("ts", 0) + _CACHE_TTL > now and _ICON_CACHE.get("data"):
        return _ICON_CACHE["data"]

    async with httpx.AsyncClient(headers=LORDICON_HDRS) as client:
        cat_names, *icon_lists = await asyncio.gather(
            _fetch_category_names(client),
            *[_fetch_category_icons(client, cid) for cid in PRIORITY_CATS],
        )

    lines: list[str] = []
    for cid, icons in zip(PRIORITY_CATS, icon_lists):
        if not icons:
            continue
        cat_label = cat_names.get(cid, str(cid))
        entries = [f"{ic['title']} ({ic['index']}-{ic['name']})" for ic in icons]
        lines.append(f"  [{cat_label}]  " + ", ".join(entries))

    inventory = "\n".join(lines)
    _ICON_CACHE["data"] = inventory
    _ICON_CACHE["ts"]   = now
    return inventory


# ── Embed URL resolution ──────────────────────────────────────────────────────

async def resolve_lottie_urls(screens: list[dict]) -> None:
    """In-place: for every element with lottieCode, fetch CDN URL and set lottieUrl."""
    codes: set[str] = set()
    for screen in screens:
        for el in screen.get("elements", []):
            c = el.get("lottieCode")
            if c:
                codes.add(c)

    if not codes:
        return

    async def fetch_embed(client: httpx.AsyncClient, code: str) -> tuple[str, str]:
        try:
            r = await client.get(
                f"{LORDICON_BASE}/embed/wired/outline/{code}",
                timeout=8,
            )
            if r.status_code == 200:
                return code, r.json().get("icon", "")
        except Exception:
            pass
        return code, ""

    async with httpx.AsyncClient(headers=LORDICON_HDRS) as client:
        results = await asyncio.gather(*[fetch_embed(client, c) for c in codes])

    code_map: dict[str, str] = dict(results)

    for screen in screens:
        for el in screen.get("elements", []):
            code = el.pop("lottieCode", None)
            if code and code_map.get(code):
                el["lottieUrl"] = code_map[code]


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """
You are a flowchart designer AI. Given a user description, output a COMPLETE animated flowchart
as a single JSON object. Return ONLY valid JSON — no markdown, no explanation.

════════════════════════════════════════════════════════
OUTPUT SCHEMA
════════════════════════════════════════════════════════

{{
  "title": string,
  "screens": [
    {{
      "id": "s1",
      "label": string,
      "ratio": "16:9" | "9:16" | "1:1" | "4:3" | "3:4" | "21:9",
      "backgroundColor": string (hex),
      "borderColor": string (hex),
      "order": number (0 = first to play),
      "elements": [ ...Element ],
      "edges": [ ...Edge ]
    }}
  ]
}}

════════════════════════════════════════════════════════
SCREEN PIXEL DIMENSIONS
════════════════════════════════════════════════════════
16:9  → 534 × 300   (landscape — use as default)
9:16  → 169 × 300   (portrait / mobile)
1:1   → 300 × 300   (square)
4:3   → 400 × 300
3:4   → 225 × 300
21:9  → 700 × 300   (ultrawide)

════════════════════════════════════════════════════════
ELEMENT SCHEMA
════════════════════════════════════════════════════════
{{
  "id": "e1",           // unique string (e.g. "e1", "e2", "s1e3")
  "x": number,          // pixels from screen LEFT — must stay inside screen width
  "y": number,          // pixels from screen TOP  — must stay inside screen height
  "width": number,
  "height": number,
  "elementType": "shape" | "text" | "premade",
  "shape": ShapeType,         // only when elementType = "shape"
  "premadeType": string,      // only when elementType = "premade"
  "lottieCode": "63-home",    // REQUIRED when premadeType starts with "lottie-"
  "lottiePrimary": "#000000", // lord-icon primary color
  "lottieSecondary": "#6366f1",
  "lottieDelay": 500,
  "text": string,
  "step": number,        // 1-based appearance order within the screen
  "style": ElementStyle,
  "animation": ElementAnimation
}}

════════════════════════════════════════════════════════
SHAPES  (elementType = "shape")
════════════════════════════════════════════════════════
rectangle | rounded-rect | circle | diamond | parallelogram |
cylinder | hexagon | document | triangle | star | cross | arrow-right | cloud | tag

════════════════════════════════════════════════════════
PREMADE ANIMATIONS  (elementType = "premade", no lottieCode needed)
════════════════════════════════════════════════════════
processing | building | writing | loading | checking | sending | thinking |
uploading | success | error | warning | waiting | syncing | downloading |
scanning | typing | broadcasting | recording | streaming | connecting |
api | database | server | user | clock | sparkle | fire | shield | lock | refresh

LUCIDE ICONS  (prefix: "lucide-")
lucide-check-circle | lucide-x-circle | lucide-alert-circle | lucide-info |
lucide-send | lucide-mail | lucide-phone | lucide-bell | lucide-user | lucide-users |
lucide-database | lucide-server | lucide-cloud | lucide-globe | lucide-shield |
lucide-lock | lucide-key | lucide-settings | lucide-search | lucide-filter |
lucide-download | lucide-upload | lucide-refresh-cw | lucide-arrow-right |
lucide-clock | lucide-calendar | lucide-star | lucide-heart | lucide-zap |
lucide-activity | lucide-layers | lucide-package | lucide-git-branch | lucide-code |
lucide-cpu | lucide-hard-drive | lucide-wifi | lucide-terminal | lucide-play

════════════════════════════════════════════════════════
LORDICON ANIMATED ICONS  (prefix: "lottie-", set lottieCode = "{{index}}-{{name}}")
════════════════════════════════════════════════════════
{icon_inventory}

════════════════════════════════════════════════════════
ELEMENT STYLE
════════════════════════════════════════════════════════
{{
  "backgroundColor": "#ffffff",
  "borderColor": "#6366f1",
  "borderWidth": 1.5,     // 0-4
  "borderRadius": 8,      // 0-50
  "textColor": "#1e293b",
  "fontSize": 13,         // 9-20
  "fontWeight": "normal" | "bold",
  "fontStyle": "normal" | "italic",
  "textAlign": "left" | "center" | "right",
  "fontFamily": "IBM Plex Sans" | "Inter" | "Poppins" | "Roboto" | "DM Sans" | "Montserrat",
  "opacity": 1,
  "shadowEnabled": false,
  "shadowColor": "rgba(0,0,0,0.15)",
  "shadowBlur": 10,
  "shadowX": 0,
  "shadowY": 3
}}

════════════════════════════════════════════════════════
ELEMENT ANIMATION
════════════════════════════════════════════════════════
{{
  "inType": "fade-in" | "slide-up" | "slide-down" | "slide-left" | "slide-right" | "zoom-in" | "bounce" | "flip" | "none",
  "duration": 0.4,   // 0.2–1.5 seconds
  "delay": 0,        // 0–3 s — stagger siblings by 0.1-0.2s for polish
  "stay": 0.5        // 0–5 s — pause after in-animation
}}

════════════════════════════════════════════════════════
EDGE SCHEMA
════════════════════════════════════════════════════════
{{
  "id": "ed1",
  "source": "e1",   // element id
  "target": "e2",
  "label": "",
  "step": 3,
  "style": {{
    "color": "#6366f1",
    "strokeWidth": 2,
    "lineType": "solid" | "dashed" | "dotted",
    "arrowType": "filled-arrow" | "open-arrow" | "none",
    "pathType": "bezier" | "straight" | "step" | "smoothstep",
    "markerSize": 6
  }},
  "animation": {{
    "inType": "draw" | "fade-in" | "none",
    "inDuration": 0.6,
    "delay": 0,
    "stay": 0,
    "type": "none" | "flow" | "pulse" | "dash",
    "loop": "none" | "infinite",
    "loopCount": 1,
    "duration": 1,
    "flowContent": {{ "type": "none", "text": "", "size": 6, "color": "#6366f1", "loop": true }}
  }}
}}

════════════════════════════════════════════════════════
SIZING GUIDELINES  (STRICTLY FOLLOW)
════════════════════════════════════════════════════════
Title / heading text:     width 180-320, height 36-50
Body label / caption:     width 100-200, height 28-40
Action button (rounded):  width 110-170, height 40-52
Shape card / box:         width 140-220, height 50-70
Lucide icon element:      width 56-72,   height 56-72
Premade animation:        width 64-80,   height 64-80
Lordicon animation:       width 80-100,  height 80-100
Decision diamond:         width 120-160, height 80-100
Small connector node:     width 28-36,   height 28-36

Minimum margin from screen edge: 18px on all sides
Minimum gap between elements: 16px
Vertical step spacing: 60-80px
Horizontal side-by-side spacing: 36-56px

FOR 16:9 (534×300) common layout patterns:
  Center column:  x = (534/2 - width/2)
  Left column:    x = 20-160
  Right column:   x = 374-494
  Top band:       y = 18-70
  Middle band:    y = 100-200
  Bottom band:    y = 220-265

════════════════════════════════════════════════════════
ANIMATION TIMING RULES
════════════════════════════════════════════════════════
• step 1 appears first; use increasing steps for sequential reveal
• Edges must have a higher step than BOTH their source and target elements
• Stagger sibling elements: add 0.1-0.15s delay between them
• Use "stay" (0.5-2s) on key narrative moments
• Recommended pairing:
    header/title     → slide-up, duration 0.5
    cards/boxes      → fade-in or zoom-in, duration 0.4
    process icons    → slide-right, duration 0.4
    status results   → bounce or zoom-in, duration 0.5
    connecting edges → "draw" inType, inDuration 0.6

════════════════════════════════════════════════════════
DESIGN PALETTE
════════════════════════════════════════════════════════
Brand indigo:   #6366f1  (primary)   muted: #818cf8
Success green:  #22c55e              bg: #f0fdf4
Error red:      #ef4444              bg: #fef2f2
Warning amber:  #f59e0b              bg: #fffbeb
Info blue:      #3b82f6              bg: #eff6ff
Neutral bg:     #f8fafc  #f1f5f9  #e2e8f0
White:          #ffffff
Dark text:      #1e293b
Muted text:     #64748b  #94a3b8

Use shadows (shadowEnabled: true) on primary cards for depth.
Maintain visual hierarchy: 2-3 distinct font sizes per screen.
Keep text SHORT — labels under 4 words, full sentences only for text elements.

════════════════════════════════════════════════════════
MULTI-SCREEN RULES
════════════════════════════════════════════════════════
• 2-6 screens for a complete story; each screen is one "chapter"
• Order 0 plays first; increment for each subsequent screen
• All x,y coordinates are RELATIVE to the screen's own top-left (0,0)
• Screen-to-screen narrative should flow left→right visually
• Keep each screen self-contained (its own elements, own step sequence starting at 1)

Output ONLY the JSON object. No code fences, no commentary.
"""


# ── Request / response ────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "16:9"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_flowchart(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    # 1. Fetch icon inventory
    try:
        icon_inventory = await get_icon_inventory()
    except Exception as exc:
        logger.warning("Lordicon fetch failed: %s", exc)
        icon_inventory = "(icon library unavailable)"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(icon_inventory=icon_inventory)

    user_message = (
        f"Create a flowchart for: {req.prompt}\n\n"
        f"Default aspect ratio: {req.aspect_ratio}"
    )

    # 2. Call Claude
    try:
        ai_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        async with ai_client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=64000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            raw_text = (await stream.get_final_text()).strip()
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI generation failed: {exc}") from exc

    # 3. Parse JSON — strip markdown fences and JS-style comments
    # Remove ```json ... ``` fences
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            l for l in lines if not l.strip().startswith("```")
        ).strip()

    # Remove JS-style // line comments (AI sometimes adds these despite instructions)
    raw_text = re.sub(r'//[^\n"]*(?=\n|$)', '', raw_text)
    # Remove trailing commas before } or ] (another common AI mistake)
    raw_text = re.sub(r',\s*([}\]])', r'\1', raw_text)

    try:
        spec = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error: %s\nRaw: %.2000s", exc, raw_text)
        raise HTTPException(status_code=502, detail="AI returned invalid JSON") from exc

    # 4. Resolve lottie CDN URLs
    try:
        await resolve_lottie_urls(spec.get("screens", []))
    except Exception as exc:
        logger.warning("Lottie URL resolution partial failure: %s", exc)

    return JSONResponse(content=spec)
