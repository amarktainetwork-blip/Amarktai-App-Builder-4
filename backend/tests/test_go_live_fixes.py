from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def test_normalize_build_context_missing_audience_does_not_crash():
    from app.services.build_context_service import DEFAULT_AUDIENCE, ensure_build_context_defaults, normalize_build_context

    ctx = normalize_build_context(
        "Create a premium production-ready landing page for Amarktai Builder.",
        project_name="Amarktai Builder",
        build_mode="landing_page",
        planner_output="# Plan\n- Hero\n- FAQ",
        scout_output="## Features\n- Live preview\n- Repo repair",
        settings={"quality_tier": "premium"},
    )

    assert ctx["audience"] == DEFAULT_AUDIENCE
    assert ctx["target_audience"] == DEFAULT_AUDIENCE
    assert ctx["brand_name"] == "Amarktai Builder"
    assert ctx["mode"] == "landing_page"
    assert ctx["seo_required"] is True
    assert ctx["preview_required"] is True

    partial = ensure_build_context_defaults({"brand_name": "Amarktai Builder"})
    assert partial["audience"] == DEFAULT_AUDIENCE
    assert partial["target_audience"] == DEFAULT_AUDIENCE


def test_landing_page_required_files_are_react_contract():
    from agents.build_contract import get_required_files

    required = get_required_files(
        "react-app",
        "landing-page",
        "Create a premium production-ready landing page for a luxury AI app-building platform.",
        {},
    )

    assert "package.json" in required
    assert "src/App.jsx" in required
    assert "src/App.css" in required
    assert "README.md" in required
    assert "preview-manifest.json" in required


def test_builds_route_is_mounted_and_returns_items(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    import server

    routes = {
        (route.path, ",".join(sorted(getattr(route, "methods", []) or [])))
        for route in server.app.router.routes
    }
    assert any(path == "/api/builds" and "GET" in methods for path, methods in routes)

    result = asyncio.run(server.list_builds(workspace_type="generated", claims={"sub": "test"}))
    assert result["items"] == []
    assert result["total"] == 0
    assert result["storage_root"] == str(tmp_path.resolve())
    assert "generated" in result["workspace_types"]


def test_preview_static_start_status_url_and_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    from app.services.build_storage_service import create_generated_workspace
    from app.services.preview_process_service import load_preview_state, start_preview, stop_preview

    meta = create_generated_workspace("preview-test")
    ws = Path(meta["local_path"])
    (ws / "index.html").write_text("<html><body><h1>Preview</h1></body></html>", encoding="utf-8")

    started = start_preview("preview-test", ws)
    assert started["status"] == "running"
    assert started["kind"] == "static"
    assert "/preview/static/index.html" in started["url"]
    assert load_preview_state("preview-test")["status"] == "running"
    assert stop_preview("preview-test")["status"] == "stopped"


def test_quality_gate_catches_placeholder_and_dead_cta(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    (tmp_path / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body><a href='#'>Start</a><button>Buy now</button><p>Lorem ipsum</p></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Test", encoding="utf-8")
    (tmp_path / "preview-manifest.json").write_text("{}", encoding="utf-8")

    report = run_quality_gate(tmp_path)
    warning_checks = {item["check"] for item in report["warnings"]}
    assert "placeholders" in warning_checks
    assert "dead_ctas" in warning_checks
    assert (tmp_path / "quality-report.json").exists()
