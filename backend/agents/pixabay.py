"""
Pixabay integration for Amarktai App Builder.

Backend-only image and video search using the Pixabay API.
Results are cached in memory for 24 hours.
All requests use safesearch=true and never expose the API key to the frontend.

Optional: Only used when PIXABAY_API_KEY is configured.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

PIXABAY_BASE_URL = "https://pixabay.com/api/"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
CACHE_TTL_SECONDS = 86400  # 24 hours

# In-memory cache: key -> (timestamp, result)
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()


def _cache_key(endpoint: str, params: dict) -> str:
    return f"{endpoint}::{json.dumps(sorted(params.items()))}"


async def _get_cached(key: str) -> Any | None:
    async with _cache_lock:
        entry = _cache.get(key)
        if entry:
            ts, result = entry
            if time.time() - ts < CACHE_TTL_SECONDS:
                return result
            del _cache[key]
    return None


async def _set_cached(key: str, result: Any) -> None:
    async with _cache_lock:
        _cache[key] = (time.time(), result)


async def search_images(
    query: str,
    api_key: str,
    per_page: int = 10,
    image_type: str = "all",
    orientation: str = "horizontal",
    category: str = "",
    min_width: int = 640,
    min_height: int = 360,
) -> list[dict[str, Any]]:
    """Search Pixabay for images.

    Returns a list of image dicts with:
      - url: the web format image URL
      - preview_url: preview thumbnail
      - full_url: largest available URL
      - attribution: attribution string required by Pixabay
      - width, height: dimensions
      - tags: comma-separated tags
      - pixabay_id: Pixabay image ID
      - pixabay_page_url: link to Pixabay page for attribution

    Args:
        query: Search query string.
        api_key: Pixabay API key (never exposed to frontend).
        per_page: Number of results (max 200, min 3).
        image_type: "all" | "photo" | "illustration" | "vector".
        orientation: "all" | "horizontal" | "vertical".
        category: optional category filter.
        min_width, min_height: minimum image dimensions.
    """
    if not api_key or not query.strip():
        return []

    per_page = max(3, min(per_page, 50))
    params: dict[str, Any] = {
        "key": api_key,
        "q": query.strip(),
        "image_type": image_type,
        "orientation": orientation,
        "safesearch": "true",
        "per_page": per_page,
        "min_width": min_width,
        "min_height": min_height,
        "editors_choice": "false",
        "order": "popular",
    }
    if category:
        params["category"] = category

    cache_params = {k: v for k, v in params.items() if k != "key"}
    key = _cache_key(PIXABAY_BASE_URL, cache_params)

    cached = await _get_cached(key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(PIXABAY_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for hit in data.get("hits", []):
        results.append({
            "url": hit.get("webformatURL", ""),
            "preview_url": hit.get("previewURL", ""),
            "full_url": hit.get("largeImageURL", hit.get("webformatURL", "")),
            "width": hit.get("webformatWidth", 0),
            "height": hit.get("webformatHeight", 0),
            "tags": hit.get("tags", ""),
            "pixabay_id": hit.get("id", 0),
            "pixabay_page_url": hit.get("pageURL", ""),
            "attribution": (
                f"Photo by {hit.get('user', 'Pixabay user')} on Pixabay "
                f"({hit.get('pageURL', 'https://pixabay.com')})"
            ),
            "source": "pixabay",
        })

    await _set_cached(key, results)
    return results


async def search_videos(
    query: str,
    api_key: str,
    per_page: int = 5,
    video_type: str = "all",
    category: str = "",
    min_width: int = 640,
    min_height: int = 360,
) -> list[dict[str, Any]]:
    """Search Pixabay for videos.

    Returns a list of video dicts with:
      - url: medium quality video URL (best for web use)
      - preview_url: video thumbnail
      - attribution: attribution string
      - width, height: dimensions
      - tags: comma-separated tags
      - duration: video duration in seconds
      - pixabay_id: Pixabay video ID
      - pixabay_page_url: link to Pixabay page for attribution

    Args:
        query: Search query string.
        api_key: Pixabay API key (never exposed to frontend).
        per_page: Number of results (max 50, min 3).
        video_type: "all" | "film" | "animation".
        category: optional category filter.
        min_width, min_height: minimum video dimensions.
    """
    if not api_key or not query.strip():
        return []

    per_page = max(3, min(per_page, 20))
    params: dict[str, Any] = {
        "key": api_key,
        "q": query.strip(),
        "video_type": video_type,
        "safesearch": "true",
        "per_page": per_page,
        "order": "popular",
    }
    if category:
        params["category"] = category

    cache_params = {k: v for k, v in params.items() if k != "key"}
    key = _cache_key(PIXABAY_VIDEO_URL, cache_params)

    cached = await _get_cached(key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(PIXABAY_VIDEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for hit in data.get("hits", []):
        videos = hit.get("videos", {})
        # Prefer medium quality; fall back to small or large
        vid = (
            videos.get("medium")
            or videos.get("small")
            or videos.get("large")
            or {}
        )
        url = vid.get("url", "")
        if not url:
            continue
        results.append({
            "url": url,
            "preview_url": hit.get("picture_id", ""),
            "width": vid.get("width", 0),
            "height": vid.get("height", 0),
            "tags": hit.get("tags", ""),
            "duration": hit.get("duration", 0),
            "pixabay_id": hit.get("id", 0),
            "pixabay_page_url": hit.get("pageURL", ""),
            "attribution": (
                f"Video by {hit.get('user', 'Pixabay user')} on Pixabay "
                f"({hit.get('pageURL', 'https://pixabay.com')})"
            ),
            "source": "pixabay",
        })

    await _set_cached(key, results)
    return results


def build_media_manifest(
    images: list[dict],
    videos: list[dict],
    query: str,
) -> dict[str, Any]:
    """Build a media manifest for inclusion in amarktai.project.json."""
    return {
        "query": query,
        "source": "pixabay",
        "attribution_required": True,
        "images": [
            {
                "url": img["url"],
                "full_url": img.get("full_url", img["url"]),
                "tags": img.get("tags", ""),
                "attribution": img.get("attribution", ""),
                "pixabay_page_url": img.get("pixabay_page_url", ""),
            }
            for img in images
        ],
        "videos": [
            {
                "url": vid["url"],
                "tags": vid.get("tags", ""),
                "duration": vid.get("duration", 0),
                "attribution": vid.get("attribution", ""),
                "pixabay_page_url": vid.get("pixabay_page_url", ""),
            }
            for vid in videos
        ],
        "license": "Pixabay License — free for commercial and non-commercial use; attribution appreciated",
        "license_url": "https://pixabay.com/service/license-summary/",
    }
