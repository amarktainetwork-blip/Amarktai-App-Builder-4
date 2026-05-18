"""GenX async media job execution helpers.

The Media Director uses this service before falling back to Qwen/Pixabay. It
submits jobs to GenX, polls for completion, and returns downloadable bytes with
sanitized job metadata for persistence into media manifests.
"""
from __future__ import annotations

import base64
import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.genx_live_probe_service import _root_base

GENX_GENERATE_TIMEOUT = float(os.environ.get("GENX_GENERATE_TIMEOUT", "90"))
GENX_JOB_TIMEOUT = float(os.environ.get("GENX_JOB_TIMEOUT", "180"))
GENX_JOB_POLL_INTERVAL = float(os.environ.get("GENX_JOB_POLL_INTERVAL", "3"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_error(value: Any) -> str:
    text = str(value)
    return re.sub(r"[a-zA-Z0-9_\-]{20,}", "***", text)[:300]


def generate_url(base_url: str | None = None) -> str:
    return f"{_root_base(base_url)}/api/v1/generate"


def job_url(job_id: str, base_url: str | None = None) -> str:
    return f"{_root_base(base_url)}/api/v1/jobs/{job_id}"


def _pick(data: Any, *paths: str) -> Any:
    for path in paths:
        cur = data
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur:
            return cur
    return None


def _result_url(data: dict[str, Any]) -> str:
    value = _pick(
        data,
        "result_url",
        "file_url",
        "url",
        "output.url",
        "output.result_url",
        "result.url",
        "asset.url",
    )
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(_pick(first, "url", "result_url", "file_url") or "")
    return str(value or "")


def _base64_payload(data: dict[str, Any]) -> str:
    value = _pick(data, "b64_json", "base64", "data.b64_json", "output.b64_json", "result.b64_json")
    if isinstance(value, str):
        return value
    return ""


def _job_id(data: dict[str, Any]) -> str:
    return str(_pick(data, "job_id", "jobId", "id", "data.job_id", "job.id") or "")


def _job_status(data: dict[str, Any]) -> str:
    return str(_pick(data, "status", "job.status", "data.status") or "").lower()


def _default_content_type(category: str) -> str:
    if category == "image":
        return "image/png"
    if category == "video":
        return "video/mp4"
    if category in {"voice", "audio"}:
        return "audio/mpeg"
    return "application/octet-stream"


def build_genx_generate_payload(
    *,
    model: str,
    prompt: str,
    category: str = "image",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the GenX /api/v1/generate payload.

    GenX media generation requires provider-specific inputs under ``params``.
    Keep the legacy top-level fields as compatibility hints, but never submit a
    media job without params because the live provider rejects that shape.
    """
    params = {"prompt": prompt, **(extra or {})}
    return {
        "model": model,
        "category": category,
        "prompt": prompt,
        "params": params,
    }


async def _download(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=GENX_GENERATE_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.content, response.headers.get("content-type", "").split(";")[0] or "application/octet-stream"


async def generate_genx_media_job(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    prompt: str,
    category: str = "image",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not api_key:
        return {"ok": False, "provider": "genx", "error": "GENX_API_KEY not configured"}
    if not model:
        return {"ok": False, "provider": "genx", "error": f"No GenX {category} model configured"}

    payload = build_genx_generate_payload(
        model=model,
        prompt=prompt,
        category=category,
        extra=extra,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Amarktai-App-Builder/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=GENX_GENERATE_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(generate_url(base_url), json=payload, headers=headers)
            if response.status_code >= 400:
                return {
                    "ok": False,
                    "provider": "genx",
                    "model": model,
                    "category": category,
                    "status": "submit_failed",
                    "error": f"GenX generate HTTP {response.status_code}: {sanitize_error(response.text[:200])}",
                    "created_at": _now(),
                }
            data = response.json()

            b64 = _base64_payload(data)
            if b64:
                return {
                    "ok": True,
                    "provider": "genx",
                    "model": model,
                    "category": category,
                    "status": "succeeded",
                    "bytes": base64.b64decode(b64),
                    "content_type": _default_content_type(category),
                    "created_at": _now(),
                }

            result_url = _result_url(data)
            if result_url:
                content, content_type = await _download(result_url)
                return {
                    "ok": True,
                    "provider": "genx",
                    "model": model,
                    "category": category,
                    "status": "succeeded",
                    "result_url": result_url,
                    "bytes": content,
                    "content_type": content_type,
                    "created_at": _now(),
                }

            job_id = _job_id(data)
            if not job_id:
                return {
                    "ok": False,
                    "provider": "genx",
                    "model": model,
                    "category": category,
                    "status": "no_job_id",
                    "error": "GenX generate returned neither job_id nor result payload",
                    "created_at": _now(),
                }

            deadline = time.monotonic() + GENX_JOB_TIMEOUT
            last_job: dict[str, Any] = {}
            while time.monotonic() < deadline:
                job_response = await client.get(job_url(job_id, base_url), headers=headers)
                if job_response.status_code >= 400:
                    return {
                        "ok": False,
                        "provider": "genx",
                        "model": model,
                        "category": category,
                        "job_id": job_id,
                        "status": "poll_failed",
                        "error": f"GenX job HTTP {job_response.status_code}: {sanitize_error(job_response.text[:200])}",
                        "created_at": _now(),
                    }
                last_job = job_response.json()
                status = _job_status(last_job)
                if status in {"succeeded", "success", "completed", "complete", "done"}:
                    result_url = _result_url(last_job)
                    b64 = _base64_payload(last_job)
                    if b64:
                        return {
                            "ok": True,
                            "provider": "genx",
                            "model": model,
                            "category": category,
                            "job_id": job_id,
                            "status": "succeeded",
                            "bytes": base64.b64decode(b64),
                            "content_type": _default_content_type(category),
                            "created_at": _now(),
                        }
                    if result_url:
                        content, content_type = await _download(result_url)
                        return {
                            "ok": True,
                            "provider": "genx",
                            "model": model,
                            "category": category,
                            "job_id": job_id,
                            "status": "succeeded",
                            "result_url": result_url,
                            "bytes": content,
                            "content_type": content_type,
                            "created_at": _now(),
                        }
                    return {
                        "ok": False,
                        "provider": "genx",
                        "model": model,
                        "category": category,
                        "job_id": job_id,
                        "status": "missing_result",
                        "error": "GenX job completed without a result_url or file payload",
                        "created_at": _now(),
                    }
                if status in {"failed", "error", "cancelled", "canceled"}:
                    return {
                        "ok": False,
                        "provider": "genx",
                        "model": model,
                        "category": category,
                        "job_id": job_id,
                        "status": status,
                        "error": sanitize_error(_pick(last_job, "error", "message", "reason") or "GenX job failed"),
                        "created_at": _now(),
                    }
                await asyncio.sleep(GENX_JOB_POLL_INTERVAL)

            return {
                "ok": False,
                "provider": "genx",
                "model": model,
                "category": category,
                "job_id": job_id,
                "status": "timeout",
                "error": f"GenX job timed out after {int(GENX_JOB_TIMEOUT)} seconds",
                "created_at": _now(),
            }
    except httpx.TimeoutException:
        return {"ok": False, "provider": "genx", "model": model, "category": category, "status": "timeout", "error": "GenX request timed out", "created_at": _now()}
    except Exception as exc:
        return {"ok": False, "provider": "genx", "model": model, "category": category, "status": "failed", "error": sanitize_error(exc), "created_at": _now()}
