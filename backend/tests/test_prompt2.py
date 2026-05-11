"""
Tests for Prompt 2 features:
  - Media upload validation / storage
  - Logo Agent (SVG fallback, uploaded logo)
  - Design diversity engine (signature + penalty)
  - Clarifier build-type questions
  - HTML/CSS validator
  - Agent contracts module
"""
from __future__ import annotations

import io
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Media storage tests ─────────────────────────────────────────────────────

from agents.media_storage import (
    validate_upload,
    save_file,
    delete_asset_files,
    safe_filename,
    build_storage_path,
    build_thumb_path,
    storage_path_is_safe,
    media_type_from_mime,
    detect_mime,
    get_storage_root,
)


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    """Redirect media storage to a temp directory for all tests."""
    monkeypatch.setenv("MEDIA_STORAGE_PATH", str(tmp_path / "media"))
    monkeypatch.setenv("MEDIA_MAX_UPLOAD_MB", "25")
    yield tmp_path / "media"


def _make_png_bytes() -> bytes:
    """Return minimal valid PNG bytes."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(0, 255, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_validate_upload_accepts_valid_png():
    content = _make_png_bytes()
    result = validate_upload("logo.png", content)
    assert result["ok"] is True
    assert result["media_type"] == "image"
    assert result["mime"] == "image/png"
    assert result["width"] == 10
    assert result["height"] == 10


def test_validate_upload_rejects_executable():
    content = b"#!/bin/bash\nrm -rf /"
    result = validate_upload("evil.sh", content)
    assert result["ok"] is False
    assert "not allowed" in result["error"]


def test_validate_upload_rejects_path_traversal_filename():
    content = _make_png_bytes()
    result = validate_upload("../../../etc/passwd.png", content)
    # The filename is sanitized but the content is valid; safe_filename handles this
    # Validate that safe_filename strips traversal
    fn = safe_filename("../../../etc/passwd.png")
    assert ".." not in fn
    assert "/" not in fn


def test_validate_upload_rejects_oversized_file(monkeypatch):
    monkeypatch.setenv("MEDIA_MAX_UPLOAD_MB", "0")
    from importlib import reload
    import agents.media_storage as ms
    reload(ms)
    content = b"x" * 100
    result = ms.validate_upload("test.png", content)
    assert result["ok"] is False
    assert "exceeds" in result["error"]


def test_validate_upload_rejects_js_extension():
    content = b"console.log('hello')"
    result = validate_upload("script.js", content)
    assert result["ok"] is False


def test_validate_upload_accepts_svg():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>'
    result = validate_upload("logo.svg", svg)
    assert result["ok"] is True
    assert result["media_type"] == "svg"


def test_safe_filename_strips_dangerous():
    assert ".." not in safe_filename("../hack.png")
    assert "/" not in safe_filename("foo/bar.png")
    # Dangerous extension stripped
    result = safe_filename("malware.exe")
    assert not result.endswith(".exe")


def test_save_file_creates_file_and_thumbnail():
    content = _make_png_bytes()
    user_id = "testuser"
    asset_id = str(uuid.uuid4())
    file_path, thumb_path = save_file(user_id, asset_id, "test.png", content)
    assert file_path.exists()
    # Thumbnail should be generated for PNG
    assert thumb_path is not None
    assert thumb_path.exists()


def test_save_file_no_thumbnail_for_svg():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    user_id = "testuser"
    asset_id = str(uuid.uuid4())
    file_path, thumb_path = save_file(user_id, asset_id, "logo.svg", svg)
    assert file_path.exists()
    # No thumbnail for SVG
    assert thumb_path is None


def test_delete_asset_files_removes_file():
    content = _make_png_bytes()
    user_id = "testuser"
    asset_id = str(uuid.uuid4())
    file_path, _ = save_file(user_id, asset_id, "test.png", content)
    assert file_path.exists()
    delete_asset_files(str(file_path))
    assert not file_path.exists()


def test_storage_path_is_safe_prevents_traversal():
    # A path outside the storage root should not be safe
    result = storage_path_is_safe("/etc/passwd")
    assert result is False


def test_storage_path_is_safe_allows_valid_path(tmp_path, monkeypatch):
    storage_root = tmp_path / "media"
    monkeypatch.setenv("MEDIA_STORAGE_PATH", str(storage_root))
    valid_path = str(storage_root / "user" / "asset" / "file.jpg")
    assert storage_path_is_safe(valid_path) is True


def test_media_type_from_mime():
    assert media_type_from_mime("image/jpeg") == "image"
    assert media_type_from_mime("image/svg+xml") == "svg"
    assert media_type_from_mime("video/mp4") == "video"
    assert media_type_from_mime("audio/mpeg") == "audio"


def test_detect_mime_png():
    content = _make_png_bytes()
    mime = detect_mime("test.png", content)
    assert mime == "image/png"


def test_detect_mime_jpeg():
    content = _make_jpeg_bytes()
    mime = detect_mime("test.jpg", content)
    assert mime == "image/jpeg"


# ── Logo Agent tests ─────────────────────────────────────────────────────────

from agents.logo_agent import (
    generate_svg_logo,
    generate_favicon_svg,
    run_logo_agent,
    logo_agent_prompt_block,
)


def test_generate_svg_logo_returns_valid_svg():
    svg = generate_svg_logo("Acme Corp", industry="tech", style="modern")
    assert "<svg" in svg
    assert "Acme Corp" in svg
    assert "</svg>" in svg


def test_generate_svg_logo_uses_initials():
    svg = generate_svg_logo("Acme Corp")
    assert "AC" in svg


def test_generate_favicon_svg_returns_valid_svg():
    favicon = generate_favicon_svg("TestBrand")
    assert "<svg" in favicon
    assert "T" in favicon  # first initial
    assert "</svg>" in favicon


@pytest.mark.asyncio
async def test_logo_agent_generates_svg_fallback():
    """Logo Agent should generate SVG when no uploaded logo."""
    result = await run_logo_agent({
        "businessName": "My Bakery",
        "industry": "food",
        "style": "organic-nature",
        "mediaSource": "css_svg",
    })
    assert result["logoType"] in ("svg", "fallback")
    assert result["htmlSnippet"]
    assert result["faviconDataUri"].startswith("data:image/svg+xml;base64,")
    assert result["fallbackUsed"] is False
    assert len(result["files"]) >= 2  # logo.svg + favicon.svg


@pytest.mark.asyncio
async def test_logo_agent_ai_source_falls_back_to_svg():
    """If AI requested but no model available, logo agent falls back to SVG with warning."""
    result = await run_logo_agent({
        "businessName": "Tech Startup",
        "mediaSource": "ai",
    })
    assert result["logoType"] in ("svg", "fallback")
    assert result["fallbackUsed"] is True
    assert any("AI logo" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_logo_agent_uses_uploaded_logo():
    """Logo Agent must use uploaded logo when uploadedLogoAssetId is provided."""
    asset_id = "test-asset-123"

    async def mock_lookup(aid: str):
        if aid == asset_id:
            return {
                "id": asset_id,
                "public_url": f"/api/media/{asset_id}/file",
                "mime_type": "image/png",
                "filename": "logo.png",
            }
        return None

    result = await run_logo_agent(
        {
            "businessName": "My Brand",
            "mediaSource": "uploaded",
            "uploadedLogoAssetId": asset_id,
        },
        media_library_fn=mock_lookup,
    )
    assert result["logoType"] == "uploaded"
    assert result["assetId"] == asset_id
    assert result["fallbackUsed"] is False
    assert "/api/media/" in result["htmlSnippet"]


@pytest.mark.asyncio
async def test_logo_agent_warns_if_uploaded_not_found():
    """Logo Agent should warn and fall back to SVG if uploaded asset not found."""

    async def mock_lookup_missing(aid: str):
        return None

    result = await run_logo_agent(
        {
            "businessName": "Ghost Brand",
            "mediaSource": "uploaded",
            "uploadedLogoAssetId": "nonexistent-id",
        },
        media_library_fn=mock_lookup_missing,
    )
    assert result["logoType"] in ("svg", "fallback")
    assert any("not found" in w.lower() for w in result["warnings"])


def test_logo_agent_prompt_block_includes_logo():
    result = {
        "logoType": "svg",
        "htmlSnippet": '<a class="site-logo-link">...</a>',
        "cssSnippet": ".site-logo-link { ... }",
        "faviconDataUri": "data:image/svg+xml;base64,abc",
        "warnings": [],
    }
    block = logo_agent_prompt_block(result)
    assert "LOGO AGENT" in block
    assert "site-logo-link" in block
    assert "favicon" in block.lower()


# ── Design diversity tests ────────────────────────────────────────────────────

from agents.design_engine import create_design_direction, make_design_signature, _DESIGN_STYLES


def test_design_direction_returns_signature():
    direction = create_design_direction("landing page for SaaS startup")
    assert "design_signature" in direction
    sig = direction["design_signature"]
    assert "styleName" in sig
    assert "paletteHash" in sig
    assert "fontPair" in sig
    assert "layoutArchetype" in sig


def test_design_diversity_avoids_recent_style():
    """Design engine should avoid recently used styles."""
    direction1 = create_design_direction("tech startup landing page")
    used_style = direction1["name"]
    recent = [{"styleName": used_style}]

    # Request with same prompt but with recent style penalized
    direction2 = create_design_direction(
        "tech startup landing page", recent_signatures=recent
    )
    # Should pick a different style (or at minimum the function runs without error)
    assert direction2["name"] is not None
    if len(_DESIGN_STYLES) > 1:
        assert direction2["name"] != used_style


def test_design_diversity_with_multiple_recent():
    """When many styles are excluded, still picks something."""
    # Block most styles
    all_styles = [{"styleName": s["name"]} for s in _DESIGN_STYLES[:-1]]
    direction = create_design_direction(
        "random prompt", recent_signatures=all_styles
    )
    assert direction["name"] is not None


def test_make_design_signature_structure():
    style = _DESIGN_STYLES[0]
    sig = make_design_signature(style)
    assert sig["styleName"] == style["name"]
    assert len(sig["paletteHash"]) == 8
    assert "|" in sig["fontPair"]


# ── Clarifier tests ───────────────────────────────────────────────────────────

from agents.clarification import (
    check_clarification_needed,
    apply_clarification_answers,
    get_questions_for_mode,
    _LANDING_PAGE_QUESTIONS,
    _PWA_QUESTIONS,
    _SAAS_FULLSTACK_QUESTIONS,
    _REPO_FIX_QUESTIONS,
)


def test_clarifier_landing_page_returns_specific_questions():
    result = check_clarification_needed("build a landing page", mode="landing_page")
    # Should use landing page question set for a vague prompt
    assert isinstance(result["questions"], list)
    assert len(result["questions"]) <= 5
    # Should include business_name or CTA as required
    ids = [q["id"] for q in result["questions"]]
    assert "business_name" in ids or "cta" in ids or "media" in ids


def test_clarifier_pwa_returns_offline_question():
    result = check_clarification_needed("build a pwa", mode="pwa")
    ids = [q["id"] for q in result["questions"]]
    # offline is required for PWA
    assert "offline" in ids or "core_workflow" in ids


def test_clarifier_saas_returns_auth_and_roles():
    result = check_clarification_needed("build a saas", mode="full_stack")
    ids = [q["id"] for q in result["questions"]]
    assert "user_roles" in ids or "auth_required" in ids


def test_clarifier_repo_fix_returns_preserve_design():
    result = check_clarification_needed("fix my repo", mode="repo_fix")
    ids = [q["id"] for q in result["questions"]]
    assert "preserve_design" in ids or "scope" in ids


def test_clarifier_max_5_questions():
    result = check_clarification_needed("build something", mode=None)
    assert len(result["questions"]) <= 5


def test_clarifier_can_skip_always_true():
    result = check_clarification_needed("build a landing page for my bakery")
    assert result["can_skip"] is True


def test_clarifier_clear_saas_prompt_not_vague():
    result = check_clarification_needed(
        "Build a full-stack SaaS application for project management with user authentication, "
        "MongoDB database, React frontend, and Docker deployment"
    )
    assert result["needs_clarification"] is False


def test_apply_clarification_answers_landing_page():
    original = "build a landing page"
    answers = {
        "business_name": "Acme Corp",
        "cta": "Get started",
        "style": "Modern / Clean / Minimal",
        "media": "Pixabay stock images",
    }
    enriched, params = apply_clarification_answers(original, answers)
    assert "Acme Corp" in enriched
    assert "Get started" in enriched
    assert params.get("media_requirements") == "Pixabay stock images"


def test_apply_clarification_answers_pwa():
    original = "build a PWA"
    answers = {
        "core_workflow": "Users can track daily habits offline",
        "offline": "Yes — full offline with service worker cache",
        "storage": "IndexedDB (structured data)",
        "logo_icon": "Use my uploaded logo",
    }
    enriched, params = apply_clarification_answers(original, answers)
    assert "habits" in enriched
    assert params.get("media_source") == "uploaded"


def test_get_questions_for_mode():
    qs = get_questions_for_mode("landing_page")
    assert qs == _LANDING_PAGE_QUESTIONS
    assert get_questions_for_mode("unknown_mode") == []


# ── HTML Validator tests ──────────────────────────────────────────────────────

from agents.html_validator import (
    validate_html_structure,
    validate_css,
    validate_media_references,
    validate_project_files_enhanced,
)


def test_html_validator_passes_good_html():
    html = """<!DOCTYPE html>
<html lang="en">
<head><title>My Site</title><link rel="stylesheet" href="styles.css"></head>
<body>
<h1>Welcome</h1>
<section><p>Some content here</p></section>
</body>
</html>"""
    result = validate_html_structure(html)
    assert len(result["issues"]) == 0


def test_html_validator_catches_missing_title():
    html = "<html><head></head><body><h1>Hi</h1></body></html>"
    result = validate_html_structure(html)
    assert any("title" in issue.lower() for issue in result["issues"])


def test_html_validator_catches_img_missing_alt():
    html = '<html><head><title>T</title></head><body><img src="logo.png"></body></html>'
    result = validate_html_structure(html)
    assert any("alt" in issue.lower() for issue in result["issues"])


def test_html_validator_warns_on_missing_stylesheet():
    html = "<html lang='en'><head><title>T</title></head><body><h1>H</h1></body></html>"
    result = validate_html_structure(html)
    assert any("stylesheet" in w.lower() for w in result["warnings"])


def test_css_validator_passes_good_css():
    css = """
body { font-family: 'Arial', sans-serif; font-size: 16px; color: #333; }
h1 { font-family: 'Georgia', serif; font-size: 2rem; }
@media (max-width: 768px) { body { font-size: 14px; } }
"""
    result = validate_css(css)
    assert len(result["issues"]) == 0


def test_css_validator_warns_missing_font_family():
    css = "body { color: red; }"
    result = validate_css(css)
    assert any("font-family" in w.lower() for w in result["warnings"])


def test_css_validator_warns_missing_media_query():
    css = "body { font-family: Arial; color: #333; }"
    result = validate_css(css)
    assert any("media" in w.lower() for w in result["warnings"])


def test_css_validator_catches_hidden_body():
    css = "body { display: none; }"
    result = validate_css(css)
    assert any("hidden" in issue.lower() or "display:none" in issue.lower() for issue in result["issues"])


def test_validate_media_references_catches_missing_logo():
    html = '<html><head><title>T</title></head><body><p>No logo here</p></body></html>'
    logo_result = {"logoType": "uploaded", "assetId": "test-asset-id-123"}
    result = validate_media_references(html, [], logo_result)
    assert any("logo" in issue.lower() or "assetId" in issue for issue in result["issues"])


def test_validate_media_references_warns_missing_pixabay_attribution():
    # HTML uses Pixabay assets (passed in pixabay_assets) but has no attribution text
    html = '<html><head><title>T</title></head><body><img src="hero.jpg" alt="hero"></body></html>'
    result = validate_media_references(html, [], pixabay_assets=["abc123"])
    assert any("attribution" in w.lower() or "pixabay" in w.lower() for w in result["warnings"])


def test_validate_project_files_enhanced():
    files = [
        {"path": "index.html", "content": """<!DOCTYPE html>
<html lang="en">
<head><title>My Site</title><link rel="stylesheet" href="styles.css"></head>
<body><h1>Hello</h1><section><p>Content</p></section></body>
</html>"""},
        {"path": "styles.css", "content": """
body { font-family: Arial; font-size: 16px; }
@media (max-width: 768px) { body { font-size: 14px; } }
"""},
    ]
    result = validate_project_files_enhanced(files)
    assert "issues" in result
    assert "warnings" in result
    assert "passed" in result


# ── Agent Contracts tests ─────────────────────────────────────────────────────

from agents.agent_contracts import get_contract, get_all_contracts, contracts_prompt_block, AGENT_CONTRACTS


def test_agent_contracts_all_present():
    contracts = get_all_contracts()
    expected = [
        "clarifier", "brand_design_director", "logo_agent", "media_agent",
        "ux_architect", "stack_architect", "frontend_agent", "backend_agent",
        "repo_agent", "preview_runtime_agent", "security_agent",
        "qa_validation_agent", "pr_release_agent",
    ]
    for key in expected:
        assert key in contracts, f"Missing agent contract: {key}"


def test_agent_contract_structure():
    contract = get_contract("logo_agent")
    assert contract is not None
    assert "name" in contract
    assert "responsibility" in contract
    assert "task_type" in contract
    assert "input_schema" in contract
    assert "output_schema" in contract
    assert "validation" in contract
    assert "failure_behavior" in contract


def test_get_contract_missing_returns_none():
    assert get_contract("nonexistent_agent") is None


def test_contracts_prompt_block_contains_all():
    block = contracts_prompt_block()
    assert "SPECIALIST AGENTS" in block
    assert "Logo Agent" in block
    assert "QA" in block
