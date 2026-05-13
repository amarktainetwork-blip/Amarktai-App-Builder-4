from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.capability_registry import (
    QWEN_DEFAULT_BASE_URL,
    get_registry,
)


SecretResolver = Callable[[str], Awaitable[dict[str, Any]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe_status(provider: str, configured: bool, source: str, cached_probes: dict[str, Any] | None) -> tuple[str, str | None, str | None]:
    if source == "decrypt_failed":
        return "decrypt_failed", "Stored setting cannot be decrypted. Clean up or rotate settings.", None
    if not configured:
        return "key_missing", f"{provider.upper()} key not configured", None
    probe = (cached_probes or {}).get(provider)
    if isinstance(probe, dict):
        raw = probe.get("status")
        if raw == "key_present_live_ok":
            return "live_ok", None, probe.get("probed_at")
        if raw in {"key_present_live_fail", "provider_timeout", "model_live_fail"}:
            return "live_fail", probe.get("error") or f"{provider} live validation failed", probe.get("probed_at")
        if raw == "key_missing":
            return "key_missing", f"{provider.upper()} key not configured", probe.get("probed_at")
    return "not_tested", "Configured but not live tested", None


def _availability(provider: dict[str, Any]) -> bool:
    return bool(provider.get("configured")) and provider.get("live_status") == "live_ok"


class CapabilityTruthService:
    """Single runtime truth source for provider, capability, and model state."""

    def __init__(
        self,
        secret_resolver: SecretResolver,
        *,
        cached_probes: dict[str, Any] | None = None,
    ) -> None:
        self.secret_resolver = secret_resolver
        self.cached_probes = cached_probes or {}

    async def build(self) -> dict[str, Any]:
        resolved = {key: await self._resolve(key) for key in [
            "GENX_API_KEY",
            "GITHUB_PAT",
            "BRAVE_SEARCH_API_KEY",
            "PIXABAY_API_KEY",
            "QWEN_API_KEY",
            "QWEN_BASE_URL",
            "QWEN_MODEL_CHAT",
            "QWEN_MODEL_CODE",
            "QWEN_MODEL_IMAGE",
            "QWEN_MODEL_VIDEO",
            "QWEN_MODEL_AUDIO",
        ]}

        providers = {
            "genx": self._provider("genx", resolved["GENX_API_KEY"], "GENX_API_KEY"),
            "github": self._provider("github", resolved["GITHUB_PAT"], "GITHUB_PAT"),
            "brave": self._provider("brave", resolved["BRAVE_SEARCH_API_KEY"], "BRAVE_SEARCH_API_KEY"),
            "pixabay": self._provider("pixabay", resolved["PIXABAY_API_KEY"], "PIXABAY_API_KEY"),
            "qwen": self._provider("qwen", resolved["QWEN_API_KEY"], "QWEN_API_KEY"),
        }

        qwen_models = {
            "chat_model": resolved["QWEN_MODEL_CHAT"].get("value") or os.environ.get("QWEN_MODEL_CHAT", ""),
            "code_model": resolved["QWEN_MODEL_CODE"].get("value") or os.environ.get("QWEN_MODEL_CODE", ""),
            "image_model": resolved["QWEN_MODEL_IMAGE"].get("value") or os.environ.get("QWEN_MODEL_IMAGE", ""),
            "video_model": resolved["QWEN_MODEL_VIDEO"].get("value") or os.environ.get("QWEN_MODEL_VIDEO", ""),
            "audio_model": resolved["QWEN_MODEL_AUDIO"].get("value") or os.environ.get("QWEN_MODEL_AUDIO", ""),
            "base_url": resolved["QWEN_BASE_URL"].get("value") or os.environ.get("QWEN_BASE_URL", QWEN_DEFAULT_BASE_URL),
        }

        capabilities = self._capabilities(providers, qwen_models)
        models = self._models(providers)
        warnings = []
        for key, item in resolved.items():
            if item.get("error") == "decrypt_failed" or item.get("source") == "decrypt_failed":
                warnings.append(f"{key} stored setting cannot be decrypted; env fallback used when available.")

        return {
            "providers": providers,
            "capabilities": capabilities,
            "summary": capabilities,
            "models": models,
            "registry": models,
            "settings": {
                key: {
                    "configured": bool(value.get("configured")),
                    "source": value.get("source"),
                    "status": value.get("stored_status") or value.get("source"),
                    "error": value.get("error"),
                }
                for key, value in resolved.items()
            },
            "warnings": warnings,
            "errors": [],
            "timestamp": _now(),
        }

    async def _resolve(self, key: str) -> dict[str, Any]:
        try:
            return await self.secret_resolver(key)
        except Exception as exc:
            env_value = os.environ.get(key)
            if env_value:
                return {"value": env_value, "source": "env", "configured": True, "error": f"resolver_failed: {type(exc).__name__}"}
            return {"value": None, "source": "missing", "configured": False, "error": f"resolver_failed: {type(exc).__name__}"}

    def _provider(self, name: str, resolved: dict[str, Any], env_key: str) -> dict[str, Any]:
        source = resolved.get("source") or "missing"
        configured = bool(resolved.get("configured"))
        live_status, reason, last_checked_at = _probe_status(name, configured, source, self.cached_probes)
        if live_status == "key_missing":
            reason = f"{env_key} not configured"
        return {
            "configured": configured,
            "source": source,
            "live_status": live_status,
            "reason": reason,
            "last_checked_at": last_checked_at,
            "env_key": env_key,
            "error": resolved.get("error"),
        }

    def _capabilities(self, providers: dict[str, dict[str, Any]], qwen_models: dict[str, str]) -> dict[str, Any]:
        genx_ok = _availability(providers["genx"])
        github_ok = _availability(providers["github"])
        brave_ok = _availability(providers["brave"])
        pixabay_ok = _availability(providers["pixabay"])
        qwen_ok = _availability(providers["qwen"])

        def cap(available: bool, provider: str | None, reason: str, fallback: str = "") -> dict[str, Any]:
            return {
                "available": available,
                "configured": bool(provider and providers.get(provider, {}).get("configured")),
                "provider": provider if available else None,
                "live_status": providers.get(provider or "", {}).get("live_status") if provider else None,
                "reason": None if available else reason,
                "fallback": fallback,
            }

        return {
            "text_generation": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "reasoning": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "vision": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "repo_analysis": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "long_context": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "tool_use": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "streaming": cap(genx_ok, "genx", providers["genx"]["reason"] or "GENX_API_KEY not configured"),
            "image_generation": cap(
                genx_ok or (qwen_ok and bool(qwen_models["image_model"])),
                "genx" if genx_ok else "qwen",
                providers["genx"]["reason"] or providers["qwen"]["reason"] or "Image provider not configured",
                "CSS/SVG visuals remain available.",
            ),
            "video_generation": cap(qwen_ok and bool(qwen_models["video_model"]), "qwen", "QWEN_API_KEY and QWEN_MODEL_VIDEO are required."),
            "audio": cap(qwen_ok and bool(qwen_models["audio_model"]), "qwen", "QWEN_API_KEY and QWEN_MODEL_AUDIO are required."),
            "voice_generation": cap(qwen_ok and bool(qwen_models["audio_model"]), "qwen", "QWEN_API_KEY and QWEN_MODEL_AUDIO are required."),
            "github_integration": cap(github_ok, "github", providers["github"]["reason"] or "GITHUB_PAT not configured", "File export remains available."),
            "web_research": cap(brave_ok, "brave", providers["brave"]["reason"] or "BRAVE_SEARCH_API_KEY not configured", "Scout continues without live web research."),
            "stock_media": cap(pixabay_ok, "pixabay", providers["pixabay"]["reason"] or "PIXABAY_API_KEY not configured", "Use AI images if available or CSS/SVG visuals."),
            "preview_generation": {"available": True, "configured": True, "provider": "sandbox", "live_status": "local", "reason": None, "fallback": ""},
            "qwen": {
                "available": qwen_ok,
                "configured": providers["qwen"]["configured"],
                "provider": "qwen" if qwen_ok else None,
                "live_status": providers["qwen"]["live_status"],
                "reason": None if qwen_ok else providers["qwen"]["reason"],
                "base_url": qwen_models["base_url"],
                **qwen_models,
                "missing": [] if not providers["qwen"]["configured"] else [
                    key for key, value in {
                        "QWEN_MODEL_CHAT": qwen_models["chat_model"],
                        "QWEN_MODEL_CODE": qwen_models["code_model"],
                        "QWEN_MODEL_IMAGE": qwen_models["image_model"],
                        "QWEN_MODEL_VIDEO": qwen_models["video_model"],
                        "QWEN_MODEL_AUDIO": qwen_models["audio_model"],
                    }.items() if not value
                ],
            },
        }

    def _models(self, providers: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        models = []
        for item in get_registry():
            provider = item.get("provider")
            provider_state = providers.get(provider, {})
            provider_available = _availability(provider_state)
            reason = None
            if not provider_state.get("configured"):
                reason = f"{provider.upper()}_API_KEY not configured" if provider == "genx" else f"{provider.upper()} provider key not configured"
                if provider == "qwen":
                    reason = "QWEN_API_KEY not configured"
            elif provider_state.get("live_status") == "decrypt_failed":
                reason = "Provider setting cannot be decrypted"
            elif provider_state.get("live_status") == "live_fail":
                reason = provider_state.get("reason") or "Provider live validation failed"
            annotated = {
                **item,
                "known": True,
                "configured_model": provider_state.get("configured", False),
                "available": provider_available,
                "provider_source": provider_state.get("source"),
                "provider_live_status": provider_state.get("live_status"),
                "unavailable_reason": None if provider_available else reason,
            }
            models.append(annotated)
        return models
