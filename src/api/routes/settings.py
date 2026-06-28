"""LLM settings API routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_services
from src.config import settings

router = APIRouter()


class PresetCreate(BaseModel):
    label: str
    base_url: str
    api_key: str
    model: str


def _mask_key(raw: str) -> str:
    if raw and len(raw) > 8:
        return raw[:4] + "****" + raw[-4:]
    elif raw:
        return "****"
    return ""


@router.get("/presets")
async def list_presets():
    """List all saved presets (active one highlighted)."""
    services = get_services()
    presets = services.settings_store.list_presets()

    # Also return the .env default as a read-only preset
    provider = settings.llm_provider
    model_map = {
        "anthropic": settings.anthropic_model,
        "openai": settings.openai_model,
        "deepseek": settings.deepseek_model,
        "ollama": settings.ollama_model,
        "custom": settings.llm_model,
    }
    url_map = {
        "anthropic": "https://api.anthropic.com",
        "openai": settings.openai_base_url or "https://api.openai.com/v1",
        "deepseek": settings.deepseek_base_url,
        "ollama": settings.ollama_base_url,
        "custom": settings.llm_base_url,
    }

    return {
        "presets": presets,
        "default": {
            "label": f"{provider} (.env)",
            "base_url": url_map.get(provider, ""),
            "model": model_map.get(provider, ""),
        },
        "active_preset_id": next((p["id"] for p in presets if p["is_active"]), None),
    }


@router.post("/presets")
async def add_preset(data: PresetCreate):
    """Save a new preset."""
    services = get_services()
    pid = services.settings_store.add_preset(
        label=data.label,
        base_url=data.base_url,
        api_key=data.api_key,
        model=data.model,
    )
    return {"status": "added", "id": pid}


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: int):
    """Delete a preset."""
    services = get_services()
    services.settings_store.delete_preset(preset_id)
    return {"status": "deleted"}


@router.post("/presets/{preset_id}/activate")
async def activate_preset(preset_id: int):
    """Activate a preset — takes effect immediately on next message."""
    services = get_services()
    result = services.settings_store.activate_preset(preset_id)
    if result is None:
        return {"status": "error", "message": "Preset not found"}
    return {"status": "activated", "config": _mask_key(result["api_key"])}


@router.post("/reset")
async def reset_to_default():
    """Deactivate all presets — next call falls back to .env."""
    services = get_services()
    services.settings_store.activate_preset(None)  # deactivates all
    return {"status": "reset"}
