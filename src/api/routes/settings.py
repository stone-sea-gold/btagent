"""LLM settings API routes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from src.agent.graph import invalidate_llm_cache
from src.api.dependencies import get_services
from src.config import settings
from src.llm_factory import _detect_protocol

router = APIRouter()


class PresetCreate(BaseModel):
    label: str
    base_url: str
    api_key: str
    model: str
    # Constrained on purpose: create_llm() treats anything but an explicit
    # protocol as "auto", so a typo would silently fall back to URL guessing
    # instead of telling the user.
    protocol: Literal["auto", "openai", "anthropic"] = "auto"


def _mask_key(raw: str) -> str:
    if raw and len(raw) > 8:
        return raw[:4] + "****" + raw[-4:]
    elif raw:
        return "****"
    return ""


@router.get("/presets")
def list_presets():
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
    # .env has no protocol field, so report what create_llm() will actually do:
    # the named providers pick their SDK directly, the rest go through the
    # URL heuristic. Ollama keeps its own protocol (ChatOllama).
    protocol_map = {
        "anthropic": "anthropic",
        "openai": "openai",
        "deepseek": _detect_protocol(settings.deepseek_base_url),
        "ollama": "ollama",
        "custom": _detect_protocol(settings.llm_base_url),
    }

    return {
        "presets": presets,
        "default": {
            "label": f"{provider} (.env)",
            "base_url": url_map.get(provider, ""),
            "model": model_map.get(provider, ""),
            "protocol": protocol_map.get(provider, "auto"),
        },
        "active_preset_id": next((p["id"] for p in presets if p["is_active"]), None),
    }


@router.post("/presets")
def add_preset(data: PresetCreate):
    """Save a new preset."""
    services = get_services()
    pid = services.settings_store.add_preset(
        label=data.label,
        base_url=data.base_url,
        api_key=data.api_key,
        model=data.model,
        protocol=data.protocol,
    )
    return {"status": "added", "id": pid}


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int):
    """Delete a preset."""
    services = get_services()
    services.settings_store.delete_preset(preset_id)
    return {"status": "deleted"}


@router.post("/presets/{preset_id}/activate")
def activate_preset(preset_id: int):
    """Activate a preset — takes effect immediately on next message."""
    services = get_services()
    result = services.settings_store.activate_preset(preset_id)
    if result is None:
        return {"status": "error", "message": "Preset not found"}
    invalidate_llm_cache()
    return {"status": "activated", "config": _mask_key(result["api_key"])}


@router.post("/reset")
def reset_to_default():
    """Deactivate all presets — next call falls back to .env."""
    services = get_services()
    services.settings_store.activate_preset(None)  # deactivates all
    invalidate_llm_cache()
    return {"status": "reset"}
