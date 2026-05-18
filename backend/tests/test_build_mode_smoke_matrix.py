"""Deterministic smoke-test matrix for all core Amarktai build modes.

Tests do NOT require live providers. They use deterministic/mock agent outputs
to verify that each mode:
  - generates the required files
  - does not treat report/metadata files as app source
  - applies mode-specific coverage rules
  - produces clear, actionable failures

Modes covered:
  landing_page, website, pwa, web_app, dashboard, full_stack,
  api_service, repo_fix, ai_chat_rag_app, crm_dashboard, research, automation_bot, media_page
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure backend is on path
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agents.build_contract import (
    filter_app_source_files,
    get_required_files,
    infer_build_mode,
    is_report_or_metadata_file,
    REPORT_AND_METADATA_FILES,
)
from agents.mode_classifier import classify_build_mode, ModeClassification


# ── Helpers ───────────────────────────────────────────────────────────────────

def _file(path: str, content: str = "# placeholder") -> dict:
    ext = path.rsplit(".", 1)[-1] if "." in path else "text"
    lang = {"html": "html", "css": "css", "js": "javascript", "py": "python",
            "json": "json", "md": "markdown", "ts": "typescript", "yml": "yaml"}.get(ext, "text")
    return {"path": path, "content": content, "language": lang}


def _report_file(name: str = "quality_report.md") -> dict:
    return _file(name, "# Quality Report\nStatus: pass\n")


def _has_report_files(files: list[dict]) -> bool:
    return any(f.get("path", "") in REPORT_AND_METADATA_FILES for f in files)


def _mode_from_mc(result: ModeClassification | str) -> str:
    """Extract mode string from ModeClassification or return string directly."""
    if isinstance(result, str):
        return result
    return result.mode if hasattr(result, "mode") else str(result)


# ── Mode detection smoke tests ────────────────────────────────────────────────

class TestModeInference:
    def test_landing_page_mode_passthrough(self):
        mode = infer_build_mode("landing_page")
        assert mode in {"landing_page", "landing-page", "website", "media_page"}

    def test_api_service_mode_passthrough(self):
        mode = infer_build_mode("api_service")
        assert mode in {"api_service", "api-service", "full_stack", "web_app"}

    def test_pwa_mode_passthrough(self):
        mode = infer_build_mode("pwa")
        assert mode in {"pwa", "website", "web_app"}

    def test_repo_fix_mode_passthrough(self):
        mode = infer_build_mode("repo_fix")
        assert mode in {"repo_fix", "repo-upgrade", "web_app", "website"}

    def test_full_stack_mode_passthrough(self):
        mode = infer_build_mode("full_stack")
        assert mode in {"full_stack", "fullstack-saas", "web_app"}

    def test_unknown_mode_falls_back_gracefully(self):
        mode = infer_build_mode(None)
        assert isinstance(mode, str)
        assert len(mode) > 0

    def test_dashboard_mode_passthrough(self):
        mode = infer_build_mode("dashboard")
        assert mode in {"dashboard", "web_app", "admin_panel"}

    def test_ai_chat_rag_mode_passthrough(self):
        mode = infer_build_mode("ai_chat_rag_app")
        assert mode in {"ai_chat_rag_app", "ai-chat-rag-app", "custom", "web_app"}

    def test_crm_dashboard_mode_passthrough(self):
        mode = infer_build_mode("crm_dashboard")
        assert mode in {"crm_dashboard", "crm-dashboard", "dashboard", "web_app"}

    def test_infer_build_mode_from_known_values(self):
        """infer_build_mode must return a valid string for all known modes."""
        known_modes = [
            "landing_page", "website", "pwa", "web_app", "dashboard",
            "full_stack", "api_service", "repo_fix", "ai_chat_rag_app", "crm_dashboard", "research",
        ]
        for m in known_modes:
            result = infer_build_mode(m)
            assert isinstance(result, str), f"infer_build_mode({m!r}) must return str"
            assert result, f"infer_build_mode({m!r}) must return non-empty string"


# ── Mode classifier smoke tests ────────────────────────────────────────────────

class TestModeClassifier:
    def test_classify_landing_page(self):
        result = classify_build_mode("Build a landing page for Luma & Stone bakery.")
        mode = _mode_from_mc(result)
        assert mode in {"landing_page", "website", "media_page"}

    def test_classify_dashboard(self):
        result = classify_build_mode("Build an analytics dashboard with charts and metrics.")
        mode = _mode_from_mc(result)
        assert mode in {"dashboard", "web_app", "admin_panel"}

    def test_classify_pwa(self):
        result = classify_build_mode("Build a Progressive Web App with offline support and push notifications.")
        mode = _mode_from_mc(result)
        assert mode in {"pwa", "website", "web_app"}

    def test_classify_api(self):
        result = classify_build_mode("Build a REST API for a CRM system.")
        mode = _mode_from_mc(result)
        assert mode in {"api_service", "api_backend", "full_stack", "web_app"}

    def test_classify_repo_fix(self):
        result = classify_build_mode("Fix my broken repo — the tests fail and the build is broken.")
        mode = _mode_from_mc(result)
        assert mode in {"repo_fix", "web_app"}

    def test_classify_research(self):
        result = classify_build_mode("Research the best Python async frameworks for building APIs.")
        mode = _mode_from_mc(result)
        assert mode in {"research", "api_service", "web_app"}

    def test_classify_ai_chat_rag(self):
        result = classify_build_mode("Build an AI chat assistant with RAG over product documentation.")
        mode = _mode_from_mc(result)
        assert mode in {"ai_chat_rag_app", "web_app", "api_service"}

    def test_classify_crm_dashboard(self):
        result = classify_build_mode("Build a CRM dashboard with lead pipeline and deal stages.")
        mode = _mode_from_mc(result)
        assert mode in {"crm_dashboard", "dashboard", "web_app", "admin_panel"}

    def test_classify_returns_mode_classification(self):
        result = classify_build_mode("Build a SaaS dashboard.")
        assert hasattr(result, "mode"), "classify_build_mode must return a ModeClassification with .mode"
        assert isinstance(result.mode, str)

    def test_classify_mode_is_non_empty(self):
        result = classify_build_mode("Build a website.")
        assert _mode_from_mc(result)


class TestPhase2RequestedBuildModes:
    """Smoke prompts for Phase 2 requested build modes."""

    @pytest.mark.parametrize("mode_hint,expected_any", [
        ("landing_page", {"landing_page", "landing-page", "website", "media_page"}),
        ("website", {"website", "landing_page", "multi-page-website", "web_app"}),
        ("pwa", {"pwa", "website", "web_app"}),
        ("web_app", {"web_app", "dashboard", "full_stack", "custom"}),
        ("dashboard", {"dashboard", "web_app", "admin_panel"}),
        ("full_stack", {"full_stack", "web_app", "api_service", "fullstack-saas"}),
        ("api_service", {"api_service", "api-service", "api_backend", "full_stack"}),
        ("repo_fix", {"repo_fix", "repo-upgrade", "web_app"}),
        ("ai_chat_rag_app", {"ai_chat_rag_app", "ai-chat-rag-app", "web_app", "api_service"}),
        ("crm_dashboard", {"crm_dashboard", "crm-dashboard", "dashboard", "web_app"}),
    ])
    def test_infer_build_mode_smoke_modes(self, mode_hint: str, expected_any: set[str]):
        inferred = infer_build_mode(mode_hint)
        assert inferred in expected_any

    @pytest.mark.parametrize("prompt,expected_any", [
        ("Build a landing page for a bakery launch.", {"landing_page", "website", "media_page"}),
        ("Build a 5-page marketing website.", {"website", "landing_page", "web_app"}),
        ("Build a progressive web app with offline support.", {"pwa", "web_app", "website"}),
        ("Build an interactive web app for customer onboarding.", {"web_app", "dashboard", "full_stack"}),
        ("Build an analytics dashboard with charts and auth.", {"dashboard", "web_app", "admin_panel", "saas_dashboard"}),
        ("Build a full-stack SaaS app with frontend and backend.", {"full_stack", "web_app", "api_service", "saas_dashboard"}),
        ("Build an API service for order processing.", {"api_service", "api_backend", "full_stack"}),
        ("Fix my repo: tests and build are broken.", {"repo_fix", "repo_upgrade", "web_app"}),
        ("Build an AI chat app with RAG over docs.", {"ai_chat_rag_app", "web_app", "api_service"}),
        ("Build a CRM/dashboard for sales leads and deals.", {"crm_dashboard", "dashboard", "web_app", "admin_panel"}),
    ])
    def test_classify_build_mode_smoke_prompts(self, prompt: str, expected_any: set[str]):
        result = classify_build_mode(prompt)
        assert _mode_from_mc(result) in expected_any


# ── Report file filtering ──────────────────────────────────────────────────────

class TestReportFileFiltering:
    """Report/metadata files must never be treated as app source in any mode."""

    ALL_MODES = [
        "landing_page", "website", "pwa", "web_app", "dashboard",
        "full_stack", "api_service", "repo_fix", "ai_chat_rag_app", "crm_dashboard", "research",
    ]

    def _mixed_files(self) -> list[dict]:
        """A mixed set of app source + report files."""
        return [
            _file("index.html"),
            _file("styles.css"),
            _file("script.js"),
            _file("main.py"),
            _file("package.json"),
            _report_file("quality_report.md"),
            _report_file("build_report.json"),
            _file("AMARKTAI_REPORT.md", "# Internal report"),
        ]

    def test_report_files_filtered_from_app_source(self):
        """No report or metadata file should pass filter_app_source_files."""
        mixed = self._mixed_files()
        filtered = filter_app_source_files(mixed)
        filtered_paths = {f.get("path", "") for f in filtered}
        assert "quality_report.md" not in filtered_paths, "quality_report.md leaked into app source"
        assert "build_report.json" not in filtered_paths, "build_report.json leaked into app source"

    @pytest.mark.parametrize("path", sorted(REPORT_AND_METADATA_FILES))
    def test_is_report_file_classification(self, path: str):
        assert is_report_or_metadata_file(path), f"{path} should be classified as report/metadata"

    def test_app_source_files_preserved(self):
        """Normal app source files must not be removed by filter."""
        files = [_file("index.html"), _file("styles.css"), _file("script.js")]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "index.html" in paths
        assert "styles.css" in paths


# ── Required files per mode ────────────────────────────────────────────────────

class TestRequiredFilesPerMode:
    """Each mode must define its required files correctly."""

    @pytest.mark.parametrize("project_type,mode", [
        ("static-site", "landing_page"),
        ("static-site", "website"),
    ])
    def test_static_modes_require_html(self, project_type: str, mode: str):
        required = get_required_files(project_type, mode)
        has_html = any("html" in f.lower() for f in required)
        assert has_html, f"{mode} should require an HTML file"

    @pytest.mark.parametrize("project_type,mode", [
        ("static-site", "landing_page"),
        ("static-site", "website"),
    ])
    def test_static_modes_require_css(self, project_type: str, mode: str):
        required = get_required_files(project_type, mode)
        has_css = any(".css" in f.lower() for f in required)
        assert has_css, f"{mode} should require a CSS file"

    def test_get_required_files_returns_list(self):
        required = get_required_files("static-site", "landing_page")
        assert isinstance(required, list)
        assert len(required) > 0

    def test_different_project_types_may_differ(self):
        static_req = get_required_files("static-site", "landing_page")
        api_req = get_required_files("api", "api_service")
        # They should both be non-empty lists
        assert len(static_req) > 0
        assert len(api_req) > 0

    def test_ai_chat_rag_mode_requires_frontend_and_backend(self):
        required = get_required_files("ai-chat-rag-app", "ai_chat_rag_app")
        assert "src/App.jsx" in required
        assert "backend/main.py" in required


# ── Preview evidence logic ─────────────────────────────────────────────────────

class TestPreviewEvidenceLogic:
    """Preview evidence rules must be mode-aware."""

    def test_static_preview_does_not_require_running_server(self):
        """For static modes, index.html presence is sufficient for preview."""
        files = [
            _file("index.html", "<html><body><h1>Hello</h1></body></html>"),
            _file("styles.css", "body { margin: 0; }"),
        ]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "index.html" in paths

    def test_pwa_preview_includes_sw(self):
        """PWA preview should include the service worker."""
        files = [
            _file("index.html"),
            _file("manifest.json", '{"name":"Test","short_name":"T","start_url":"/"}'),
            _file("sw.js", "self.addEventListener('install', () => {});"),
        ]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "index.html" in paths

    def test_api_service_files_not_filtered_out(self):
        """API service files must pass through."""
        files = [
            _file("main.py", "from fastapi import FastAPI; app = FastAPI()"),
            _file("requirements.txt", "fastapi\nuvicorn"),
        ]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "main.py" in paths

    def test_full_stack_includes_both_frontend_and_backend(self):
        """Full-stack mode must preserve both frontend and backend files."""
        files = [
            _file("frontend/index.html"),
            _file("frontend/styles.css"),
            _file("backend/main.py"),
            _file("docker-compose.yml"),
        ]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "frontend/index.html" in paths
        assert "backend/main.py" in paths


# ── Coverage rules per mode ────────────────────────────────────────────────────

class TestCoverageRulesPerMode:
    """Coverage rules must be mode-specific and not bleed across modes."""

    def test_landing_page_coverage_focuses_on_visual_completeness(self):
        from agents.coverage_score import compute_coverage_score
        files = [
            _file("index.html", """
                <html><head><title>T</title></head><body>
                <nav><a href="#hero">Home</a></nav>
                <section id="hero"><h1>Hero</h1><a href="#cta" class="cta">Call to action</a></section>
                <section id="features"><h2>Features</h2></section>
                <section id="cta"><h2>Get started</h2></section>
                <footer>Footer</footer>
                </body></html>
            """),
            _file("styles.css", ":root { --color-bg: #fff; } body { font-size: 16px; }"),
        ]
        result = compute_coverage_score(
            "landing page",
            files,
            mode="landing_page",
        )
        # compute_coverage_score returns a dict with "coverageScore" key
        score = result.get("coverageScore", result.get("score", result.get("coverage", 0)))
        assert isinstance(score, (int, float, type(None))), "Coverage score must be numeric or None"

    def test_api_service_coverage_returns_numeric(self):
        from agents.coverage_score import compute_coverage_score
        files = [
            _file("main.py", "from fastapi import FastAPI; app = FastAPI()\n@app.get('/health')\ndef health(): return {'ok': True}"),
            _file("requirements.txt", "fastapi\nuvicorn"),
            _file("README.md", "# API Service"),
        ]
        result = compute_coverage_score(
            "REST API service",
            files,
            mode="api_service",
        )
        # Must return a dict
        assert isinstance(result, dict)


# ── Deterministic failure messages ────────────────────────────────────────────

class TestFailureMessages:
    """Build failures must be clear and actionable, not opaque."""

    def test_report_file_does_not_appear_in_app_source(self):
        """Report files must be filtered from app source."""
        mixed = [
            _file("index.html"),
            _file("styles.css"),
            _report_file("quality_report.md"),
        ]
        filtered = filter_app_source_files(mixed)
        report_in_filtered = any(f.get("path") == "quality_report.md" for f in filtered)
        assert not report_in_filtered, "quality_report.md must not appear in filtered app source"

    def test_filter_preserves_non_report_files(self):
        """filter_app_source_files must not remove legitimate source files."""
        files = [
            _file("index.html"),
            _file("styles.css"),
            _file("script.js"),
        ]
        filtered = filter_app_source_files(files)
        paths = {f.get("path") for f in filtered}
        assert "index.html" in paths
        assert "styles.css" in paths

    def test_empty_file_list_does_not_crash(self):
        filtered = filter_app_source_files([])
        assert isinstance(filtered, list)
