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
    # GenX media models are discovered at runtime from category endpoints.
    # ── Qwen (optional, direct provider) ─────────────────────────────────────
    ModelCapability(
        provider="qwen",
        model="qwen3-max",
        supports_reasoning=True,
        supports_vision=False,
        supports_repo_analysis=True,
        supports_long_context=True,
        supports_tool_use=True,
        cost_tier="high",
        speed_tier="medium",
        reliability_score=0.91,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-coder-plus",
        supports_reasoning=True,
        supports_repo_analysis=True,
        supports_tool_use=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.90,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-coder-flash",
        supports_reasoning=True,
        supports_repo_analysis=True,
        supports_tool_use=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.87,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen-image-plus",
        supports_image_generation=True,
        supports_vision=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.86,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-omni-flash",
        supports_audio=True,
        supports_vision=True,
        supports_streaming=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.84,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-asr-flash",
        supports_audio=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.83,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen-long-latest",
        supports_reasoning=True,
        supports_long_context=True,
        supports_repo_analysis=True,
        cost_tier="medium",
        speed_tier="slow",
        reliability_score=0.85,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-vl-plus",
        supports_vision=True,
        cost_tier="medium",
        speed_tier="medium",
        reliability_score=0.85,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen3-omni-flash-realtime",
        supports_audio=True,
        supports_streaming=True,
        cost_tier="low",
        speed_tier="fast",
        reliability_score=0.82,
    ),
    ModelCapability(
        provider="qwen",
        model="qwen-deep-research",
        supports_reasoning=True,
        supports_long_context=True,
        supports_tool_use=True,
        cost_tier="high",
        speed_tier="slow",
        reliability_score=0.88,
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
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")

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
        # Phase 3 additions — agent audit requirements
        "github_integration": {
            "available": bool(os.environ.get("GITHUB_PAT")),
            "provider": "github" if os.environ.get("GITHUB_PAT") else None,
            "reason": (
                None if os.environ.get("GITHUB_PAT")
                else "GitHub integration unavailable: GITHUB_PAT not configured."
            ),
            "fallback": "File export only — no GitHub push/PR without a PAT.",
        },
        "web_research": {
            "available": bool(firecrawl_key),
            "configured": bool(firecrawl_key),
            "provider": "firecrawl" if firecrawl_key else None,
            "live_status": "key_present_not_tested" if firecrawl_key else "setup_needed",
            "reason": None if firecrawl_key else "Firecrawl unavailable: FIRECRAWL_API_KEY not configured.",
            "fallback": "Scout continues without live web research.",
        },
        "stock_media": {
            "available": bool(pixabay_key),
            "configured": bool(pixabay_key),
            "provider": "pixabay" if pixabay_key else None,
            "live_status": "key_present_not_tested" if pixabay_key else "key_missing",
            "reason": None if pixabay_key else "Pixabay unavailable: PIXABAY_API_KEY not configured.",
            "fallback": "Use AI images if configured or CSS/SVG visuals.",
        },
        "preview_generation": {
            "available": True,  # Static preview always available; sandbox preview requires filesystem
            "provider": "sandbox",
            "reason": None,
            "fallback": "Static HTML preview always available; Vite/React preview requires server.",
        },
        "voice_generation": {
            "available": bool(qwen_key and qwen_audio_model),
            "provider": "qwen" if (qwen_key and qwen_audio_model) else None,
            "reason": (
                None if (qwen_key and qwen_audio_model)
                else "Voice generation unavailable: configure QWEN_API_KEY and QWEN_MODEL_AUDIO."
            ),
            "fallback": "No voice fallback — voice features are omitted when unavailable.",
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


# ── Qwen defaults ─────────────────────────────────────────────────────────────

QWEN_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_ALT_BASE_URLS = [
    "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1",
]
QWEN_RECOMMENDED_MODELS = {
    "QWEN_MODEL_CHAT":  "qwen3-max",
    "QWEN_MODEL_CODE":  "qwen3-coder-plus",
    "QWEN_MODEL_IMAGE": "qwen-image-plus",
    "QWEN_MODEL_VIDEO": "qwen3-omni-flash",
    "QWEN_MODEL_AUDIO": "qwen3-asr-flash",
}
QWEN_OPTIONAL_MODELS = [
    "qwen3-coder-flash",
    "qwen3-vl-plus",
    "qwen3-omni-flash-realtime",
    "qwen-long-latest",
    "qwen-deep-research",
]


async def async_capabilities_summary(get_secret_fn) -> dict:
    """Async single source of truth for capability availability.

    Reads from saved settings (DB) first, then falls back to environment
    variables.  ``get_secret_fn`` is an async callable that accepts a key name
    and returns the decrypted value or None, e.g.::

        async def _get(key): return await get_secret(db, key)

    This ensures that if a user configures an API key in the Settings UI, the
    capability endpoints immediately reflect the correct state without a restart.
    """
    genx_key = await get_secret_fn("GENX_API_KEY") or os.environ.get("GENX_API_KEY", "")
    qwen_key = await get_secret_fn("QWEN_API_KEY") or os.environ.get("QWEN_API_KEY", "")
    github_pat = await get_secret_fn("GITHUB_PAT") or os.environ.get("GITHUB_PAT", "")
    firecrawl_key = await get_secret_fn("FIRECRAWL_API_KEY") or os.environ.get("FIRECRAWL_API_KEY", "")
    pixabay_key = await get_secret_fn("PIXABAY_API_KEY") or os.environ.get("PIXABAY_API_KEY", "")

    qwen_base_url = (
        await get_secret_fn("QWEN_BASE_URL")
        or os.environ.get("QWEN_BASE_URL", QWEN_DEFAULT_BASE_URL)
    )
    qwen_chat_model = (
        await get_secret_fn("QWEN_MODEL_CHAT")
        or os.environ.get("QWEN_MODEL_CHAT", "")
    )
    qwen_code_model = (
        await get_secret_fn("QWEN_MODEL_CODE")
        or os.environ.get("QWEN_MODEL_CODE", "")
    )
    qwen_image_model = (
        await get_secret_fn("QWEN_MODEL_IMAGE")
        or os.environ.get("QWEN_MODEL_IMAGE", "")
    )
    qwen_video_model = (
        await get_secret_fn("QWEN_MODEL_VIDEO")
        or os.environ.get("QWEN_MODEL_VIDEO", "")
    )
    qwen_audio_model = (
        await get_secret_fn("QWEN_MODEL_AUDIO")
        or os.environ.get("QWEN_MODEL_AUDIO", "")
    )

    genx_available = bool(genx_key)
    qwen_available = bool(qwen_key)
    image_gen_available = genx_available or bool(qwen_key and qwen_image_model)
    video_gen_available = bool(qwen_key and qwen_video_model)
    audio_available = bool(qwen_key and qwen_audio_model)

    def _qwen_detail(model_key: str, model_val: str) -> str | None:
        if not qwen_key:
            return "QWEN_API_KEY not configured"
        if not model_val:
            return f"QWEN_API_KEY is set but {model_key} is not configured"
        return None

    return {
        "text_generation": {
            "available": genx_available,
            "provider": "genx" if genx_available else None,
            "source": "settings" if genx_key else None,
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
            "provider": (
                "genx" if genx_available else ("qwen" if qwen_key and qwen_image_model else None)
            ),
            "reason": (
                None if image_gen_available
                else (
                    _qwen_detail("QWEN_MODEL_IMAGE", qwen_image_model)
                    if qwen_key
                    else "Image generation unavailable: configure GENX_API_KEY or QWEN_API_KEY + QWEN_MODEL_IMAGE."
                )
            ),
            "fallback": "CSS gradients and SVG placeholders are used instead.",
        },
        "video_generation": {
            "available": video_gen_available,
            "provider": "qwen" if video_gen_available else None,
            "reason": (
                None if video_gen_available
                else _qwen_detail("QWEN_MODEL_VIDEO", qwen_video_model)
            ),
            "fallback": "No video fallback — video sections are replaced with static visuals.",
        },
        "audio": {
            "available": audio_available,
            "provider": "qwen" if audio_available else None,
            "reason": (
                None if audio_available
                else _qwen_detail("QWEN_MODEL_AUDIO", qwen_audio_model)
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
        "github_integration": {
            "available": bool(github_pat),
            "provider": "github" if github_pat else None,
            "reason": (
                None if github_pat
                else "GitHub integration unavailable: GITHUB_PAT not configured."
            ),
            "fallback": "File export only — no GitHub push/PR without a PAT.",
        },
        "web_research": {
            "available": bool(firecrawl_key),
            "configured": bool(firecrawl_key),
            "provider": "firecrawl" if firecrawl_key else None,
            "live_status": "key_present_not_tested" if firecrawl_key else "setup_needed",
            "reason": None if firecrawl_key else "Firecrawl unavailable: FIRECRAWL_API_KEY not configured.",
            "fallback": "Scout continues without live web research.",
        },
        "stock_media": {
            "available": bool(pixabay_key),
            "configured": bool(pixabay_key),
            "provider": "pixabay" if pixabay_key else None,
            "live_status": "key_present_not_tested" if pixabay_key else "key_missing",
            "reason": None if pixabay_key else "Pixabay unavailable: PIXABAY_API_KEY not configured.",
            "fallback": "Use AI images if configured or CSS/SVG visuals.",
        },
        "preview_generation": {
            "available": True,
            "provider": "sandbox",
            "reason": None,
            "fallback": "Static HTML preview always available; Vite/React preview requires server.",
        },
        "voice_generation": {
            "available": bool(qwen_key and qwen_audio_model),
            "provider": "qwen" if (qwen_key and qwen_audio_model) else None,
            "reason": (
                None if (qwen_key and qwen_audio_model)
                else _qwen_detail("QWEN_MODEL_AUDIO", qwen_audio_model)
            ),
            "fallback": "No voice fallback — voice features are omitted when unavailable.",
        },
        "qwen": {
            "available": qwen_available,
            "api_key_set": qwen_available,
            "base_url": qwen_base_url or QWEN_DEFAULT_BASE_URL,
            "chat_model": qwen_chat_model,
            "code_model": qwen_code_model,
            "image_model": qwen_image_model,
            "video_model": qwen_video_model,
            "audio_model": qwen_audio_model,
            "missing": [
                k for k, v in {
                    "QWEN_BASE_URL": qwen_base_url,
                    "QWEN_MODEL_CHAT": qwen_chat_model,
                    "QWEN_MODEL_CODE": qwen_code_model,
                    "QWEN_MODEL_IMAGE": qwen_image_model,
                    "QWEN_MODEL_VIDEO": qwen_video_model,
                    "QWEN_MODEL_AUDIO": qwen_audio_model,
                }.items() if not v
            ] if qwen_available else [],
            "reason": None if qwen_available else "QWEN_API_KEY not configured",
        },
    }
