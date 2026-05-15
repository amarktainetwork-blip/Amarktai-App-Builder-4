"""Live GenX runtime discovery.

This service is the runtime source of truth for GenX catalog capabilities.
It probes the text model endpoint plus the media category model endpoints and
returns sanitized, dashboard-safe metadata. API keys are never returned.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_GENX_ROOT_URL = "https://query.genx.sh"
GENX_MEDIA_CATEGORIES = ("image", "video", "voice", "audio", "avatar")
PROBE_TIMEOUT = float(os.environ.get("GENX_RUNTIME_PROBE_TIMEOUT", "15"))
_CACHE_TTL = int(os.environ.get("GENX_RUNTIME_PROBE_CACHE_TTL", "120"))
_CACHE: dict[str, Any] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_error(value: Any) -> str:
    text = str(value)
    return re.sub(r"[a-zA-Z0-9_\-]{20,}", "***", text)[:300]


def _root_base(base_url: str | None = None) -> str:
    raw = (base_url or os.environ.get("GENX_BASE_URL") or DEFAULT_GENX_ROOT_URL).strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return DEFAULT_GENX_ROOT_URL
    return raw


def text_models_url(base_url: str | None = None) -> str:
    return f"{_root_base(base_url)}/v1/models"


def category_models_url(category: str, base_url: str | None = None) -> str:
    return f"{_root_base(base_url)}/api/v1/models?category={category}"


def _model_id(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("id", "model", "name", "slug"):
        value = item.get(key)
        if value:
            return str(value).strip()
    return ""


def extract_models(payload: Any, *, category: str = "text") -> list[dict[str, Any]]:
    raw = payload
    if isinstance(payload, dict):
        raw = (
            payload.get("data")
            or payload.get("models")
            or payload.get("items")
            or payload.get("results")
            or payload.get(category)
            or []
        )
    if not isinstance(raw, list):
        return []

    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        model_id = _model_id(item)
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append({
            "id": model_id,
            "category": category,
            "provider": "genx",
            "raw": item if isinstance(item, dict) else {"id": model_id},
        })
    return models


async def _fetch_json(client: httpx.AsyncClient, url: str, api_key: str) -> tuple[bool, int | None, Any, str | None]:
    try:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Amarktai-App-Builder/1.0",
            },
        )
        if response.status_code >= 400:
            return False, response.status_code, None, _sanitize_error(response.text[:200])
        return True, response.status_code, response.json(), None
    except httpx.TimeoutException:
        return False, None, None, "provider_timeout"
    except Exception as exc:
        return False, None, None, _sanitize_error(exc)


async def discover_genx_runtime(
    api_key: str,
    *,
    base_url: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Probe live GenX text and media catalog endpoints."""
    if not api_key:
        return {
            "provider": "genx",
            "configured": False,
            "status": "key_missing",
            "live_status": "key_missing",
            "reason": "GENX_API_KEY not configured",
            "capabilities": {},
            "category_counts": {},
            "models": [],
            "probed_at": _now(),
        }

    root = _root_base(base_url)
    cache_key = f"{root}:{api_key[:8]}"
    now_monotonic = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and not force_refresh and now_monotonic - cached.get("_cached_at_monotonic", 0) < _CACHE_TTL:
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    text_result: dict[str, Any] = {}
    media_results: dict[str, Any] = {}
    all_models: list[dict[str, Any]] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
        ok, http_status, payload, error = await _fetch_json(client, text_models_url(root), api_key)
        text_models = extract_models(payload, category="text") if ok else []
        if ok:
            all_models.extend(text_models)
            text_result = {
                "status": "live_ok",
                "endpoint": "/v1/models",
                "http_status": http_status,
                "model_count": len(text_models),
                "models": [{"id": m["id"], "category": "text"} for m in text_models],
            }
        else:
            errors.append(f"text: {error or http_status}")
            text_result = {
                "status": "provider_timeout" if error == "provider_timeout" else "live_fail",
                "endpoint": "/v1/models",
                "http_status": http_status,
                "model_count": 0,
                "models": [],
                "error": error,
            }

        for category in GENX_MEDIA_CATEGORIES:
            ok, http_status, payload, error = await _fetch_json(client, category_models_url(category, root), api_key)
            models = extract_models(payload, category=category) if ok else []
            if ok:
                all_models.extend(models)
                media_results[category] = {
                    "status": "live_ok",
                    "endpoint": f"/api/v1/models?category={category}",
                    "http_status": http_status,
                    "model_count": len(models),
                    "models": [{"id": m["id"], "category": category} for m in models],
                }
            else:
                errors.append(f"{category}: {error or http_status}")
                media_results[category] = {
                    "status": "provider_timeout" if error == "provider_timeout" else "live_fail",
                    "endpoint": f"/api/v1/models?category={category}",
                    "http_status": http_status,
                    "model_count": 0,
                    "models": [],
                    "error": error,
                }

    seen: set[tuple[str, str]] = set()
    unique_models: list[dict[str, Any]] = []
    for model in all_models:
        key = (model["id"], model["category"])
        if key in seen:
            continue
        seen.add(key)
        unique_models.append(model)

    category_counts = {"text": text_result.get("model_count", 0)}
    category_counts.update({category: data.get("model_count", 0) for category, data in media_results.items()})
    capabilities = {
        "text": category_counts.get("text", 0) > 0,
        "streaming": category_counts.get("text", 0) > 0,
        "image": category_counts.get("image", 0) > 0,
        "video": category_counts.get("video", 0) > 0,
        "voice": category_counts.get("voice", 0) > 0,
        "audio": category_counts.get("audio", 0) > 0,
        "avatar": category_counts.get("avatar", 0) > 0,
        "music": category_counts.get("audio", 0) > 0,
    }
    live_ok = capabilities["text"] or any(capabilities[c] for c in ("image", "video", "voice", "audio", "avatar"))
    status = "live_ok" if live_ok else ("provider_timeout" if any("provider_timeout" in e for e in errors) else "live_fail")
    result = {
        "provider": "genx",
        "configured": True,
        "status": "key_present_live_ok" if status == "live_ok" else status,
        "live_status": status,
        "base_url": root,
        "text": text_result,
        "streaming": {"status": text_result.get("status"), "available": capabilities["streaming"]},
        "media": media_results,
        "capabilities": capabilities,
        "category_counts": category_counts,
        "models": [{"id": m["id"], "category": m["category"], "provider": "genx"} for m in unique_models],
        "errors": errors,
        "reason": None if status == "live_ok" else "; ".join(errors[:4]) or "GenX runtime discovery failed",
        "probed_at": _now(),
    }
    _CACHE[cache_key] = {**result, "_cached_at_monotonic": now_monotonic}
    return result
