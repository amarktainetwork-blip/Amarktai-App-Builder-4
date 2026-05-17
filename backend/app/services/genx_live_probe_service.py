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


def _flatten_values(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(_flatten_values(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(_flatten_values(item))
    elif value is not None:
        out.append(str(value))
    return out


def _modalities(raw: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    input_keys = ("input", "inputs", "input_modalities", "input_types", "input_type", "source_modalities")
    output_keys = ("output", "outputs", "output_modalities", "output_types", "output_type", "target_modalities")
    all_values = _flatten_values(raw)
    input_values: list[str] = []
    output_values: list[str] = []
    for key in input_keys:
        input_values.extend(_flatten_values(raw.get(key)))
    for key in output_keys:
        output_values.extend(_flatten_values(raw.get(key)))

    def normalise(values: list[str]) -> set[str]:
        joined = " ".join(values).lower().replace("_", " ").replace("-", " ")
        found: set[str] = set()
        for token in ("text", "image", "audio", "voice", "video", "avatar", "music", "speech"):
            if re.search(rf"\b{token}\b", joined):
                found.add(token)
        if "tts" in joined:
            found.update({"voice", "audio"})
        if "asr" in joined or "transcription" in joined or "transcribe" in joined:
            found.update({"speech", "audio"})
        return found

    return normalise(input_values), normalise(output_values), normalise(all_values)


def classify_genx_model_capabilities(model: dict[str, Any]) -> list[str]:
    """Infer runtime capabilities from live GenX model metadata.

    GenX can expose multi-modal models under broader categories. For example,
    `kling-avatar-v2-pro` is discovered under video but is specifically an
    image+audio -> video avatar model. This classifier keeps that distinction
    without inventing support when no matching model is live-discovered.
    """
    model_id = str(model.get("id") or model.get("model") or "").lower()
    category = str(model.get("category") or "").lower()
    raw = model.get("raw") if isinstance(model.get("raw"), dict) else {}
    raw_text = " ".join(_flatten_values(raw)).lower().replace("_", " ").replace("-", " ")
    inputs, outputs, modalities = _modalities(raw)
    caps: set[str] = set()

    if category == "text":
        caps.update({"text", "reasoning", "streaming", "tool_use", "repo_analysis"})
    if category == "image" or re.search(r"\b(image|img|imagine|recraft|nano banana|gpt image|genxlm pro v1 img)\b", f"{model_id} {raw_text}"):
        caps.add("image")
    if category == "video" or re.search(r"\b(video|veo|kling|seedance|pixverse|i2v)\b", f"{model_id} {raw_text}"):
        caps.add("video")
    if category in {"voice", "audio"}:
        caps.add("audio")
    if category == "voice" or re.search(r"\b(tts|voice|aura|grok tts|genxlm voice)\b", f"{model_id} {raw_text}"):
        caps.update({"voice", "audio"})
    if category == "audio" or re.search(r"\b(audio|music|lyria|asr|speech|whisper)\b", f"{model_id} {raw_text}"):
        caps.add("audio")
    if re.search(r"\b(asr|transcrib|speech to text|genxlm pro v1 tr)\b", f"{model_id} {raw_text}"):
        caps.update({"speech_to_text", "audio_transcription", "audio"})

    input_has_image = "image" in inputs or "image" in modalities or "i2v" in model_id
    input_has_audio = bool({"audio", "voice", "speech"} & (inputs | modalities))
    output_has_video = "video" in outputs or "video" in modalities or "video" in caps
    if input_has_image and output_has_video:
        caps.update({"video", "image_to_video"})
    if (input_has_image and input_has_audio and output_has_video) or "kling-avatar" in model_id or category == "avatar":
        caps.update({"avatar", "avatar_generation", "video", "audio_image_to_video"})

    if "avatar" in raw_text and output_has_video:
        caps.update({"avatar", "avatar_generation", "video"})
    if "music" in caps or "lyria" in model_id:
        caps.update({"audio", "music"})

    order = [
        "text", "reasoning", "streaming", "tool_use", "repo_analysis",
        "image", "video", "image_to_video", "audio_image_to_video",
        "audio", "voice", "speech_to_text", "audio_transcription",
        "avatar", "avatar_generation", "music",
    ]
    return [cap for cap in order if cap in caps]


def build_capability_index(models: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        caps = classify_genx_model_capabilities(model)
        model["capabilities"] = caps
        for cap in caps:
            index.setdefault(cap, []).append({
                "id": model["id"],
                "category": model.get("category"),
                "provider": "genx",
                "capabilities": caps,
            })
    return index


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
                "models": [
                    {"id": m["id"], "category": "text", "capabilities": classify_genx_model_capabilities(m)}
                    for m in text_models
                ],
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
                    "models": [
                        {"id": m["id"], "category": category, "capabilities": classify_genx_model_capabilities(m)}
                        for m in models
                    ],
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

    capability_models = build_capability_index(unique_models)
    category_counts = {"text": text_result.get("model_count", 0)}
    category_counts.update({category: data.get("model_count", 0) for category, data in media_results.items()})
    capability_counts = {cap: len(items) for cap, items in capability_models.items()}
    capabilities = {
        "text": capability_counts.get("text", 0) > 0 or category_counts.get("text", 0) > 0,
        "streaming": capability_counts.get("streaming", 0) > 0 or category_counts.get("text", 0) > 0,
        "image": capability_counts.get("image", 0) > 0,
        "video": capability_counts.get("video", 0) > 0,
        "voice": capability_counts.get("voice", 0) > 0,
        "audio": capability_counts.get("audio", 0) > 0,
        "speech_to_text": capability_counts.get("speech_to_text", 0) > 0,
        "audio_transcription": capability_counts.get("audio_transcription", 0) > 0,
        "image_to_video": capability_counts.get("image_to_video", 0) > 0,
        "audio_image_to_video": capability_counts.get("audio_image_to_video", 0) > 0,
        "avatar": capability_counts.get("avatar", 0) > 0 or capability_counts.get("avatar_generation", 0) > 0,
        "music": capability_counts.get("music", 0) > 0 or category_counts.get("audio", 0) > 0,
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
        "capability_counts": capability_counts,
        "capability_models": capability_models,
        "models": [
            {
                "id": m["id"],
                "category": m["category"],
                "provider": "genx",
                "capabilities": m.get("capabilities", []),
            }
            for m in unique_models
        ],
        "errors": errors,
        "reason": None if status == "live_ok" else "; ".join(errors[:4]) or "GenX runtime discovery failed",
        "probed_at": _now(),
    }
    _CACHE[cache_key] = {**result, "_cached_at_monotonic": now_monotonic}
    return result
