"""
Amarktai App Builder — Centralized AI Capability Registry.

Phase 1A: Single source of truth for what every provider/model supports.

The registry is intentionally declarative and stateless so it can be
serialised to JSON for the frontend at any time.  A separate
``probe_live_status`` coroutine performs a lightweight live check against
the configured provider and annotates the registry with a ``live``
availability flag.

Usage::

    from app.core.capability_registry import (
        get_registry,
        probe_live_status,
        get_model_capability,
    )
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

# ── Capability schema ─────────────────────────────────────────────────────────


@dataclass
class ModelCapability:
    """Capability descriptor for a single provider / model combination."""

    provider: str
    model: str
    # Functional capabilities
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_image_generation: bool = False
    supports_video_generation: bool = False
    supports_audio: bool = False
    supports_repo_analysis: bool = False
    supports_long_context: bool = False
    supports_tool_use: bool = False
    supports_streaming: bool = False
    # Routing metadata
    cost_tier: str = "medium"      # low | medium | high
    speed_tier: str = "medium"     # fast | medium | slow
    reliability_score: float = 0.9  # 0.0–1.0
    # Runtime state (populated by probe_live_status)
    available: bool = True
    unavailable_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Static capability catalog ─────────────────────────────────────────────────

_CATALOG: list[ModelCapability] = [
    # ── GenX / Claude Sonnet ──────────────────────────────────────────────────
    ModelCapability(
        provider="genx",
        model="claude-sonnet-4-6",
        supports_reasoning=True,
        supports_vision=True,
        supports_repo_analysis=True,
        supports_long_context=True,
        supports_tool_use=True,
        supports_streaming=True,
        cost_tier="high",
        speed_tier="medium",
        reliability_score=0.97,
    ),
    # ── GenX / Claude Haiku ───────────────────────────────────────────────────
    ModelCapability(
        provider="genx",
        model="claude-haiku-4-5",
        supports_reasoning=True,
        supports_vision=False,
        supports_repo_analysis=True,
        supports_long_context=False,
        supports_tool_use=True,
        supports_streaming=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.95,
    ),
    # ── GenX / Gemini Flash ───────────────────────────────────────────────────
    ModelCapability(
        provider="genx",
        model="gemini-2.5-flash",
        supports_reasoning=True,
        supports_vision=True,
        supports_repo_analysis=True,
        supports_long_context=True,
        supports_tool_use=True,
        supports_streaming=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.93,
    ),
    # ── GenX / GPT-5 mini ─────────────────────────────────────────────────────
    ModelCapability(
        provider="genx",
        model="gpt-5.4-mini",
        supports_reasoning=True,
        supports_vision=True,
        supports_repo_analysis=True,
        supports_long_context=False,
        supports_tool_use=True,
        supports_streaming=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.94,
    ),
    # ── GenX / image generation (DALL·E / Flux style) ────────────────────────
    ModelCapability(
        provider="genx",
        model="dall-e-3",
        supports_image_generation=True,
        cost_tier="high",
        speed_tier="slow",
        reliability_score=0.88,
    ),
    ModelCapability(
        provider="genx",
        model="flux-schnell",
        supports_image_generation=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.85,
    ),
    # ── Qwen (optional, direct provider) ─────────────────────────────────────
    ModelCapability(
        provider="qwen",
        model="qwen-max",
        supports_reasoning=True,
        supports_vision=True,
        supports_repo_analysis=True,
        supports_long_context=True,
        supports_tool_use=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.88,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen-vl-plus",
        supports_vision=True,
        supports_image_generation=False,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.86,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen-audio-turbo",
        supports_audio=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.82,
    ),
]

# Index by (provider, model) for O(1) lookups
_INDEX: dict[tuple[str, str], ModelCapability] = {
    (c.provider, c.model): c for c in _CATALOG
}


# ── Public API ────────────────────────────────────────────────────────────────


def get_registry() -> list[dict]:
    """Return the full capability catalog as a list of dicts."""
    return [c.to_dict() for c in _CATALOG]


def get_model_capability(provider: str, model: str) -> ModelCapability | None:
    """Look up a model in the registry.  Returns None if unknown."""
    return _INDEX.get((provider, model))


def capabilities_summary() -> dict:
    """Return a high-level summary of what the system supports right now.

    Derives truth from the configured environment variables, so it reflects
    the actual runtime state without a live network call.
    """
    genx_key = os.environ.get("GENX_API_KEY", "")
    qwen_key = os.environ.get("QWEN_API_KEY", "")

    genx_available = bool(genx_key)
    qwen_available = bool(qwen_key)
    qwen_image_model = os.environ.get("QWEN_MODEL_IMAGE", "")
    qwen_video_model = os.environ.get("QWEN_MODEL_VIDEO", "")
    qwen_audio_model = os.environ.get("QWEN_MODEL_AUDIO", "")

    image_gen_available = genx_available  # GenX provides image gen models
    video_gen_available = bool(qwen_key and qwen_video_model)
    audio_available = bool(qwen_key and qwen_audio_model)

    return {
        "text_generation": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "reasoning": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "vision": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "image_generation": {
            "available": image_gen_available,
            "provider": "genx" if image_gen_available else None,
            "reason": (
                None if image_gen_available
                else "Image generation unavailable: GENX_API_KEY not configured. "
                     "Configure it in Settings to enable AI image generation."
            ),
            "fallback": "CSS gradients and SVG placeholders are used instead.",
        },
        "video_generation": {
            "available": video_gen_available,
            "provider": "qwen" if video_gen_available else None,
            "reason": (
                None if video_gen_available
                else (
                    "Video generation unavailable: configure QWEN_API_KEY and QWEN_MODEL_VIDEO."
                    if qwen_key else "Video generation unavailable: QWEN_API_KEY not configured."
                )
            ),
            "fallback": "No video fallback — video sections are replaced with static visuals.",
        },
        "audio": {
            "available": audio_available,
            "provider": "qwen" if audio_available else None,
            "reason": (
                None if audio_available
                else (
                    "Audio generation unavailable: configure QWEN_API_KEY and QWEN_MODEL_AUDIO."
                    if qwen_key else "Audio generation unavailable: QWEN_API_KEY not configured."
                )
            ),
            "fallback": "No audio fallback.",
        },
        "repo_analysis": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "long_context": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "tool_use": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
        "streaming": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "reason": None if genx_available else "GENX_API_KEY not configured",
        },
    }


async def probe_live_status(api_key: str | None, base_url: str | None = None) -> dict:
    """Probe the live GenX endpoint to check which models are actually available.

    Returns a dict of model_id → {"available": bool, "reason": str}.
    Safe to call at startup — failures do NOT crash the server.
    """
    import httpx

    base = (base_url or os.environ.get("GENX_BASE_URL", "https://query.genx.sh/v1")).rstrip("/")
    key = api_key or os.environ.get("GENX_API_KEY", "")

    if not key:
        return {c.model: {"available": False, "reason": "GENX_API_KEY not configured"}
                for c in _CATALOG if c.provider == "genx"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as cx:
            r = await cx.get(
                f"{base}/models",
                headers={
                    "Authorization": f"Bearer {key}",
                    "User-Agent": "Amarktai-App-Builder/1.0",
                },
            )
            if r.status_code in (401, 403):
                return {c.model: {"available": False, "reason": "API key rejected by provider"}
                        for c in _CATALOG if c.provider == "genx"}
            r.raise_for_status()
            live_models: list[dict] = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
            live_ids = {m.get("id", "") for m in live_models}
    except Exception as exc:
        return {c.model: {"available": False, "reason": f"Provider unreachable: {exc}"}
                for c in _CATALOG if c.provider == "genx"}

    result: dict[str, dict] = {}
    for cap in _CATALOG:
        if cap.provider != "genx":
            continue
        if cap.model in live_ids:
            result[cap.model] = {"available": True, "reason": None}
        else:
            result[cap.model] = {
                "available": False,
                "reason": f"Model '{cap.model}' not returned by provider's /models endpoint.",
            }
    return result


def models_with_capability(capability: str) -> list[dict]:
    """Return all models that support a given capability flag.

    ``capability`` must be one of the boolean fields on ModelCapability,
    e.g. ``'supports_image_generation'``, ``'supports_vision'``.
    """
    if not capability.startswith("supports_"):
        capability = f"supports_{capability}"
    return [
        c.to_dict()
        for c in _CATALOG
        if getattr(c, capability, False)
    ]
