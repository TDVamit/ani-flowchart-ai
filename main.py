from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import connect_db, close_db
from config import settings
from routers import settings as settings_router, flowcharts, flowchart_assets
from routers.auth_router import router as auth_router
from routers.lordicon import router as lordicon_router
from routers.flowchart_ai import router as flowchart_ai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Flowchart AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)              # public — login
app.include_router(settings_router.router)   # protected
app.include_router(flowcharts.router)        # protected
app.include_router(flowchart_assets.router)  # protected
app.include_router(lordicon_router)          # public — proxies lordicon.com
app.include_router(flowchart_ai_router)      # protected — AI flowchart generation


@app.get("/health")
async def health():
    return {"status": "ok"}
