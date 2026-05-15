"""
Amarktai App Builder — GenX Full Model Discovery and Sync Service.

Fetches the complete list of models from GenX, classifies them by capability,
stores them in a local model registry, and exposes them for routing.

If the live sync fails, a static fallback list is used so the system remains
functional. The live model count always overrides the static list when sync succeeds.

Capability classification is heuristic, based on model ID patterns.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.genx_live_probe_service import discover_genx_runtime

logger = logging.getLogger("amarktai.genx_model_sync")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BUILDS_ROOT = "/var/www/amarktai/builds"
REGISTRY_FILE = "genx_model_registry.json"
SYNC_CACHE_TTL = int(os.environ.get("GENX_MODEL_SYNC_TTL", "3600"))  # 1 hour
PROBE_TIMEOUT = float(os.environ.get("GENX_SYNC_TIMEOUT", "15"))

# ── Static fallback model list ────────────────────────────────────────────────
# Used when live sync is unavailable.

STATIC_GENX_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-5",
    "gpt-5-mini",
    "o3",
    "o4-mini",
    "grok-3",
    "grok-3-mini",
    "qwen3-max",
    "llama-4-maverick",
    "llama-4-scout",
    "deepseek-v3",
    "deepseek-r1",
    "mistral-large",
]

# ── Capability classification rules ──────────────────────────────────────────

_CAPABILITY_PATTERNS: dict[str, list[str]] = {
    "text":         [".*"],                                        # all models do text
    "reasoning":    ["o3", "o4", "o1", "r1", "sonnet", "opus", "gemini-2.5-pro", "grok-3$", "qwen3-max", "qwen3-plus"],
    "coding":       ["sonnet", "haiku", "gpt-4", "gpt-5", "claude", "codex", "qwen.*coder", "deepseek", "llama"],
    "vision":       ["vision", "vl", "gemini", "gpt-4", "gpt-5", "claude-sonnet", "claude-opus", "claude-haiku"],
    "image":        ["image", "dall-e", "stable", "flux", "midjourney", "ideogram"],
    "audio":        ["audio", "whisper", "tts", "asr", "omni", "realtime"],
    "video":        ["video", "sora", "kling"],
    "long_context": ["gemini-2.5", "claude-opus", "claude-sonnet", "qwen-long", "128k", "200k"],
    "tool_use":     ["sonnet", "haiku", "opus", "gpt-4", "gpt-5", "gemini", "llama-4"],
    "streaming":    ["sonnet", "haiku", "opus", "gpt-4", "gpt-5", "gemini", "llama"],
    "embeddings":   ["embed", "text-embedding", "e5", "bge"],
    "moderation":   ["omni-moderation", "moderation"],
}


def _classify_model(model_id: str) -> list[str]:
    """Return capability tags for a model based on its ID."""
    model_lower = model_id.lower()
    caps = []
    for cap, patterns in _CAPABILITY_PATTERNS.items():
        if any(re.search(p, model_lower) for p in patterns):
            caps.append(cap)
    return caps


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_path() -> Path:
    root = Path(os.environ.get("BUILDS_STORAGE_ROOT", DEFAULT_BUILDS_ROOT)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / REGISTRY_FILE


# ── Sync ──────────────────────────────────────────────────────────────────────

async def sync_genx_models(api_key: str) -> dict[str, Any]:
    """
    Fetch the full model list from GenX and update the local registry.

    Returns a status dict with:
      - ok: bool
      - source: "live" | "fallback"
      - model_count: int
      - models: list[dict]
      - synced_at: str
      - error: str | None
    """
    if not api_key:
        return _use_fallback("GENX_API_KEY not configured")

    try:
        runtime = await discover_genx_runtime(
            api_key,
            base_url=os.environ.get("GENX_BASE_URL", "https://query.genx.sh/v1"),
            force_refresh=True,
        )
        if runtime.get("live_status") != "live_ok":
            return _use_fallback(runtime.get("reason") or "GenX runtime discovery failed")

        models = _build_model_list(runtime.get("models", []))
        result = _build_registry(models, source="live")
        result["category_counts"] = runtime.get("category_counts", {})
        result["runtime_capabilities"] = runtime.get("capabilities", {})
        result["base_url"] = runtime.get("base_url")
        _save_registry(result)
        return result

    except Exception as exc:
        return _use_fallback(str(exc)[:200])


def _build_model_list(raw: list) -> list[dict]:
    """Convert raw GenX model objects to classified model dicts."""
    models = []
    for item in raw:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id", item.get("name", ""))
        else:
            continue
        if not model_id:
            continue
        caps = _classify_model(model_id)
        if isinstance(item, dict) and item.get("category") and item["category"] not in caps:
            caps.append(str(item["category"]))
        models.append({
            "id": model_id,
            "provider": "genx",
            "capabilities": caps,
            "category": item.get("category") if isinstance(item, dict) else None,
            "raw": item if isinstance(item, dict) else {"id": model_id},
        })
    return models


def _capability_counts(models: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in models:
        for cap in m.get("capabilities", []):
            counts[cap] = counts.get(cap, 0) + 1
    return counts


def _build_registry(models: list[dict], source: str) -> dict[str, Any]:
    return {
        "ok": True,
        "source": source,
        "model_count": len(models),
        "models": models,
        "capability_counts": _capability_counts(models),
        "synced_at": _now(),
        "error": None,
    }


def _use_fallback(error: str) -> dict[str, Any]:
    logger.warning("GenX model sync failed, using fallback: %s", error)
    models = [
        {"id": m, "provider": "genx", "capabilities": _classify_model(m), "raw": {"id": m}}
        for m in STATIC_GENX_MODELS
    ]
    result = _build_registry(models, source="fallback")
    result["error"] = error
    result["ok"] = False
    _save_registry(result)
    return result


def _save_registry(data: dict) -> None:
    path = _registry_path()
    try:
        # Remove raw detail to keep file small
        slim = {
            **data,
            "models": [
                {
                    "id": m["id"],
                    "provider": "genx",
                    "category": m.get("category"),
                    "capabilities": m["capabilities"],
                }
                for m in data.get("models", [])
            ],
        }
        path.write_text(json.dumps(slim, indent=2))
    except Exception as exc:
        logger.warning("Could not save GenX registry: %s", exc)


def load_registry() -> dict[str, Any]:
    """Load the saved model registry from disk, or return the fallback."""
    path = _registry_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data
        except Exception:
            pass
    return _use_fallback("Registry file not found; using static fallback.")


def get_models_by_capability(capability: str) -> list[str]:
    """Return model IDs that support the given capability."""
    registry = load_registry()
    return [
        m["id"]
        for m in registry.get("models", [])
        if capability in m.get("capabilities", [])
    ]
