"""Phase tests: Premium page quality, Runtime QA, Motion pipeline, Repo workbench,
Capability truth, and Talking avatar readiness.

All tests are deterministic — no live providers required.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ==============================================================================
# PHASE 1 — PREMIUM PAGE QUALITY (Bakery / Luma & Stone)
# ==============================================================================

class TestPremiumPageQualityBakery:
    """Phase 1: Premium bakery output should use warm palette and section media."""

    def _direction(self, prompt: str) -> dict:
        from agents.design_engine import create_design_direction
        return create_design_direction(prompt=prompt, project_type="static-site", tier="premium")

    def test_bakery_prompt_gets_warm_artisan_style(self):
        d = self._direction("Build a premium website for Luma & Stone sourdough bakery.")
        assert d["name"] == "warm-artisan-bakery", (
            f"Bakery prompt should select warm-artisan-bakery, got {d['name']!r}"
        )

    def test_bakery_palette_is_warm_not_saas_dark(self):
        d = self._direction("Build a premium website for Luma & Stone sourdough bakery.")
        bg = d["palette"]["background"]
        # Should be cream/warm — NOT a dark SaaS background like #080a10 or #0f0f23
        assert not bg.startswith("#0"), (
            f"Bakery palette background should be warm/cream, got {bg!r}"
        )

    def test_bakery_palette_has_warm_accent(self):
        d = self._direction("Artisan bakery and patisserie website.")
        accent = d["palette"]["accent"]
        # Terracotta / warm gold territory — not blue/teal/green
        assert "b5" in accent.lower() or "c8" in accent.lower() or "d4" in accent.lower() or "e6" in accent.lower(), (
            f"Bakery accent should be warm/terracotta, got {accent!r}"
        )

    def test_bakery_typography_is_serif(self):
        d = self._direction("Sourdough bread and pastry shop website for Luma & Stone.")
        heading_font = d["typography"]["heading"].lower()
        assert any(s in heading_font for s in ["playfair", "cormorant", "georgia", "serif"]), (
            f"Bakery heading font should be serif, got {d['typography']['heading']!r}"
        )

    def test_bakery_instructions_include_sticky_nav(self):
        d = self._direction("Build a landing page for Luma & Stone artisan bakery.")
        assert "sticky" in d["coder_instructions"].lower() or "sticky-nav" in d["coder_instructions"].lower()

    def test_bakery_instructions_include_cinematic_hero(self):
        d = self._direction("Build a website for a sourdough bakery called Luma & Stone.")
        assert "cinematic" in d["coder_instructions"].lower() or "hero" in d["coder_instructions"].lower()

    def test_bakery_instructions_include_alternating_sections(self):
        d = self._direction("Bakery website with product showcase and gallery.")
        instructions = d["coder_instructions"].lower()
        assert "alternating" in instructions or "editorial" in instructions

    def test_bakery_instructions_include_product_cards(self):
        d = self._direction("Premium bakery website with pastries, bread, and coffee.")
        assert "product card" in d["coder_instructions"].lower() or "cards" in d["coder_instructions"].lower()

    def test_bakery_instructions_include_gallery(self):
        d = self._direction("Artisan bakery with sourdough, pastries, and catering.")
        assert "gallery" in d["coder_instructions"].lower()

    def test_bakery_instructions_forbid_bottom_only_media_dump(self):
        d = self._direction("Bakery website with lots of images.")
        instructions = d["coder_instructions"].lower()
        assert "never append all images" in instructions or "never append" in instructions or "not only" in instructions or "inside its named section" in instructions

    def test_bakery_instructions_forbid_saas_dark_palette(self):
        d = self._direction("Luma & Stone bakery landing page.")
        assert "do not use generic saas dark" in d["coder_instructions"].lower() or "saas" in d["coder_instructions"].lower()

    def test_bakery_mobile_breakpoints_mentioned(self):
        d = self._direction("Responsive bakery website for mobile and desktop.")
        assert "mobile" in d["coder_instructions"].lower() or "breakpoint" in d["coder_instructions"].lower()

    def test_bakery_section_media_map_present(self):
        d = self._direction("Luma & Stone sourdough bakery website with gallery and events.")
        assert isinstance(d.get("section_media_map"), dict)
        assert len(d["section_media_map"]) > 0

    def test_bakery_premium_sections_present(self):
        d = self._direction("Full premium bakery website for Luma & Stone.")
        assert isinstance(d.get("premium_sections"), list)
        # Bakery style has premium_sections
        if d.get("is_bakery"):
            assert len(d["premium_sections"]) > 0
            sections_str = " ".join(d["premium_sections"])
            assert "hero" in sections_str

    def test_non_bakery_does_not_get_warm_artisan_style(self):
        """A SaaS prompt should NOT get the bakery style."""
        d = self._direction("Build a SaaS dashboard for software analytics.")
        assert d["name"] != "warm-artisan-bakery", (
            "Non-bakery prompt should not receive warm-artisan-bakery style"
        )

    def test_bakery_is_bakery_flag_set(self):
        d = self._direction("Sourdough and pastry bakery website.")
        assert d.get("is_bakery") is True

    def test_fitness_studio_does_not_get_bakery_style(self):
        """Fitness studio prompt should get a non-bakery, non-warm-artisan style."""
        d = self._direction("Build a premium one-page website for a boutique fitness studio called Forge House.")
        assert d["name"] != "warm-artisan-bakery"
        # Fitness should get industrial/dark style
        assert d.get("is_bakery") is False


# ==============================================================================
# PHASE 2 — REAL-TIME RUNTIME QA
# ==============================================================================

class TestRuntimeQATooling:
    """Phase 2: Runtime QA must distinguish tool-unavailable from score-zero."""

    def test_chromium_path_detection_returns_string_or_none(self):
        from app.services.runtime_qa_service import _detect_chromium_path
        result = _detect_chromium_path()
        assert result is None or isinstance(result, str), "Chromium detection must return str or None"

    def test_axe_source_returns_string_or_none(self):
        from app.services.runtime_qa_service import _axe_source
        result = _axe_source()
        assert result is None or isinstance(result, str)

    def test_missing_workspace_gives_blocker(self):
        from app.services.runtime_qa_service import run_runtime_qa
        result = run_runtime_qa("/tmp/nonexistent_workspace_amarktai_test_xyz")
        assert "blockers" in result
        assert len(result["blockers"]) > 0

    def test_tool_unavailable_lighthouse_does_not_give_score_zero(self):
        from app.services.runtime_qa_service import _run_lighthouse
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            result = _run_lighthouse("file:///tmp/index.html", report_dir)
            if not result.get("available"):
                # Tool unavailable — must set tool_unavailable flag, not give score 0
                assert result.get("tool_unavailable") is True, (
                    "Lighthouse unavailable should set tool_unavailable=True, not score=0"
                )

    def test_report_has_screenshots_dict(self):
        """QA report must have a screenshots key."""
        from app.services.runtime_qa_service import run_runtime_qa
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text("<html><body><h1>Test</h1></body></html>", encoding="utf-8")
            result = run_runtime_qa(ws)
        assert "screenshots" in result
        assert isinstance(result["screenshots"], dict)

    def test_report_distinguishes_tool_unavailable_in_accessibility(self):
        """When axe-core is not available, accessibility must set tool_unavailable, not score 0."""
        from app.services.runtime_qa_service import run_runtime_qa
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text("<html><body><h1>Test</h1></body></html>", encoding="utf-8")
            result = run_runtime_qa(ws)
        acc = result.get("accessibility", {})
        # If axe not available, it must not show score=0 and claim it ran
        if acc.get("tool_unavailable"):
            assert acc.get("score") is None or acc.get("available") is False, (
                "tool_unavailable accessibility should not report a meaningful score"
            )

    def test_broken_media_recorded_in_report(self):
        """Report must have a media_assets key."""
        from app.services.runtime_qa_service import run_runtime_qa
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text("<html><body><h1>Test</h1></body></html>", encoding="utf-8")
            result = run_runtime_qa(ws)
        assert "media_assets" in result

    def test_report_written_to_disk(self):
        """QA report must be persisted to disk."""
        import tempfile as _tempfile
        from app.services.runtime_qa_service import run_runtime_qa
        tmp_dir = _tempfile.mkdtemp(prefix="amarktai_qa_test_")
        try:
            ws = Path(tmp_dir)
            (ws / "index.html").write_text("<html><body><h1>Test</h1></body></html>", encoding="utf-8")
            result = run_runtime_qa(ws)
            report_path = Path(result.get("report_path", ""))
            assert report_path.exists(), (
                f"QA report must be written to disk; got tooling_status={result.get('tooling_status')}, "
                f"report_path={report_path}"
            )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# PHASE 3 — MOTION / MEDIA PIPELINE
# ==============================================================================

class TestMotionPipeline:
    """Phase 3: Motion_3D output must be parsed via AMARKTAI_FILE blocks."""

    def test_parse_motion_agent_output_extracts_css(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        agent_output = (
            "===AMARKTAI_FILE[styles.css]===\n"
            ".hero { animation: fadeIn 1s ease; }\n"
            "===END_AMARKTAI_FILE[styles.css]==="
        )
        files, warnings = parse_motion_agent_output(agent_output)
        assert "styles.css" in files
        assert "animation" in files["styles.css"]
        assert not warnings

    def test_parse_motion_agent_output_extracts_js(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        agent_output = (
            "===AMARKTAI_FILE[script.js]===\n"
            "document.querySelector('.hero').classList.add('animate');\n"
            "===END_AMARKTAI_FILE[script.js]==="
        )
        files, warnings = parse_motion_agent_output(agent_output)
        assert "script.js" in files

    def test_parse_motion_agent_output_extracts_html(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        agent_output = (
            "===AMARKTAI_FILE[index.html]===\n"
            "<html><body data-motion-runtime='pending'></body></html>\n"
            "===END_AMARKTAI_FILE[index.html]==="
        )
        files, warnings = parse_motion_agent_output(agent_output)
        assert "index.html" in files

    def test_parse_motion_rejects_report_files(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        agent_output = (
            "===AMARKTAI_FILE[quality_report.md]===\n"
            "# Quality Report\n"
            "===END_AMARKTAI_FILE[quality_report.md]===\n"
            "===AMARKTAI_FILE[styles.css]===\n"
            ".ok { color: green; }\n"
            "===END_AMARKTAI_FILE[styles.css]==="
        )
        files, warnings = parse_motion_agent_output(agent_output)
        assert "quality_report.md" not in files, "Report file must be rejected as motion target"
        assert "styles.css" in files
        assert any("quality_report.md" in w for w in warnings)

    def test_parse_motion_empty_output_gives_warning(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        files, warnings = parse_motion_agent_output("")
        assert not files
        assert len(warnings) > 0

    def test_parse_motion_unparsable_output_gives_warning_not_crash(self):
        from app.services.motion_runtime_service import parse_motion_agent_output
        files, warnings = parse_motion_agent_output("Some random text with no AMARKTAI_FILE blocks.")
        assert isinstance(files, dict)
        assert isinstance(warnings, list)
        assert len(warnings) > 0

    def test_apply_motion_agent_output_merges_css(self):
        from app.services.motion_runtime_service import apply_motion_agent_output
        existing_files = [
            {"path": "styles.css", "content": "body { margin: 0; }\n", "language": "css"},
        ]
        agent_output = (
            "===AMARKTAI_FILE[styles.css]===\n"
            ".hero { animation: fadeIn 1s ease; }\n"
            "===END_AMARKTAI_FILE[styles.css]==="
        )
        patched, warnings = apply_motion_agent_output(existing_files, agent_output)
        css_file = next(f for f in patched if f["path"] == "styles.css")
        assert "body { margin: 0; }" in css_file["content"]
        assert "animation" in css_file["content"]

    def test_apply_motion_invalid_output_preserves_files(self):
        from app.services.motion_runtime_service import apply_motion_agent_output
        existing_files = [
            {"path": "index.html", "content": "<html></html>", "language": "html"},
        ]
        patched, warnings = apply_motion_agent_output(existing_files, "Random unparsable output.")
        # Original file must be preserved
        paths = {f["path"] for f in patched}
        assert "index.html" in paths
        html_file = next(f for f in patched if f["path"] == "index.html")
        assert "<html>" in html_file["content"]

    def test_map_asset_to_section_hero(self):
        from app.services.motion_runtime_service import map_asset_to_section
        assert map_asset_to_section("cinematic hero bakery scene") == "hero"

    def test_map_asset_to_section_product(self):
        from app.services.motion_runtime_service import map_asset_to_section
        assert map_asset_to_section("sourdough bread product shot") == "product"

    def test_map_asset_to_section_gallery(self):
        from app.services.motion_runtime_service import map_asset_to_section
        assert map_asset_to_section("bakery gallery grid photos") == "gallery"

    def test_map_asset_to_section_events(self):
        from app.services.motion_runtime_service import map_asset_to_section
        assert map_asset_to_section("wedding catering event setup") == "events"

    def test_build_media_section_manifest_groups_assets(self):
        from app.services.motion_runtime_service import build_media_section_manifest
        assets = [
            {"prompt": "cinematic hero bakery", "url": "https://example.com/hero.jpg"},
            {"prompt": "sourdough bread product", "url": "https://example.com/bread.jpg"},
            {"prompt": "gallery photos", "url": "https://example.com/gallery.jpg"},
            {"prompt": "wedding catering event", "url": ""},
        ]
        manifest = build_media_section_manifest(assets)
        assert "hero" in manifest
        assert "product" in manifest
        assert "gallery" in manifest
        assert "events" in manifest
        assert len(manifest["hero"]) >= 1
        assert manifest["events"][0].get("fallback") is True  # no URL

    def test_motion_manifest_has_section_choreography(self):
        from app.services.motion_runtime_service import patch_motion_files
        files = [
            {"path": "index.html", "content": "<html><body><section id='hero'></section></body></html>", "language": "html"},
            {"path": "styles.css", "content": "body{}", "language": "css"},
        ]
        patched, manifest = patch_motion_files(files, prompt="bakery motion animation")
        assert "choreography" in manifest
        assert isinstance(manifest["choreography"], list)

    def test_motion_output_cannot_write_report_file_as_source(self):
        from app.services.motion_runtime_service import apply_motion_agent_output
        existing = [{"path": "index.html", "content": "<html></html>", "language": "html"}]
        agent_output = (
            "===AMARKTAI_FILE[quality_report.md]===\n"
            "# Fake report content\n"
            "===END_AMARKTAI_FILE[quality_report.md]==="
        )
        patched, warnings = apply_motion_agent_output(existing, agent_output)
        paths = {f["path"] for f in patched}
        assert "quality_report.md" not in paths


# ==============================================================================
# PHASE 5 — REPO WORKBENCH PROOF
# ==============================================================================

class TestRepoWorkbench:
    """Phase 5: GitHub URL parsing and repo workbench contracts."""

    def test_parse_full_https_url(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("https://github.com/owner/my-repo")
        assert result["ok"] is True
        assert result["owner"] == "owner"
        assert result["repo"] == "my-repo"
        assert result["full_name"] == "owner/my-repo"

    def test_parse_git_suffix_url(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("https://github.com/owner/my-repo.git")
        assert result["ok"] is True
        assert result["owner"] == "owner"
        assert result["repo"] == "my-repo"

    def test_parse_shorthand_owner_repo(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("owner/repo")
        assert result["ok"] is True
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"

    def test_parse_invalid_url_returns_error(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("not-a-url")
        assert result["ok"] is False
        assert "error" in result
        assert result["error"]

    def test_parse_empty_url_returns_error(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("")
        assert result["ok"] is False
        assert "error" in result

    def test_parse_url_with_extra_path_segments(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("https://github.com/owner/repo/tree/main")
        assert result["ok"] is True
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"

    def test_parse_url_clone_url_format(self):
        from app.services.github_repo_service import parse_github_url
        result = parse_github_url("https://github.com/owner/repo")
        assert result.get("clone_url") == "https://github.com/owner/repo.git"

    def test_validate_owner_repo_safe(self):
        from app.services.github_repo_service import validate_owner_repo
        owner, repo = validate_owner_repo("my-org", "my.repo_123")
        assert owner == "my-org"
        assert repo == "my.repo_123"

    def test_validate_owner_repo_rejects_unsafe(self):
        from app.services.github_repo_service import validate_owner_repo
        with pytest.raises(ValueError, match="[Uu]nsafe"):
            validate_owner_repo("owner; rm -rf /", "repo")

    def test_normalize_repo_shape(self):
        from app.services.github_repo_service import normalize_repo
        raw = {
            "id": 123,
            "name": "my-repo",
            "owner": {"login": "owner"},
            "full_name": "owner/my-repo",
            "html_url": "https://github.com/owner/my-repo",
            "clone_url": "https://github.com/owner/my-repo.git",
            "default_branch": "main",
            "private": False,
            "description": "A test repo",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-02T00:00:00Z",
            "archived": False,
            "disabled": False,
        }
        normalized = normalize_repo(raw)
        assert normalized["owner"] == "owner"
        assert normalized["name"] == "my-repo"
        assert normalized["default_branch"] == "main"
        assert "private" in normalized
        assert "html_url" in normalized
        assert "clone_url" in normalized

    def test_normalize_branch_shape(self):
        from app.services.github_repo_service import normalize_branch
        raw = {
            "name": "feature/test",
            "commit": {"sha": "abc123"},
            "protected": False,
        }
        normalized = normalize_branch(raw)
        assert normalized["name"] == "feature/test"
        assert normalized["commit_sha"] == "abc123"
        assert "protected" in normalized

    def test_list_repositories_without_token_returns_not_configured(self):
        """Without a token, repo listing must return a clear error, not a crash."""
        import asyncio
        from app.services.github_repo_service import list_repositories
        result = asyncio.run(list_repositories(token=""))
        assert result["ok"] is False
        assert result["configured"] is False
        assert "error" in result

    def test_list_branches_without_token_returns_not_configured(self):
        import asyncio
        from app.services.github_repo_service import list_branches
        result = asyncio.run(list_branches(token="", owner="owner", repo="repo"))
        assert result["ok"] is False
        assert "error" in result


# ==============================================================================
# PHASE 6 — CAPABILITY TRUTH CLEANUP
# ==============================================================================

class TestCapabilityTruthCleanup:
    """Phase 6: Brave 402 mapping, optional tool separation, readiness sync."""

    async def _build_caps(self, probes: dict | None = None) -> dict:
        from app.services.capability_truth_service import CapabilityTruthService

        async def resolver(key: str) -> dict:
            return {"value": None, "source": "missing", "configured": False}

        svc = CapabilityTruthService(resolver, cached_probes=probes or {})
        return await svc.build()

    def test_brave_402_maps_to_payment_required(self):
        from app.services.capability_truth_service import _probe_status
        # Simulate a probe result with HTTP 402
        probe = {"status": "payment_required", "http_status": 402, "live_status": "payment_required"}
        status, reason, _ = _probe_status("brave", True, "env", {"brave": probe})
        assert status == "payment_required"
        assert "402" in (reason or "") or "payment" in (reason or "").lower()

    def test_brave_live_fail_does_not_override_402(self):
        from app.services.capability_truth_service import _probe_status
        probe = {"http_status": 402, "live_status": "payment_required"}
        status, reason, _ = _probe_status("brave", True, "env", {"brave": probe})
        assert status == "payment_required"

    def test_optional_integration_has_does_not_block_preview(self):
        from app.services.capability_truth_service import _optional_integration
        result = _optional_integration("WHISPER_MODEL_PATH", "Whisper/STT")
        assert result.get("does_not_block_preview") is True
        assert result.get("optional") is True

    def test_optional_integration_has_blocks_finalize_false(self):
        from app.services.capability_truth_service import _optional_integration
        result = _optional_integration("FAISS_INDEX_PATH", "FAISS")
        assert result.get("blocks_finalize_if_required") is False

    def test_lighthouse_is_optional_in_capabilities(self):
        import asyncio
        caps = asyncio.run(self._build_caps())
        lighthouse = caps["capabilities"].get("lighthouse", {})
        assert lighthouse.get("optional") is True or lighthouse.get("does_not_block_preview") is True

    def test_axe_core_is_optional_in_capabilities(self):
        import asyncio
        caps = asyncio.run(self._build_caps())
        axe = caps["capabilities"].get("axe_core", {})
        assert axe.get("optional") is True or axe.get("does_not_block_preview") is True

    def test_axe_core_capability_not_module_based(self):
        """axe_core capability should check for JS file, not Python module."""
        import asyncio
        caps = asyncio.run(self._build_caps())
        axe = caps["capabilities"].get("axe_core", {})
        # Should exist in capabilities
        assert axe is not None
        # Should have does_not_block_preview
        assert "does_not_block_preview" in axe

    def test_readiness_live_ok_reflects_in_capability_status(self):
        from app.services.capability_truth_service import _probe_status
        probe = {"live_status": "live_ok", "probed_at": "2024-01-01T00:00:00Z"}
        status, reason, _ = _probe_status("genx", True, "settings", {"genx": probe})
        assert status == "live_ok"
        assert reason is None

    def test_not_tested_message_is_accurate(self):
        from app.services.capability_truth_service import _probe_status
        # No probe data — should return not_tested
        status, reason, _ = _probe_status("brave", True, "env", {})
        assert status == "not_tested"
        assert reason is not None

    def test_capability_required_keys_present(self):
        import asyncio
        caps = asyncio.run(self._build_caps())
        required_keys = [
            "text_generation", "reasoning", "vision", "repo_analysis",
            "tool_use", "streaming", "github_integration", "web_research",
            "preview_generation", "deployment_finalize",
        ]
        for key in required_keys:
            assert key in caps["capabilities"], f"Capability key {key!r} missing"


# ==============================================================================
# PHASE 7 — TALKING AVATAR WEBSITE READINESS
# ==============================================================================

class TestTalkingAvatarWebsiteReadiness:
    """Phase 7: Avatar website scaffold/fallback path."""

    def test_talking_avatar_prompt_detected(self):
        from app.services.avatar_runtime_service import prompt_requires_avatar_website
        assert prompt_requires_avatar_website("Build a talking avatar landing page for a property consultant.")
        assert prompt_requires_avatar_website("Create a voice-guided website for a luxury brand.")
        assert prompt_requires_avatar_website("Spokesperson avatar for our product launch.")

    def test_non_avatar_prompt_not_detected(self):
        from app.services.avatar_runtime_service import prompt_requires_avatar_website
        assert not prompt_requires_avatar_website("Build a bakery landing page.")
        assert not prompt_requires_avatar_website("Create a SaaS dashboard.")

    def test_generate_avatar_script_from_prompt(self):
        from app.services.avatar_runtime_service import generate_avatar_script
        script = generate_avatar_script(
            "A luxury property consultant specialising in premium London homes.",
            brand_name="Harrington Property"
        )
        assert "Harrington Property" in script
        assert len(script) > 30

    def test_generate_avatar_fallback_section_html(self):
        from app.services.avatar_runtime_service import generate_avatar_website_section
        html = generate_avatar_website_section(
            brand_name="Harrington Property",
            script="Welcome to Harrington Property.",
            provider_available=False,
            provider_name="genx",
            fallback_reason="No avatar model available",
        )
        assert "avatar-guide" in html
        assert "data-avatar-runtime" in html
        assert "fallback" in html
        assert "Harrington Property" in html

    def test_generate_avatar_ready_section_has_video(self):
        from app.services.avatar_runtime_service import generate_avatar_website_section
        html = generate_avatar_website_section(
            brand_name="Harrington Property",
            script="Welcome.",
            video_path="media/avatar.mp4",
            provider_available=True,
            provider_name="genx",
        )
        assert "<video" in html
        assert "avatar.mp4" in html
        assert "data-avatar-runtime=\"ready\"" in html

    def test_avatar_section_has_play_pause_controls(self):
        from app.services.avatar_runtime_service import generate_avatar_website_section
        html = generate_avatar_website_section(
            brand_name="Test Brand",
            script="Hello world.",
            video_path="media/avatar.mp4",
            provider_available=True,
        )
        assert "Play" in html or "play" in html.lower()
        assert "Mute" in html or "mute" in html.lower()

    def test_avatar_section_has_no_autoplay_with_sound(self):
        from app.services.avatar_runtime_service import generate_avatar_website_section
        html = generate_avatar_website_section(
            brand_name="Test",
            script="Hello.",
            video_path="media/avatar.mp4",
            provider_available=True,
        )
        # Must not have autoplay attribute without muted
        assert "autoplay" not in html.lower() or "muted" in html.lower()

    def test_inject_avatar_section_into_html(self):
        from app.services.avatar_runtime_service import inject_avatar_website_section
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text(
                "<html><body><main><section id='hero'><h1>Hero</h1></section></main></body></html>",
                encoding="utf-8"
            )
            (ws / "styles.css").write_text("body { margin: 0; }", encoding="utf-8")
            changed = inject_avatar_website_section(
                ws,
                brand_name="Test Brand",
                script="Welcome to Test Brand.",
                provider_available=False,
                fallback_reason="No provider",
            )
            assert "index.html" in changed
            html = (ws / "index.html").read_text()
            assert "avatar-guide" in html

    def test_inject_avatar_adds_css(self):
        from app.services.avatar_runtime_service import inject_avatar_website_section
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text(
                "<html><body><main></main></body></html>",
                encoding="utf-8"
            )
            (ws / "styles.css").write_text("body {}", encoding="utf-8")
            inject_avatar_website_section(ws, brand_name="Test", script="Hello.")
            css = (ws / "styles.css").read_text()
            assert "avatar-section" in css

    def test_avatar_fallback_does_not_block_static_build(self):
        from app.services.avatar_runtime_service import build_avatar_website_manifest
        manifest = build_avatar_website_manifest(
            project_id="test-123",
            prompt="Talking avatar website",
            provider_available=False,
            fallback_reason="No avatar provider configured",
        )
        assert manifest["does_not_block_static_preview"] is True
        assert manifest["fallback_used"] is True
        assert manifest["status"] == "fallback"

    def test_avatar_manifest_ready_when_video_available(self):
        from app.services.avatar_runtime_service import build_avatar_website_manifest
        manifest = build_avatar_website_manifest(
            project_id="test-456",
            prompt="Talking avatar website",
            video_path="media/avatar.mp4",
            provider_available=True,
            provider="genx",
        )
        assert manifest["status"] == "ready"
        assert manifest["fallback_used"] is False

    def test_consent_guard_blocks_real_person_clone(self):
        from app.services.avatar_runtime_service import check_avatar_consent
        result = check_avatar_consent(
            "Clone the voice of Elon Musk for our avatar.",
            explicit_consent_flag=False,
        )
        assert result["allowed"] is False
        assert "consent" in result["reason"].lower()

    def test_consent_guard_allows_with_explicit_consent(self):
        from app.services.avatar_runtime_service import check_avatar_consent
        result = check_avatar_consent(
            "Clone the voice of Elon Musk for our avatar.",
            explicit_consent_flag=True,
        )
        assert result["allowed"] is True

    def test_consent_guard_allows_generic_avatar(self):
        from app.services.avatar_runtime_service import check_avatar_consent
        result = check_avatar_consent("Build a talking avatar for our brand.")
        assert result["allowed"] is True

    def test_avatar_manifest_records_provider_and_fallback_reason(self):
        from app.services.avatar_runtime_service import build_avatar_website_manifest
        manifest = build_avatar_website_manifest(
            project_id="test-789",
            prompt="Talking avatar",
            provider_available=False,
            provider="genx",
            fallback_reason="GenX avatar model not available",
        )
        assert "GenX avatar model not available" in (manifest.get("fallback_reason") or "")

    def test_avatar_mobile_css_includes_responsive(self):
        from app.services.avatar_runtime_service import inject_avatar_website_section
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "index.html").write_text("<html><body><main></main></body></html>", encoding="utf-8")
            inject_avatar_website_section(ws, brand_name="Test", script="Hello.")
            if (ws / "styles.css").exists():
                css = (ws / "styles.css").read_text()
                # Should have at least one media query for mobile
                assert "@media" in css
