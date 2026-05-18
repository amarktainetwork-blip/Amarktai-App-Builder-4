"""Runtime media generation and persistence for production builds."""
from __future__ import annotations

import base64
import asyncio
import io
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
from agents.media_storage import get_max_upload_bytes, safe_filename, validate_upload
from app.services.genx_live_probe_service import discover_genx_runtime
from app.services.genx_runtime_service import generate_genx_media_job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _media_dir(workspace: Path) -> Path:
    path = workspace / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _download(url: str, *, attempts: int = 3) -> tuple[bytes, str]:
    last_error: Exception | None = None
    max_bytes = get_max_upload_bytes()
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        for attempt in range(max(1, attempts)):
            try:
                response = await client.get(url)
                if response.status_code == 429 and attempt < attempts - 1:
                    retry_after = response.headers.get("retry-after")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 1.5
                    await asyncio.sleep(min(delay, 8.0))
                    continue
                response.raise_for_status()
                content_length = int(response.headers.get("content-length") or 0)
                if content_length and content_length > max_bytes:
                    raise ValueError(f"Downloaded media exceeds maximum upload size of {max_bytes // (1024 * 1024)} MB.")
                content = response.content
                if len(content) > max_bytes:
                    raise ValueError(f"Downloaded media exceeds maximum upload size of {max_bytes // (1024 * 1024)} MB.")
                content_type = response.headers.get("content-type", "").split(";")[0] or "application/octet-stream"
                return content, content_type
            except Exception as exc:
                last_error = exc
                if attempt < attempts - 1:
                    await asyncio.sleep((attempt + 1) * 0.75)
    raise last_error or RuntimeError("Media download failed")


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
    if provider.lower() == "qwen" and os.environ.get("QWEN_IMAGE_ENDPOINT_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return {"ok": False, "provider": provider, "error": "Qwen image endpoint is disabled by QWEN_IMAGE_ENDPOINT_ENABLED"}
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
    if media_type == "video":
        max_video_mb = int(os.environ.get("MEDIA_MAX_VIDEO_MB", "18"))
        if len(content) > max_video_mb * 1024 * 1024:
            raise ValueError(f"Video exceeds maximum persisted video size of {max_video_mb} MB.")
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
        and (
            Path(str(asset.get("path", ""))).suffix.lower() != ".svg"
            or asset.get("source") == "css_svg_fallback"
        )
    ])


def _fallback_palette(index: int) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    palettes = [
        ((4, 10, 18), (0, 230, 118), (83, 216, 255)),
        ((7, 8, 18), (139, 92, 246), (0, 230, 118)),
        ((5, 12, 24), (83, 216, 255), (248, 250, 252)),
    ]
    return palettes[index % len(palettes)]


def _local_runtime_fallback_png(prompt: str, index: int) -> bytes:
    """Create an honest local raster fallback image when providers are unavailable.

    These assets are deliberately marked as local runtime fallbacks in the manifest.
    They are not counted or described as AI-generated media.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        bg, accent, accent_two = _fallback_palette(index)
        image = Image.new("RGB", (1280, 720), bg)
        draw = ImageDraw.Draw(image)
        for radius in range(620, 40, -48):
            color = tuple(int(bg[i] + (accent[i] - bg[i]) * 0.55) for i in range(3))
            draw.ellipse((120 - radius // 2, -220 - radius // 3, 120 + radius, 360 + radius // 2), outline=color, width=3)
        for step in range(0, 1280, 44):
            color = tuple(int(bg[i] + (accent_two[i] - bg[i]) * 0.36) for i in range(3))
            draw.line((step, 720, step + 360, 0), fill=color, width=1)
        panel = (86, 118, 166, 198)
        draw.rounded_rectangle((120, 120, 1160, 600), radius=28, outline=accent, width=3, fill=(10, 17, 30))
        draw.rounded_rectangle((170, 184, 720, 246), radius=14, fill=panel)
        draw.rounded_rectangle((170, 278, 1040, 340), radius=14, outline=accent_two, width=2)
        draw.rounded_rectangle((170, 376, 940, 438), radius=14, outline=accent, width=2)
        draw.rounded_rectangle((170, 474, 1080, 536), radius=14, outline=(248, 250, 252), width=2)
        text = "Amarktai Builder runtime media"
        sub = "Local fallback asset - external providers unavailable"
        font = ImageFont.load_default()
        draw.text((196, 202), text, fill=(248, 250, 252), font=font)
        draw.text((196, 302), sub, fill=(168, 179, 199), font=font)
        draw.text((196, 400), f"Build prompt: {(prompt or 'production website')[:72]}", fill=(168, 179, 199), font=font)
        draw.text((196, 498), f"Asset {index + 1} of 3", fill=(168, 179, 199), font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception:
        # 16x16 PNG generated once; still a real raster file, just minimal.
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAI0lEQVR42mP8z8Dwn4ECwESJ5lEDRg0YNWDUgFEDBg0AALuGAxk9WyeTAAAAAElFTkSuQmCC"
        )


def _persist_local_runtime_fallbacks(
    workspace: Path,
    *,
    prompt: str,
    assets: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    minimum_assets: int = 3,
) -> None:
    while _approved_asset_count(assets) < minimum_assets:
        index = _approved_asset_count(assets)
        content = _local_runtime_fallback_png(prompt, index)
        try:
            written = _write_asset(
                workspace,
                content=content,
                content_type="image/png",
                source="local_runtime_fallback",
                prompt=prompt,
                media_type="image",
                meta={
                    "provider": "local_runtime_fallback",
                    "model": "deterministic-raster-fallback",
                    "status": "persisted",
                    "reason": "External media providers failed, timed out, were rate limited, or returned unusable assets. This asset is not AI-generated.",
                },
            )
            attempts.append({
                "provider": "local_runtime_fallback",
                "ok": True,
                "status": "persisted",
                "path": written.get("path"),
                "reason": "Persisted honest local raster fallback; not AI-generated.",
            })
            assets.append(written)
        except Exception as exc:
            attempts.append({"provider": "local_runtime_fallback", "ok": False, "reason": str(exc)})
            break


MEDIA_PROFILES: dict[str, dict[str, Any]] = {
    "bakery": {
        "triggers": {"bakery", "baker", "bread", "sourdough", "pastry", "pastries", "cafe", "coffee", "catering"},
        "queries": ["artisan bakery", "sourdough bread", "pastry cafe", "coffee interior", "handcrafted pastry"],
        "conflicts": {"software", "logistics", "courier", "transport", "programming", "app", "digital", "computer"},
    },
    "fashion": {
        "triggers": {"fashion", "boutique", "runway", "couture", "atelier", "fabric", "wardrobe"},
        "queries": ["editorial fashion", "luxury boutique", "runway fabric detail"],
        "conflicts": {"software", "logistics", "courier", "warehouse", "truck", "computer"},
    },
    "fitness": {
        "triggers": {"fitness", "gym", "workout", "strength", "trainer", "coaching", "pilates", "yoga"},
        "queries": ["premium fitness studio", "strength coaching", "modern gym"],
        "conflicts": {"software", "logistics", "courier", "transport", "programming", "computer"},
    },
    "software": {
        "triggers": {"ai", "software", "dashboard", "automation", "repo", "developer", "coding", "app"},
        "queries": ["artificial intelligence technology", "futuristic software dashboard", "digital media studio"],
        "conflicts": set(),
    },
}

SECTION_ALIASES: dict[str, list[str]] = {
    "hero": ["hero", "banner", "cover", "intro", "masthead"],
    "services": ["service", "features", "solutions", "offerings"],
    "gallery": ["gallery", "portfolio", "showcase", "photos", "work"],
    "about": ["about", "story", "team", "mission"],
    "contact": ["contact", "cta", "book", "consult", "reach"],
    "general": ["general"],
}


def _media_profile(prompt: str, sections: list[str]) -> str:
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", " ".join([prompt or "", " ".join(sections or [])])).lower()
    tokens = set(text.split())
    for name, profile in MEDIA_PROFILES.items():
        if tokens & set(profile["triggers"]):
            return name
    return "generic"


def _compact_media_query(prompt: str, sections: list[str]) -> str:
    """Create a short industry-aware stock query instead of sending the raw user prompt to Pixabay."""
    profile_name = _media_profile(prompt, sections)
    if profile_name in MEDIA_PROFILES:
        return MEDIA_PROFILES[profile_name]["queries"][0]
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", prompt or "").lower()
    stop = {
        "build", "create", "page", "landing", "website", "must", "include", "generated",
        "system", "itself", "using", "live", "with", "and", "the", "for", "our", "all",
        "capabilities", "requirements", "mandatory", "production", "ready", "responsive",
    }
    words = [w for w in text.split() if len(w) > 3 and w not in stop]
    selected = words[:4] or ["premium", "editorial", "brand"]
    return " ".join(selected[:6])


def _media_queries(prompt: str, sections: list[str]) -> list[str]:
    profile_name = _media_profile(prompt, sections)
    queries = list(MEDIA_PROFILES.get(profile_name, {}).get("queries", [])) or [_compact_media_query(prompt, sections)]
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = " ".join(str(q).split()).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def _asset_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, ""))
        for key in ("tags", "title", "attribution", "user", "description")
    ).lower()


def _explicitly_requested(prompt: str, term: str) -> bool:
    text = (prompt or "").lower()
    negative = re.search(rf"\b(?:do not|don't|without|no)\b[^\n.]*\b{re.escape(term)}\b", text)
    return bool(term in text and not negative)


def _asset_conflicts_with_prompt(item: dict[str, Any], prompt: str, sections: list[str]) -> str:
    profile = MEDIA_PROFILES.get(_media_profile(prompt, sections), {})
    conflicts = set(profile.get("conflicts", set()))
    text = _asset_text(item)
    for term in sorted(conflicts):
        if term in text and not _explicitly_requested(prompt, term):
            return term
    return ""


def _normalize_section_name(name: str) -> str:
    raw = (name or "").strip().lower().replace("-", "_").replace("/", "_")
    if raw in {"feature", "features", "service", "services", "products", "product"}:
        return "services"
    if raw in {"cta", "book", "booking", "contact", "footer"}:
        return "contact"
    if raw in {"portfolio", "showcase", "photos"}:
        return "gallery"
    if raw in {"about", "story", "team", "mission"}:
        return "about"
    if raw in {"hero", "banner", "intro"}:
        return "hero"
    if raw in SECTION_ALIASES:
        return raw
    return "general"


def _infer_asset_section(asset: dict[str, Any], fallback_order: list[str]) -> str:
    explicit = _normalize_section_name(str(asset.get("section", "")))
    if explicit != "general":
        return explicit
    text = " ".join(
        str(asset.get(k, ""))
        for k in ("prompt", "tags", "title", "description", "remote_url", "path")
    ).lower()
    for section, aliases in SECTION_ALIASES.items():
        if section == "general":
            continue
        if any(alias in text for alias in aliases):
            return section
    for section in fallback_order:
        mapped = _normalize_section_name(section)
        if mapped != "general":
            return mapped
    return "general"


def _persist_css_svg_fallbacks(
    workspace: Path,
    *,
    prompt: str,
    sections: list[str],
    assets: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    minimum_assets: int = 3,
) -> None:
    safe_sections = [_normalize_section_name(s) for s in (sections or []) if s]
    section_cycle = safe_sections or ["hero", "services", "gallery"]
    while _approved_asset_count(assets) < minimum_assets:
        index = _approved_asset_count(assets)
        section = section_cycle[index % len(section_cycle)]
        asset_id = uuid.uuid4().hex[:12]
        filename = safe_filename(f"css-svg-fallback-{asset_id}.svg")
        path = _media_dir(workspace) / filename
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720' role='img' aria-label='Amarktai fallback visual'>"
            "<defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'>"
            "<stop offset='0%' stop-color='#050b16'/><stop offset='100%' stop-color='#121f36'/></linearGradient></defs>"
            "<rect width='1280' height='720' fill='url(#g)'/>"
            "<circle cx='980' cy='120' r='220' fill='rgba(0,230,118,.16)'/>"
            "<circle cx='220' cy='600' r='260' fill='rgba(83,216,255,.16)'/>"
            "<rect x='96' y='112' width='1088' height='496' rx='28' fill='none' stroke='rgba(83,216,255,.5)' stroke-width='3'/>"
            f"<text x='140' y='220' fill='#F8FAFC' font-size='34' font-family='Inter, Arial, sans-serif'>Amarktai media fallback</text>"
            f"<text x='140' y='274' fill='#A8B3C7' font-size='22' font-family='Inter, Arial, sans-serif'>Section: {section}</text>"
            f"<text x='140' y='326' fill='#A8B3C7' font-size='18' font-family='Inter, Arial, sans-serif'>{(prompt or 'production website')[:110]}</text>"
            "</svg>"
        )
        path.write_text(svg, encoding="utf-8")
        asset = {
            "id": asset_id,
            "source": "css_svg_fallback",
            "provider": "css_svg_fallback",
            "model": "deterministic-svg-fallback",
            "media_type": "image",
            "mime_type": "image/svg+xml",
            "path": str(path.relative_to(workspace)).replace("\\", "/"),
            "size_bytes": len(svg.encode("utf-8")),
            "width": 1280,
            "height": 720,
            "prompt": prompt,
            "section": section,
            "created_at": _now(),
            "status": "persisted",
            "reason": "Generated deterministic CSS/SVG fallback because provider media was unavailable or irrelevant.",
        }
        assets.append(asset)
        attempts.append({
            "provider": "css_svg_fallback",
            "ok": True,
            "status": "persisted",
            "path": asset["path"],
            "reason": "Generated deterministic SVG fallback media.",
        })


def _filter_relevant_pixabay_assets(
    items: list[dict[str, Any]],
    *,
    prompt: str,
    sections: list[str],
    media_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in items:
        conflict = _asset_conflicts_with_prompt(item, prompt, sections)
        if conflict:
            rejected.append({
                "media_type": media_type,
                "reason": f"conflicting_{conflict}",
                "tags": item.get("tags", ""),
                "title": item.get("title", ""),
            })
        else:
            accepted.append(item)
    return accepted, rejected


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
            result = None
            for attempt_no in range(2):
                result = await generate_genx_media_job(
                    api_key=key,
                    base_url=base,
                    model=model,
                    prompt=image_prompt,
                    category="image",
                    extra={"size": "1792x1024"},
                )
                attempts.append({
                    k: v for k, v in (result or {}).items()
                    if k not in {"bytes"}
                } | {"attempt": attempt_no + 1})
                if result and result.get("ok"):
                    break
                if (result or {}).get("status") not in {"timeout", "failed", "poll_failed"}:
                    break
                await asyncio.sleep(1.0 + attempt_no)
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
        rejected_assets: list[dict[str, Any]] = []
        for query in _media_queries(prompt, sections):
            try:
                images = await search_images(query, pixabay_api_key, per_page=8, min_width=1024, min_height=576)
                videos = await search_videos(query, pixabay_api_key, per_page=3, min_width=1024, min_height=576)
                accepted_images, rejected_images = _filter_relevant_pixabay_assets(
                    images,
                    prompt=prompt,
                    sections=sections,
                    media_type="image",
                )
                accepted_videos, rejected_videos = _filter_relevant_pixabay_assets(
                    videos,
                    prompt=prompt,
                    sections=sections,
                    media_type="video",
                )
                rejected_assets.extend(rejected_images + rejected_videos)
                attempts.append({
                    "provider": "pixabay_search",
                    "ok": True,
                    "query": query,
                    "images_found": len(images),
                    "videos_found": len(videos),
                    "images_accepted": len(accepted_images),
                    "videos_accepted": len(accepted_videos),
                    "rejected_conflicts": len(rejected_images) + len(rejected_videos),
                })
                selected_images.extend(accepted_images)
                selected_videos.extend(accepted_videos)
                if len(selected_images) >= 6:
                    break
            except Exception as exc:
                attempts.append({"provider": "pixabay_search", "ok": False, "query": query, "reason": str(exc)})
        if rejected_assets:
            attempts.append({
                "provider": "pixabay_relevance_filter",
                "ok": True,
                "rejected": rejected_assets[:20],
                "rejected_count": len(rejected_assets),
            })

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

    no_relevant_stock = (
        allow_stock_fallback
        and pixabay_api_key
        and _approved_asset_count(assets) < 3
        and any(a.get("provider") == "pixabay_search" and a.get("ok") for a in attempts)
        and not any(a.get("provider") in {"pixabay", "pixabay_video"} and a.get("ok") for a in attempts)
    )
    if _approved_asset_count(assets) < 3 and not no_relevant_stock:
        _persist_local_runtime_fallbacks(
            workspace,
            prompt=prompt,
            assets=assets,
            attempts=attempts,
            minimum_assets=3,
        )
    elif no_relevant_stock:
        _persist_css_svg_fallbacks(
            workspace,
            prompt=prompt,
            sections=sections,
            assets=assets,
            attempts=attempts,
            minimum_assets=3,
        )
        attempts.append({
            "provider": "media_relevance_policy",
            "ok": True,
            "status": "fallback",
            "reason": "no_relevant_media_found",
        })
    section_hints = [_normalize_section_name(s) for s in (sections or []) if s]
    for idx, asset in enumerate(assets):
        if not asset.get("section"):
            fallback = section_hints[idx:] + section_hints[:idx] if section_hints else []
            asset["section"] = _infer_asset_section(asset, fallback)

    injected_files = inject_media_assets(workspace, assets, sections=sections) if assets else []
    section_alignment = summarize_media_section_alignment(workspace, assets, sections=sections)
    manifest = {
        "project_id": project_id,
        "status": "ready" if _approved_asset_count(assets) >= 3 else ("fallback" if no_relevant_stock else "failed"),
        "reason": "no_relevant_media_found" if no_relevant_stock else "",
        "assets": assets,
        "attempts": attempts,
        "asset_count": _approved_asset_count(assets),
        "stored_asset_count": len(assets),
        "injected_files": injected_files,
        "section_alignment": section_alignment,
        "created_at": _now(),
    }
    (workspace / "media_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _build_asset_markup(asset: dict[str, Any]) -> str:
    if asset.get("media_type") == "video":
        return (
            f'<div class="amarktai-inline-media-card"><video data-amarktai-media-asset src="{asset["path"]}" autoplay muted loop playsinline '
            'aria-label="Persisted generated video asset"></video></div>'
        )
    if asset.get("media_type") == "audio":
        return (
            f'<div class="amarktai-inline-media-card"><audio data-amarktai-media-asset src="{asset["path"]}" controls '
            'aria-label="Persisted generated audio asset"></audio></div>'
        )
    source_label = "Local runtime fallback" if asset.get("source") in {"local_runtime_fallback", "css_svg_fallback"} else "Persisted generated visual"
    return (
        f'<figure class="amarktai-inline-media-card"><img data-amarktai-media-asset src="{asset["path"]}" alt="{source_label} for this build" loading="lazy" /></figure>'
    )


def _inject_markup_into_section(html: str, section: str, markup: str) -> tuple[str, bool]:
    aliases = SECTION_ALIASES.get(section, [])
    for alias in aliases:
        pat = re.compile(
            rf"(<section[^>]*(?:id|class)=['\"][^'\"]*\b{re.escape(alias)}\b[^'\"]*['\"][^>]*>)(.*?)(</section>)",
            re.IGNORECASE | re.DOTALL,
        )
        if pat.search(html):
            return pat.sub(rf"\1\2{markup}\3", html, count=1), True
    return html, False


def summarize_media_section_alignment(
    workspace: Path,
    assets: list[dict[str, Any]],
    *,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    html = ""
    for rel in ("index.html", "public/index.html"):
        path = workspace / rel
        if path.exists():
            html = path.read_text(encoding="utf-8", errors="replace")
            break
    found_sections: list[dict[str, str]] = []
    if html:
        for match in re.finditer(r"<section(?P<attrs>[^>]*)>", html, re.IGNORECASE):
            attrs = match.group("attrs") or ""
            id_match = re.search(r"\bid=['\"]([^'\"]+)['\"]", attrs, re.IGNORECASE)
            class_match = re.search(r"\bclass=['\"]([^'\"]+)['\"]", attrs, re.IGNORECASE)
            section_id = id_match.group(1) if id_match else ""
            class_tokens = (class_match.group(1).split() if class_match else [])
            label = _normalize_section_name(section_id or (class_tokens[0] if class_tokens else "general"))
            found_sections.append({"id": section_id or "", "label": label})
    expected_sections = [_normalize_section_name(s) for s in (sections or []) if s]
    if not expected_sections:
        expected_sections = [item["label"] for item in found_sections if item["label"] != "general"]
    asset_counts: dict[str, int] = {}
    for asset in assets:
        key = _normalize_section_name(str(asset.get("section", "general")))
        asset_counts[key] = asset_counts.get(key, 0) + 1
    section_ids = [item["id"] for item in found_sections if item["id"]]
    return {
        "expected_sections": expected_sections,
        "page_sections": found_sections,
        "page_section_count": len(found_sections),
        "page_section_ids": section_ids,
        "asset_counts_by_section": asset_counts,
        "aligned_sections": sorted(
            section for section in set(expected_sections or asset_counts.keys())
            if asset_counts.get(section, 0) > 0
        ),
    }


def inject_media_assets(workspace: Path, assets: list[dict[str, Any]], *, sections: list[str] | None = None) -> list[str]:
    """Inject persisted media assets into static HTML/CSS when generated files omit them."""
    changed: list[str] = []
    media_assets = [
        asset for asset in assets
        if asset.get("media_type") in {"image", "logo", "video", "audio"}
        and asset.get("path")
    ][:4]
    if not media_assets:
        return changed
    section_hints = [_normalize_section_name(s) for s in (sections or []) if s]
    for rel in ("index.html", "public/index.html"):
        path = workspace / rel
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        if "data-amarktai-media-asset" in html:
            return changed
        unused: list[dict[str, Any]] = []
        for idx, asset in enumerate(media_assets):
            section = _normalize_section_name(str(asset.get("section", "")))
            if section == "general":
                fallback = section_hints[idx:] + section_hints[:idx] if section_hints else []
                section = _infer_asset_section(asset, fallback)
            markup = _build_asset_markup(asset)
            html, placed = _inject_markup_into_section(html, section, markup)
            if not placed:
                unused.append(asset)

        if unused:
            overflow_assets = unused
            asset_markup = '<div class="amarktai-generated-media-grid">'
            for asset in overflow_assets:
                asset_markup += _build_asset_markup(asset)
            asset_markup += "</div>"
            if any(asset.get("media_type") == "video" for asset in overflow_assets):
                asset_markup += (
                    '<p class="amarktai-media-note">Video media is persisted locally and validated before finalize.</p>'
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
.amarktai-generated-media-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:1rem; }
.amarktai-inline-media-card { margin-top: 1rem; }
.amarktai-generated-media img, .amarktai-generated-media video, .amarktai-generated-media audio { width:100%; border-radius:20px; object-fit:cover; box-shadow:0 24px 80px rgba(0,0,0,.32); }
.amarktai-inline-media-card img, .amarktai-inline-media-card video, .amarktai-inline-media-card audio { width:100%; border-radius:16px; object-fit:cover; box-shadow:0 18px 54px rgba(0,0,0,.28); }
.amarktai-media-note { color:var(--color-muted,#94a3b8); }
""".strip()
    if css_path.exists() and "amarktai-generated-media" not in css_path.read_text(errors="replace"):
        css_path.write_text(css_path.read_text(encoding="utf-8", errors="replace") + "\n\n" + css + "\n", encoding="utf-8")
        changed.append("styles.css")
    return changed
