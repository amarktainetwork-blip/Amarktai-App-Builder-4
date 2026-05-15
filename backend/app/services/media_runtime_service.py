"""Runtime media generation and persistence for production builds."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agents.pixabay import search_images, search_videos
from agents.media_storage import safe_filename, validate_upload
from app.services.genx_live_probe_service import discover_genx_runtime
from app.services.genx_runtime_service import generate_genx_media_job


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


def _approved_asset_count(assets: list[dict[str, Any]]) -> int:
    return len([
        asset for asset in assets
        if asset.get("media_type") in {"image", "video", "audio", "logo"}
        and Path(str(asset.get("path", ""))).suffix.lower() != ".svg"
    ])


def _compact_media_query(prompt: str, sections: list[str]) -> str:
    """Create a short stock-media query instead of sending an entire long user prompt to Pixabay."""
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", prompt or "").lower()
    stop = {
        "build", "create", "page", "landing", "website", "must", "include", "generated",
        "system", "itself", "using", "live", "with", "and", "the", "for", "our", "all",
        "capabilities", "requirements", "mandatory", "production", "ready"
    }
    words = [w for w in text.split() if len(w) > 3 and w not in stop]
    preferred = [w for w in words if w in {
        "ai", "artificial", "intelligence", "software", "video", "voice", "audio",
        "image", "robot", "technology", "coding", "automation", "dashboard",
        "futuristic", "digital", "network", "studio", "creative"
    }]
    selected = preferred[:6] or words[:6] or ["artificial", "intelligence", "technology"]
    return " ".join(selected[:8])


def _media_queries(prompt: str, sections: list[str]) -> list[str]:
    base = _compact_media_query(prompt, sections)
    queries = [
        base,
        "artificial intelligence technology",
        "futuristic software dashboard",
        "digital media studio",
        "robot artificial intelligence",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = " ".join(str(q).split()).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


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
            if provider == "genx" and key:
                try:
                    runtime = await discover_genx_runtime(key, base_url=base)
                    image_models = runtime.get("media", {}).get("image", {}).get("models", [])
                    model = (image_models[0] or {}).get("id", "") if image_models else ""
                except Exception as exc:
                    attempts.append({"provider": "genx_runtime_discovery", "ok": False, "reason": str(exc)})
            if not key or not model:
                attempts.append({"provider": provider, "ok": False, "reason": "missing key or model"})
                continue
        if provider == "genx":
            result = await generate_genx_media_job(
                api_key=key,
                base_url=base,
                model=model,
                prompt=image_prompt,
                category="image",
                extra={"size": "1792x1024"},
            )
        else:
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
                remote_url=result.get("remote_url", "") or result.get("result_url", ""),
                meta={
                    "provider": provider,
                    "model": model,
                    "job_id": result.get("job_id", ""),
                    "status": result.get("status", "succeeded"),
                    "result_url": result.get("result_url", ""),
                } if provider == "genx" else None,
            ))
            if _approved_asset_count(assets) >= 3:
                break

    if _approved_asset_count(assets) < 3 and allow_stock_fallback and pixabay_api_key:
        selected_images: list[dict[str, Any]] = []
        selected_videos: list[dict[str, Any]] = []
        for query in _media_queries(prompt, sections):
            try:
                images = await search_images(query, pixabay_api_key, per_page=8, min_width=1024, min_height=576)
                videos = await search_videos(query, pixabay_api_key, per_page=3, min_width=1024, min_height=576)
                attempts.append({
                    "provider": "pixabay_search",
                    "ok": True,
                    "query": query,
                    "images_found": len(images),
                    "videos_found": len(videos),
                })
                selected_images.extend(images)
                selected_videos.extend(videos)
                if len(selected_images) >= 6:
                    break
            except Exception as exc:
                attempts.append({"provider": "pixabay_search", "ok": False, "query": query, "reason": str(exc)})

        seen_remote: set[str] = set()
        for item in selected_images:
            if _approved_asset_count(assets) >= 3:
                break
            remote = item.get("full_url") or item.get("url", "")
            if not remote or remote in seen_remote:
                continue
            seen_remote.add(remote)
            try:
                content, content_type = await _download(remote)
                written = _write_asset(
                    workspace,
                    content=content,
                    content_type=content_type,
                    source="pixabay",
                    prompt=prompt,
                    media_type="image",
                    remote_url=remote,
                    meta={"attribution": item.get("attribution", ""), "tags": item.get("tags", "")},
                )
                if Path(written.get("path", "")).suffix.lower() == ".svg":
                    attempts.append({"provider": "pixabay", "ok": False, "remote_url": remote, "reason": "SVG assets do not count as premium persisted media."})
                else:
                    attempts.append({"provider": "pixabay", "ok": True, "remote_url": remote, "path": written.get("path")})
                assets.append(written)
            except Exception as exc:
                attempts.append({"provider": "pixabay", "ok": False, "remote_url": remote, "reason": str(exc)})

        for item in selected_videos[:1]:
            remote = item.get("url", "")
            if not remote:
                continue
            try:
                content, content_type = await _download(remote)
                written = _write_asset(
                    workspace,
                    content=content,
                    content_type=content_type,
                    source="pixabay",
                    prompt=prompt,
                    media_type="video",
                    remote_url=remote,
                    meta={"attribution": item.get("attribution", ""), "tags": item.get("tags", "")},
                )
                attempts.append({"provider": "pixabay_video", "ok": True, "remote_url": remote, "path": written.get("path")})
                assets.append(written)
            except Exception as exc:
                attempts.append({"provider": "pixabay_video", "ok": False, "remote_url": remote, "reason": str(exc)})

    injected_files = inject_media_assets(workspace, assets) if assets else []
    manifest = {
        "project_id": project_id,
        "status": "ready" if _approved_asset_count(assets) >= 3 else "failed",
        "assets": assets,
        "attempts": attempts,
        "asset_count": _approved_asset_count(assets),
        "stored_asset_count": len(assets),
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
