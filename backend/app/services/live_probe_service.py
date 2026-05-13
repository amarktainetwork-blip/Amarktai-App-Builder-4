"""
Amarktai App Builder — Live Provider Probe Service.

Performs lightweight, cached live probes against each configured provider.
Results are cached (60–300 s) and can be manually refreshed.

Probe status values:
  key_missing          → no API key/token configured
  key_present_not_tested → key exists but live probe not yet run
  key_present_live_ok  → key exists and a live test call succeeded
  key_present_live_fail → key exists but live test call failed
  provider_timeout     → live probe timed out
  model_missing        → key present but required model not configured
  model_live_ok        → model endpoint responded successfully
  model_live_fail      → model endpoint returned an error

Security:
  - API keys are never logged or returned in responses.
  - Errors are sanitised before returning (no key material).
  - Short timeouts prevent blocking the caller.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("amarktai.live_probe")

# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = int(os.environ.get("PROVIDER_PROBE_CACHE_TTL", "120"))  # seconds

# ── Probe status constants ────────────────────────────────────────────────────

KEY_MISSING          = "key_missing"
KEY_PRESENT_NOT_TESTED = "key_present_not_tested"
KEY_PRESENT_LIVE_OK  = "key_present_live_ok"
KEY_PRESENT_LIVE_FAIL = "key_present_live_fail"
PROVIDER_TIMEOUT     = "provider_timeout"
MODEL_MISSING        = "model_missing"
MODEL_LIVE_OK        = "model_live_ok"
MODEL_LIVE_FAIL      = "model_live_fail"

PROBE_TIMEOUT = float(os.environ.get("PROVIDER_PROBE_TIMEOUT", "10"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask(key: str) -> str:
    """Show only first 6 chars of a key for diagnostic purposes."""
    if not key:
        return ""
    return key[:6] + "***"


def _sanitise_error(err: str) -> str:
    """Remove any potential key material from error messages."""
    # Remove anything that looks like a token (long alphanumeric strings)
    return re.sub(r"[a-zA-Z0-9_\-]{20,}", "***", str(err))[:300]


# ── Individual probes ─────────────────────────────────────────────────────────

async def probe_genx(api_key: str) -> dict[str, Any]:
    """Probe GenX by calling /models endpoint."""
    if not api_key:
        return {"provider": "genx", "status": KEY_MISSING, "probed_at": _now()}

    base_url = os.environ.get("GENX_BASE_URL", "https://query.genx.sh/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as cx:
            r = await cx.get(
                f"{base_url}/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "Amarktai-App-Builder/1.0",
                },
            )
        if r.status_code == 200:
            data = r.json()
            models = data.get("data", data) if isinstance(data, dict) else data
            model_count = len(models) if isinstance(models, list) else 0
            return {
                "provider": "genx",
                "status": KEY_PRESENT_LIVE_OK,
                "model_count": model_count,
                "key_prefix": _mask(api_key),
                "probed_at": _now(),
            }
        return {
            "provider": "genx",
            "status": KEY_PRESENT_LIVE_FAIL,
            "http_status": r.status_code,
            "error": _sanitise_error(r.text[:200]),
            "probed_at": _now(),
        }
    except httpx.TimeoutException:
        return {"provider": "genx", "status": PROVIDER_TIMEOUT, "probed_at": _now()}
    except Exception as exc:
        return {
            "provider": "genx",
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": _sanitise_error(str(exc)),
            "probed_at": _now(),
        }


async def probe_qwen(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Probe Qwen by listing available models."""
    if not api_key:
        return {"provider": "qwen", "status": KEY_MISSING, "probed_at": _now()}

    url = (base_url or os.environ.get(
        "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )).rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as cx:
            r = await cx.get(
                f"{url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            data = r.json()
            models = data.get("data", [])
            return {
                "provider": "qwen",
                "status": KEY_PRESENT_LIVE_OK,
                "model_count": len(models),
                "key_prefix": _mask(api_key),
                "probed_at": _now(),
            }
        return {
            "provider": "qwen",
            "status": KEY_PRESENT_LIVE_FAIL,
            "http_status": r.status_code,
            "error": _sanitise_error(r.text[:200]),
            "probed_at": _now(),
        }
    except httpx.TimeoutException:
        return {"provider": "qwen", "status": PROVIDER_TIMEOUT, "probed_at": _now()}
    except Exception as exc:
        return {
            "provider": "qwen",
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": _sanitise_error(str(exc)),
            "probed_at": _now(),
        }


async def probe_github(pat: str) -> dict[str, Any]:
    """Probe GitHub by calling /user endpoint."""
    if not pat:
        return {"provider": "github", "status": KEY_MISSING, "probed_at": _now()}

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as cx:
            r = await cx.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if r.status_code == 200:
            data = r.json()
            return {
                "provider": "github",
                "status": KEY_PRESENT_LIVE_OK,
                "login": data.get("login", ""),
                "scopes": r.headers.get("x-oauth-scopes", ""),
                "probed_at": _now(),
            }
        return {
            "provider": "github",
            "status": KEY_PRESENT_LIVE_FAIL,
            "http_status": r.status_code,
            "error": _sanitise_error(r.text[:200]),
            "probed_at": _now(),
        }
    except httpx.TimeoutException:
        return {"provider": "github", "status": PROVIDER_TIMEOUT, "probed_at": _now()}
    except Exception as exc:
        return {
            "provider": "github",
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": _sanitise_error(str(exc)),
            "probed_at": _now(),
        }


async def probe_brave(api_key: str) -> dict[str, Any]:
    """Probe Brave Search API with a minimal search call."""
    if not api_key:
        return {"provider": "brave", "status": KEY_MISSING, "probed_at": _now()}

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as cx:
            r = await cx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": "test", "count": "1"},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
        if r.status_code in (200, 202):
            return {
                "provider": "brave",
                "status": KEY_PRESENT_LIVE_OK,
                "key_prefix": _mask(api_key),
                "probed_at": _now(),
            }
        return {
            "provider": "brave",
            "status": KEY_PRESENT_LIVE_FAIL,
            "http_status": r.status_code,
            "error": _sanitise_error(r.text[:200]),
            "probed_at": _now(),
        }
    except httpx.TimeoutException:
        return {"provider": "brave", "status": PROVIDER_TIMEOUT, "probed_at": _now()}
    except Exception as exc:
        return {
            "provider": "brave",
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": _sanitise_error(str(exc)),
            "probed_at": _now(),
        }


async def probe_pixabay(api_key: str) -> dict[str, Any]:
    """Probe Pixabay API with a minimal search call."""
    if not api_key:
        return {"provider": "pixabay", "status": KEY_MISSING, "probed_at": _now()}

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as cx:
            r = await cx.get(
                "https://pixabay.com/api/",
                params={"key": api_key, "q": "test", "per_page": "3"},
            )
        if r.status_code == 200:
            return {
                "provider": "pixabay",
                "status": KEY_PRESENT_LIVE_OK,
                "key_prefix": _mask(api_key),
                "probed_at": _now(),
            }
        return {
            "provider": "pixabay",
            "status": KEY_PRESENT_LIVE_FAIL,
            "http_status": r.status_code,
            "error": _sanitise_error(r.text[:200]),
            "probed_at": _now(),
        }
    except httpx.TimeoutException:
        return {"provider": "pixabay", "status": PROVIDER_TIMEOUT, "probed_at": _now()}
    except Exception as exc:
        return {
            "provider": "pixabay",
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": _sanitise_error(str(exc)),
            "probed_at": _now(),
        }


# ── Orchestrated multi-probe ──────────────────────────────────────────────────

async def probe_all_providers(
    genx_key: str = "",
    qwen_key: str = "",
    github_pat: str = "",
    brave_key: str = "",
    pixabay_key: str = "",
    qwen_base_url: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Run all provider probes concurrently and return a combined status dict.
    Results are cached for PROVIDER_PROBE_CACHE_TTL seconds.
    """
    cache_key = "all_providers"
    now = time.monotonic()

    if not force_refresh and cache_key in _CACHE:
        cached = _CACHE[cache_key]
        age = now - cached.get("_cached_at_monotonic", 0)
        if age < _CACHE_TTL:
            return {k: v for k, v in cached.items() if not k.startswith("_")}

    results = await asyncio.gather(
        probe_genx(genx_key),
        probe_qwen(qwen_key, qwen_base_url),
        probe_github(github_pat),
        probe_brave(brave_key),
        probe_pixabay(pixabay_key),
        return_exceptions=True,
    )

    combined: dict[str, Any] = {}
    providers = ["genx", "qwen", "github", "brave", "pixabay"]
    for i, (prov, res) in enumerate(zip(providers, results)):
        if isinstance(res, Exception):
            combined[prov] = {
                "provider": prov,
                "status": KEY_PRESENT_LIVE_FAIL,
                "error": _sanitise_error(str(res)),
                "probed_at": _now(),
            }
        else:
            combined[prov] = res

    combined["probed_at"] = _now()
    combined["cache_ttl_seconds"] = _CACHE_TTL

    _CACHE[cache_key] = {**combined, "_cached_at_monotonic": now}
    return combined


async def probe_single_provider(
    provider: str,
    genx_key: str = "",
    qwen_key: str = "",
    github_pat: str = "",
    brave_key: str = "",
    pixabay_key: str = "",
    qwen_base_url: str | None = None,
) -> dict[str, Any]:
    """Probe a single provider by name."""
    probes = {
        "genx":    lambda: probe_genx(genx_key),
        "qwen":    lambda: probe_qwen(qwen_key, qwen_base_url),
        "github":  lambda: probe_github(github_pat),
        "brave":   lambda: probe_brave(brave_key),
        "pixabay": lambda: probe_pixabay(pixabay_key),
    }
    if provider not in probes:
        return {
            "provider": provider,
            "status": KEY_PRESENT_LIVE_FAIL,
            "error": f"Unknown provider: {provider!r}",
        }

    cache_key = f"provider_{provider}"
    now = time.monotonic()
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        age = now - cached.get("_cached_at_monotonic", 0)
        if age < _CACHE_TTL:
            return {k: v for k, v in cached.items() if not k.startswith("_")}

    result = await probes[provider]()
    _CACHE[cache_key] = {**result, "_cached_at_monotonic": now}
    return result
