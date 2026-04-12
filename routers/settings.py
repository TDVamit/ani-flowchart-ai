from fastapi import APIRouter, Depends
from services.llm_service import AVAILABLE_MODELS
from auth import verify_token
from config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(verify_token)])


@router.get("/models")
async def get_available_models():
    """Returns available models per provider, with configured status."""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic (Claude)",
                "is_configured": bool(settings.anthropic_api_key),
                "models": AVAILABLE_MODELS["anthropic"]
            },
            {
                "id": "openai",
                "name": "OpenAI (GPT)",
                "is_configured": bool(settings.openai_api_key),
                "models": AVAILABLE_MODELS["openai"]
            },
            {
                "id": "gemini",
                "name": "Google (Gemini)",
                "is_configured": bool(settings.google_api_key),
                "models": AVAILABLE_MODELS["gemini"]
            }
        ],
        "default_provider": settings.default_llm_provider,
        "default_model": settings.default_llm_model,
        "whisper_configured": bool(settings.openai_api_key)
    }
