from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.build_contract import enforce_static_contract_files, filter_app_source_files
from agents.orchestrator import Orchestrator
from app.services.media_runtime_service import execute_media_plan


def test_source_report_split_excludes_internal_artifacts():
    files = [
        {"path": "index.html", "content": "<html></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "content_quality_report.json", "content": "{}"},
        {"path": "media_manifest.json", "content": "{}"},
        {"path": "runtime-qa/runtime-qa-report.json", "content": "{}"},
    ]
    app_paths = [f["path"] for f in filter_app_source_files(files)]
    assert app_paths == ["index.html", "styles.css"]


def test_ensure_contract_files_skips_non_ensured_changes_without_keyerror(monkeypatch):
    class _Projects:
        async def find_one(self, *_args, **_kwargs):
            return {"id": "p1", "mode": "landing_page"}

    db = SimpleNamespace(projects=_Projects(), agent_events=SimpleNamespace(insert_one=AsyncMock()))
    emitted = []

    async def emit(payload):
        emitted.append(payload)

    orch = Orchestrator(db, SimpleNamespace(), "p1", emit)
    orch.fs = SimpleNamespace(
        list_full=AsyncMock(return_value=[]),
        write=AsyncMock(),
    )

    def fake_ensure_required_files(_project, _prompt, _plan, _files):
        return ([{"path": "index.html", "language": "html", "content": "<html></html>"}], ["content_quality_report.json", "index.html"])

    monkeypatch.setattr("agents.orchestrator.ensure_required_files", fake_ensure_required_files)
    asyncio.run(orch._ensure_contract_files("prompt", {}))

    orch.fs.write.assert_awaited_once()
    assert orch.fs.write.await_args.args[0] == "index.html"
    assert any(event.get("type") == "required_files_change_skipped" for event in emitted)


def test_truncated_html_recovery_repairs_anchor_targets_for_bakery_prompt():
    prompt = "premium cinematic luxury artisan bakery landing page fixture bakery"
    broken = [
        {
            "path": "index.html",
            "language": "html",
            "content": "<!doctype html><html><body><nav><a href='#menu'>Menu</a><a href='#story'>Story</a><a href='#gallery'>Gallery</a><a href='#contact'>Contact</a><a href='#events'>Events</a></nav><main><section id='hero'><svg rx=\"48",
        },
    ]
    repaired, _changed = enforce_static_contract_files({"mode": "landing_page", "quality_tier": "premium"}, prompt, {}, broken)
    html = next(item["content"] for item in repaired if item["path"] == "index.html")
    ids = set(__import__("re").findall(r'id=["\']([^"\']+)["\']', html))
    href_ids = set(__import__("re").findall(r'href=["\']#([^"\']+)["\']', html))
    assert "</html>" in html
    assert "</body>" in html
    assert "<footer" in html.lower()
    assert href_ids.issubset(ids)
    assert {"menu", "story", "gallery", "contact"}.issubset(ids)


def test_media_manifest_status_never_missing_for_premium_static(tmp_path: Path):
    manifest = asyncio.run(
        execute_media_plan(
            tmp_path,
            project_id="p1",
            prompt="premium cinematic bakery landing page",
            sections=["hero", "gallery", "contact"],
            allow_stock_fallback=False,
        )
    )
    assert manifest["status"] in {"ai_generated", "stock", "fallback", "setup_needed"}
    assert manifest["status"] != "missing"


def test_go_live_status_includes_firecrawl_and_self_tests(monkeypatch):
    import server

    async def fake_truth():
        return {
            "providers": {"firecrawl": {"configured": False, "live_status": "setup_needed", "reason": "FIRECRAWL_API_KEY not configured"}},
            "summary": {
                "runtime_qa": {"available": True, "live_status": "local"},
                "playwright": {"live_status": "setup_needed"},
                "lighthouse": {"live_status": "setup_needed"},
                "axe_core": {"live_status": "setup_needed"},
            },
        }

    monkeypatch.setattr(server, "_capability_truth", fake_truth)
    result = asyncio.run(server.go_live_status())
    names = {check["name"] for check in result["checks"]}
    assert "Firecrawl provider status" in names
    assert "source/report split self-test" in names
    assert "truncated HTML recovery self-test" in names

