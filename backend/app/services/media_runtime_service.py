"""Runtime media generation and persistence for production builds."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agents.pixabay import search_images, search_videos
from agents.media_storage import safe_filename, validate_upload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _media_dir(workspace: Path) -> Path:
    path = workspace / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _download(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0] or "application/octet-stream"
    return response.content, content_type


def _extension(content_type: str, fallback: str = ".bin") -> str:
    return mimetypes.guess_extension(content_type) or fallback


async def _openai_image_endpoint(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
) -> dict[str, Any] | None:
    if not api_key or not base_url or not model:
        return None
    url = f"{base_url.rstrip('/')}/images/generations"
    payload = {"model": model, "prompt": prompt, "n": 1, "size": "1792x1024"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            return {"ok": False, "provider": provider, "error": f"{provider} image endpoint HTTP {response.status_code}"}
        data = response.json()
    except Exception as exc:
        return {"ok": False, "provider": provider, "error": f"{provider} image generation failed: {exc}"}
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return {"ok": True, "provider": provider, "bytes": base64.b64decode(item["b64_json"]), "content_type": "image/png"}
    if item.get("url"):
        content, content_type = await _download(item["url"])
        return {"ok": True, "provider": provider, "bytes": content, "content_type": content_type, "remote_url": item["url"]}
    return {"ok": False, "provider": provider, "error": f"{provider} returned no image payload"}


def _write_asset(
    workspace: Path,
    *,
    content: bytes,
    content_type: str,
    source: str,
    prompt: str,
    media_type: str,
    remote_url: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ext = _extension(content_type, ".jpg" if media_type == "image" else ".mp4")
    asset_id = uuid.uuid4().hex[:12]
    filename = safe_filename(f"{source}-{asset_id}{ext}")
    validation = validate_upload(filename, content, media_type_override=media_type)
    if not validation.get("ok"):
        raise ValueError(validation.get("error", "Media validation failed"))
    path = _media_dir(workspace) / filename
    path.write_bytes(content)
    return {
        "id": asset_id,
        "source": source,
        "media_type": validation.get("media_type", media_type),
        "mime_type": validation.get("mime", content_type),
        "path": str(path.relative_to(workspace)).replace("\\", "/"),
        "size_bytes": len(content),
        "width": validation.get("width", 0),
        "height": validation.get("height", 0),
        "prompt": prompt,
        "remote_url": remote_url,
        "created_at": _now(),
        **(meta or {}),
    }


async def execute_media_plan(
    workspace_path: str | Path,
    *,
    project_id: str,
    prompt: str,
    sections: list[str] | None = None,
    genx_api_key: str = "",
    genx_base_url: str = "https://query.genx.sh/v1",
    genx_image_model: str = "",
    qwen_api_key: str = "",
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    qwen_image_model: str = "",
    pixabay_api_key: str = "",
    allow_stock_fallback: bool = True,
) -> dict[str, Any]:
    """Create real media assets and persist `media_manifest.json` in a workspace."""
    workspace = Path(workspace_path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    sections = sections or ["hero", "features", "cta"]
    assets: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []

    image_prompt = (
        f"Premium cinematic production media for {prompt}. "
        f"Sections: {', '.join(sections[:6])}. Dark luxury, polished, commercial-ready."
    )
    providers = [
        ("genx", genx_api_key, genx_base_url, genx_image_model or os.environ.get("GENX_MODEL_IMAGE", "")),
        ("qwen", qwen_api_key, qwen_base_url, qwen_image_model),
    ]
    for provider, key, base, model in providers:
        if not key or not model:
            attempts.append({"provider": provider, "ok": False, "reason": "missing key or model"})
            continue
        result = await _openai_image_endpoint(provider=provider, api_key=key, base_url=base, model=model, prompt=image_prompt)
        attempts.append({k: v for k, v in (result or {}).items() if k not in {"bytes"}} or {"provider": provider, "ok": False})
        if result and result.get("ok"):
            assets.append(_write_asset(
                workspace,
                content=result["bytes"],
                content_type=result.get("content_type", "image/png"),
                source=provider,
                prompt=image_prompt,
                media_type="image",
                remote_url=result.get("remote_url", ""),
            ))
            break

    if not assets and allow_stock_fallback and pixabay_api_key:
        images = await search_images(prompt, pixabay_api_key, per_page=3, min_width=1280, min_height=720)
        videos = await search_videos(prompt, pixabay_api_key, per_page=3, min_width=1280, min_height=720)
        for item in images[:2]:
            try:
                content, content_type = await _download(item.get("full_url") or item["url"])
                assets.append(_write_asset(
                    workspace,
                    content=content,
                    content_type=content_type,
                    source="pixabay",
                    prompt=prompt,
                    media_type="image",
                    remote_url=item.get("full_url") or item.get("url", ""),
                    meta={"attribution": item.get("attribution", ""), "tags": item.get("tags", "")},
                ))
            except Exception as exc:
                attempts.append({"provider": "pixabay", "ok": False, "reason": str(exc)})
        for item in videos[:1]:
            try:
                content, content_type = await _download(item["url"])
                assets.append(_write_asset(
                    workspace,
                    content=content,
                    content_type=content_type,
                    source="pixabay",
                    prompt=prompt,
                    media_type="video",
                    remote_url=item.get("url", ""),
                    meta={"attribution": item.get("attribution", ""), "tags": item.get("tags", "")},
                ))
            except Exception as exc:
                attempts.append({"provider": "pixabay_video", "ok": False, "reason": str(exc)})

    injected_files = inject_media_assets(workspace, assets) if assets else []
    manifest = {
        "project_id": project_id,
        "status": "ready" if assets else "failed",
        "assets": assets,
        "attempts": attempts,
        "asset_count": len(assets),
        "injected_files": injected_files,
        "created_at": _now(),
    }
    (workspace / "media_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def inject_media_assets(workspace: Path, assets: list[dict[str, Any]]) -> list[str]:
    """Inject persisted media assets into static HTML/CSS when generated files omit them."""
    changed: list[str] = []
    image = next((a for a in assets if a.get("media_type") in {"image", "logo", "svg"}), None)
    video = next((a for a in assets if a.get("media_type") == "video"), None)
    if not image and not video:
        return changed
    for rel in ("index.html", "public/index.html"):
        path = workspace / rel
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        if "data-amarktai-media-asset" in html:
            return changed
        asset_markup = ""
        if video:
            asset_markup += (
                f'<video data-amarktai-media-asset src="{video["path"]}" autoplay muted loop playsinline '
                'aria-label="Generated background media"></video>'
            )
        if image:
            asset_markup += (
                f'<img data-amarktai-media-asset src="{image["path"]}" alt="Generated visual asset for this build" />'
            )
        if "</main>" in html:
            html = html.replace("</main>", f'<section class="amarktai-generated-media">{asset_markup}</section></main>', 1)
        else:
            html = html.replace("</body>", f'<section class="amarktai-generated-media">{asset_markup}</section></body>', 1)
        path.write_text(html, encoding="utf-8")
        changed.append(rel)
        break
    css_path = workspace / "styles.css"
    css = """
.amarktai-generated-media { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:1rem; padding:clamp(2rem,6vw,5rem); }
.amarktai-generated-media img, .amarktai-generated-media video { width:100%; border-radius:20px; object-fit:cover; box-shadow:0 24px 80px rgba(0,0,0,.32); }
""".strip()
    if css_path.exists() and "amarktai-generated-media" not in css_path.read_text(errors="replace"):
        css_path.write_text(css_path.read_text(encoding="utf-8", errors="replace") + "\n\n" + css + "\n", encoding="utf-8")
        changed.append("styles.css")
    return changed
