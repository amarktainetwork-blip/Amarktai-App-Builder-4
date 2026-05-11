"""
Media storage utilities for Amarktai App Builder.

Handles:
  - Safe file path construction (no traversal)
  - MIME/type validation (image, video, audio, svg, document)
  - Pillow-based image verification and thumbnail generation
  - Slug-based filename sanitization
  - Storage path management from environment
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any

from slugify import slugify

logger = logging.getLogger("amarktai.media")

# ── Storage path config ───────────────────────────────────────────────────────

def get_storage_root() -> Path:
    path = os.environ.get("MEDIA_STORAGE_PATH", "/app/storage/media")
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_max_upload_bytes() -> int:
    mb = int(os.environ.get("MEDIA_MAX_UPLOAD_MB", "25"))
    return mb * 1024 * 1024


# ── Allowed MIME types ────────────────────────────────────────────────────────

_ALLOWED_IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/avif", "image/bmp", "image/tiff",
}
_ALLOWED_SVG_MIMES = {"image/svg+xml"}
_ALLOWED_VIDEO_MIMES = {
    "video/mp4", "video/webm", "video/ogg", "video/quicktime",
}
_ALLOWED_AUDIO_MIMES = {
    "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm",
    "audio/aac", "audio/flac",
}
_ALLOWED_DOCUMENT_MIMES = {
    "application/pdf", "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_ALL_ALLOWED_MIMES = (
    _ALLOWED_IMAGE_MIMES
    | _ALLOWED_SVG_MIMES
    | _ALLOWED_VIDEO_MIMES
    | _ALLOWED_AUDIO_MIMES
    | _ALLOWED_DOCUMENT_MIMES
)

# MIME to media_type mapping
_MIME_TO_MEDIA_TYPE: dict[str, str] = {
    **{m: "image" for m in _ALLOWED_IMAGE_MIMES},
    **{m: "svg" for m in _ALLOWED_SVG_MIMES},
    **{m: "video" for m in _ALLOWED_VIDEO_MIMES},
    **{m: "audio" for m in _ALLOWED_AUDIO_MIMES},
    **{m: "document" for m in _ALLOWED_DOCUMENT_MIMES},
}

# Dangerous extensions that must never be accepted regardless of mime
_DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".js", ".mjs",
    ".py", ".rb", ".php", ".pl", ".lua", ".jar", ".war",
    ".dll", ".so", ".dylib", ".vbs", ".wsf", ".pif", ".com",
    ".scr", ".reg", ".msi", ".hta",
}


def safe_filename(original: str) -> str:
    """Return a slugified, extension-preserved safe filename."""
    path = Path(original)
    stem = slugify(path.stem or "upload", max_length=60) or "upload"
    ext = path.suffix.lower()
    if ext in _DANGEROUS_EXTENSIONS:
        ext = ""
    return f"{stem}{ext}"


def media_type_from_mime(mime: str) -> str:
    return _MIME_TO_MEDIA_TYPE.get(mime, "document")


def detect_mime(filename: str, content: bytes) -> str:
    """Detect MIME type from file content and filename."""
    # Check filename extension first
    guessed, _ = mimetypes.guess_type(filename)
    # For SVG, check content
    if filename.lower().endswith(".svg") or (guessed and "svg" in guessed):
        stripped = content[:512].lstrip()
        if stripped.startswith(b"<svg") or b"<svg" in stripped[:200]:
            return "image/svg+xml"
    # Check magic bytes for common image types
    if content[:4] == b"\x89PNG":
        return "image/png"
    if content[:3] in (b"\xff\xd8\xff",):
        return "image/jpeg"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[:4] == b"\x00\x00\x00\x18" or content[:4] == b"\x00\x00\x00\x20":
        if b"ftyp" in content[:16]:
            return "video/mp4"
    if guessed:
        return guessed
    return "application/octet-stream"


def validate_upload(
    filename: str,
    content: bytes,
    media_type_override: str | None = None,
) -> dict[str, Any]:
    """Validate an uploaded file. Returns dict with ok/error/mime/media_type."""
    # Size check
    max_bytes = get_max_upload_bytes()
    if len(content) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return {"ok": False, "error": f"File exceeds maximum upload size of {mb} MB."}

    if not filename.strip():
        return {"ok": False, "error": "Filename is required."}

    ext = Path(filename).suffix.lower()
    if ext in _DANGEROUS_EXTENSIONS:
        return {"ok": False, "error": f"Extension '{ext}' is not allowed."}

    mime = detect_mime(filename, content)

    if mime not in _ALL_ALLOWED_MIMES:
        return {"ok": False, "error": f"File type '{mime}' is not allowed."}

    media_type = media_type_override or media_type_from_mime(mime)

    # Verify images with Pillow
    if media_type in ("image", "logo") and mime in _ALLOWED_IMAGE_MIMES:
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(content))
            img.verify()
            # Re-open to get dimensions (verify() closes the image)
            img = Image.open(io.BytesIO(content))
            width, height = img.size
        except Exception as e:
            return {"ok": False, "error": f"Image validation failed: {e}"}
        return {"ok": True, "mime": mime, "media_type": media_type, "width": width, "height": height}

    return {"ok": True, "mime": mime, "media_type": media_type, "width": 0, "height": 0}


def build_storage_path(user_id: str, asset_id: str, filename: str) -> Path:
    """Return the absolute storage path for an asset file."""
    root = get_storage_root()
    # Sanitize user_id and asset_id to prevent traversal
    safe_uid = slugify(str(user_id), max_length=64) or "default"
    safe_aid = slugify(str(asset_id), max_length=64) or asset_id[:36]
    safe_fn = safe_filename(filename)
    asset_dir = root / safe_uid / safe_aid
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir / safe_fn


def build_thumb_path(file_path: Path) -> Path:
    """Return the thumbnail path for a given asset file path."""
    return file_path.parent / f"thumb_{file_path.name}"


def save_file(
    user_id: str,
    asset_id: str,
    filename: str,
    content: bytes,
) -> tuple[Path, Path | None]:
    """Save file to storage and generate thumbnail if it's an image.

    Returns (file_path, thumb_path|None).
    """
    file_path = build_storage_path(user_id, asset_id, filename)
    file_path.write_bytes(content)

    thumb_path: Path | None = None
    mime = detect_mime(filename, content)
    if mime in _ALLOWED_IMAGE_MIMES:
        thumb_path = _generate_thumbnail(content, file_path)

    return file_path, thumb_path


def _generate_thumbnail(content: bytes, original_path: Path, size: tuple[int, int] = (320, 200)) -> Path | None:
    """Generate a thumbnail for an image file. Returns thumbnail path or None on failure."""
    try:
        from PIL import Image
        import io
        thumb_path = build_thumb_path(original_path)
        img = Image.open(io.BytesIO(content))
        img.thumbnail(size, Image.LANCZOS)
        # Convert to RGB if necessary (e.g. RGBA PNG)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(str(thumb_path), "JPEG", quality=80, optimize=True)
        return thumb_path
    except Exception as e:
        logger.warning("Thumbnail generation failed: %s", e)
        return None


def delete_asset_files(storage_path: str) -> None:
    """Delete an asset file and its thumbnail if they exist."""
    try:
        p = Path(storage_path)
        if p.exists():
            p.unlink()
        thumb = build_thumb_path(p)
        if thumb.exists():
            thumb.unlink()
        # Remove parent dir if empty
        if p.parent.exists() and not any(p.parent.iterdir()):
            p.parent.rmdir()
    except Exception as e:
        logger.warning("Failed to delete asset files: %s", e)


def public_url_for(asset_id: str, filename: str, thumb: bool = False) -> str:
    """Return the public API URL for serving an asset."""
    if thumb:
        return f"/api/media/{asset_id}/thumbnail"
    return f"/api/media/{asset_id}/file"


def storage_path_is_safe(path_str: str) -> bool:
    """Verify the storage path is within the allowed storage root (no traversal)."""
    root = get_storage_root().resolve()
    try:
        target = Path(path_str).resolve()
        return str(target).startswith(str(root))
    except Exception:
        return False
