import asyncio
import json
import os
import unittest.mock as mock
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.mcp_tools import safe_project_path
from agents.orchestrator import Orchestrator, BuildCancelled
from agents.genx_provider import GenXProvider
from config import valid_fernet_key


def test_safe_project_path_accepts_relative_files():
    assert safe_project_path("src/app.js") == "src/app.js"


def test_safe_project_path_rejects_traversal():
    try:
        safe_project_path("../secret.txt")
    except ValueError as exc:
        assert "traversal" in str(exc)
    else:
        raise AssertionError("path traversal was accepted")


def test_fernet_key_validation():
    assert valid_fernet_key("YW1hcmt0YWktZGV2LWZlcm5ldC1rZXktMzItYnl0ZSE=")


# ---------- orchestrator unit tests ----------

def _make_db(files=None, project_status="running"):
    """Return a mock MongoDB db object with in-memory state."""
    db = MagicMock()
    _project = {"id": "proj1", "status": project_status, "cancel_requested": False}
    _files = list(files or [])
    _events = []
    _messages = []

    async def find_one_project(query, projection=None):
        return dict(_project)

    async def update_one_project(query, update, **kwargs):
        if "$set" in update:
            _project.update(update["$set"])

    async def insert_one_event(doc):
        _events.append(doc)

    async def insert_one_msg(doc):
        _messages.append(doc)

    async def find_files(query, projection=None):
        return list(_files)

    # projects collection
    db.projects.find_one = AsyncMock(side_effect=find_one_project)
    db.projects.update_one = AsyncMock(side_effect=update_one_project)
    # events collection
    db.agent_events.insert_one = AsyncMock(side_effect=insert_one_event)
    db.agent_events.find = MagicMock()
    # messages collection
    db.messages.insert_one = AsyncMock(side_effect=insert_one_msg)
    # files collection — upsert
    db.files.update_one = AsyncMock()
    db.files.find = MagicMock()

    return db, _project, _files, _events, _messages


def _make_provider_ok(json_payload):
    """Return a GenXProvider mock that returns valid JSON."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": json.dumps(json_payload),
        "model_label": "test-model",
        "model": "test-model",
        "session_id": "sess",
        "usage": {},
    })
    return provider


def _make_provider_bad_json(bad_text):
    """Return a GenXProvider mock that returns unparseable text."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": bad_text,
        "model_label": "test-model",
        "model": "test-model",
        "session_id": "sess",
        "usage": {},
    })
    return provider


@pytest.mark.asyncio
async def test_json_parse_failure_does_not_mark_ready():
    """When Coder returns malformed JSON and repair also fails, project must be 'failed', not 'ready'."""
    db, proj, files, events, messages = _make_db()

    # Provider always returns unparseable text (repair also fails)
    provider = _make_provider_bad_json("UNTERMINATED STRING {bad json: 'unclosed")

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)

    # Patch fs.write and fs.list_full to no-ops
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[])
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    with pytest.raises(Exception):
        await orch.run_full_build("Build a dating app")

    # Project must be failed, not ready
    assert proj.get("status") == "failed", f"Expected failed, got {proj.get('status')}"
    # Must not emit ready
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" not in statuses, f"Should not emit ready, got: {statuses}"


@pytest.mark.asyncio
async def test_project_cannot_be_ready_with_no_generated_files():
    """When Coder returns valid JSON but with empty files list, project must be failed."""
    db, proj, files, events, messages = _make_db()
    # Provide valid responses for all agents but coder returns empty files
    call_count = [0]
    responses = [
        # scout
        {"summary": "Dating app", "audience": "singles", "core_features": ["profiles"], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        # coder — empty files
        {"files": [], "summary": "No files"},
    ]

    async def complete_side_effect(**kwargs):
        idx = call_count[0] % len(responses)
        call_count[0] += 1
        return {
            "text": json.dumps(responses[idx]),
            "model_label": "test-model",
            "model": "test-model",
            "session_id": "sess",
            "usage": {},
        }

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_side_effect)

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[])
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    await orch.run_full_build("Build a dating app")

    assert proj.get("status") == "failed", f"Expected failed, got {proj.get('status')}"
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" not in statuses


@pytest.mark.asyncio
async def test_cancel_sets_cancelled_and_stops_pipeline():
    """cancel_requested=True must raise BuildCancelled and mark project cancelled."""
    db, proj, files, events, messages = _make_db()
    # Set cancel flag immediately
    proj["cancel_requested"] = True

    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": json.dumps({"summary": "x", "audience": "y", "core_features": [], "requirements_md": ""}),
        "model_label": "test-model", "model": "test-model", "session_id": "sess", "usage": {},
    })

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[])
    orch.fs.list = AsyncMock(return_value=[])

    # Should not raise — BuildCancelled is caught internally
    await orch.run_full_build("Build a dating app")

    assert proj.get("status") == "cancelled", f"Expected cancelled, got {proj.get('status')}"
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" not in statuses
    assert "cancelled" in statuses


@pytest.mark.asyncio
async def test_iteration_blocked_when_no_app_files():
    """Iteration must not run when there are no app files."""
    db, proj, files, events, messages = _make_db()

    provider = MagicMock()
    provider.complete = AsyncMock()  # should not be called

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    # No app files (only metadata)
    orch.fs.list_full = AsyncMock(return_value=[
        {"path": "requirements.md", "content": "# Reqs", "language": "markdown"},
        {"path": "tech_stack.json", "content": "{}", "language": "json"},
    ])
    orch.fs.write = AsyncMock()

    await orch.run_iteration("Make it blue")

    # Should not call the model at all
    provider.complete.assert_not_called()
    assert proj.get("status") == "failed"
    # Error message should mention the build
    error_msgs = [m["content"] for m in messages if m.get("meta", {}).get("iteration_blocked")]
    assert error_msgs, "Expected an iteration_blocked message"


# ---------- readiness scanner path exclusion ----------

def test_readiness_scanner_never_scans_proc(tmp_path):
    """The new allowlist scanner must never call rglob on /proc or any system path."""
    import server

    proc_called = []

    class FakePath:
        def __init__(self, path):
            self._path = path
        def exists(self):
            return False
        def is_symlink(self):
            return False
        def __truediv__(self, other):
            return FakePath(str(self._path) + "/" + str(other))
        def rglob(self, *args):
            proc_called.append(str(self._path))
            return iter([])
        def __str__(self):
            return str(self._path)

    # Patch _build_scan_roots to return an empty list so scanner exits cleanly
    with mock.patch.object(server, "_build_scan_roots", return_value=[]):
        clean, detail = asyncio.get_event_loop().run_until_complete(server._forbidden_source_check())

    # No /proc paths should have been scanned
    assert not any("/proc" in p for p in proc_called), f"Scanner called rglob on /proc paths: {proc_called}"
    assert clean, f"Scanner should return clean when no roots: {detail}"


def test_readiness_scanner_ignores_system_paths(tmp_path):
    """
    Even if a scan root somehow contains a system-like path,
    the scanner must not flag files in /usr, /lib, etc.
    """
    import server

    # Create a temporary file with no forbidden content
    clean_file = tmp_path / "app.py"
    clean_file.write_text("# clean source file")

    with mock.patch.object(server, "_build_scan_roots", return_value=[clean_file]):
        clean, detail = asyncio.get_event_loop().run_until_complete(server._forbidden_source_check())

    assert clean, f"Scanner wrongly flagged clean file: {detail}"


def test_readiness_scanner_catches_forbidden_in_app_source(tmp_path):
    """Scanner must still catch forbidden strings in explicitly allowlisted app source."""
    import server

    bad_file = tmp_path / "server.py"
    # Write a forbidden string (constructed to avoid triggering this file's own scan)
    forbidden = "".join(("ai", "va"))
    bad_file.write_text(f"# this file uses {forbidden}")

    with mock.patch.object(server, "_build_scan_roots", return_value=[bad_file]):
        clean, detail = asyncio.get_event_loop().run_until_complete(server._forbidden_source_check())

    assert not clean, "Scanner should have caught forbidden reference"
    assert "Legacy reference" in detail


def test_readiness_scanner_skip_env_var(tmp_path):
    """SKIP_SOURCE_SCAN=true must bypass the scanner and return clean."""
    import server

    bad_file = tmp_path / "server.py"
    bad_file.write_text("".join(("ai", "va")))

    with mock.patch.dict(os.environ, {"SKIP_SOURCE_SCAN": "true"}):
        with mock.patch.object(server, "_build_scan_roots", return_value=[bad_file]):
            clean, detail = asyncio.get_event_loop().run_until_complete(server._forbidden_source_check())

    assert clean, "SKIP_SOURCE_SCAN=true should bypass scanner"
    assert "skipped" in detail.lower()


# ---------- quality router ----------

def test_router_tiers_exist():
    """GenXProvider must expose cheap/balanced/premium-equivalent internal tiers."""
    tiers = GenXProvider.list_tiers()
    assert "edits" in tiers or "lightweight" in tiers, "cheap tier missing"
    assert "research" in tiers or "fast" in tiers, "balanced tier missing"
    assert "reasoning" in tiers or "coding" in tiers, "premium tier missing"


# ---------- stack decision engine ----------

from agents.stack_engine import decide_stack, REQUIRED_FILES, ALL_MODES


def test_stack_landing_page():
    """Landing page mode: simple complexity, iframe preview, required files include index.html."""
    sd = decide_stack(prompt="Make a landing page for my startup", mode="landing_page")
    assert sd["recommended_mode"] == "landing_page"
    assert sd["complexity"] == "simple"
    assert sd["preview_strategy"] == "iframe"
    assert "index.html" in sd["required_files"]
    assert "README.md" in sd["required_files"]
    assert "amarktai.project.json" in sd["required_files"]
    assert sd["stack"]["backend"] == "none"


def test_stack_full_stack():
    """Full stack mode: standard complexity, repo_structure preview."""
    sd = decide_stack(prompt="Build a task manager with login", mode="full_stack")
    assert sd["recommended_mode"] == "full_stack"
    assert sd["complexity"] in ("standard", "advanced")
    assert sd["preview_strategy"] == "repo_structure"
    assert "README.md" in sd["required_files"]
    assert ".env.example" in sd["required_files"]
    assert "docker-compose.yml" in sd["required_files"]
    # default stack has react/fastapi
    assert "React" in sd["stack"]["frontend"] or "FastAPI" in sd["stack"]["backend"]


def test_stack_trading_bot_scaffold():
    """Trading bot: high_risk complexity, safety notes, premium recommended."""
    sd = decide_stack(prompt="Build a crypto trading bot", mode="trading_bot_scaffold")
    assert sd["recommended_mode"] == "trading_bot_scaffold"
    assert sd["complexity"] == "high_risk"
    assert sd["recommended_tier"] == "premium"
    assert sd["safety_notes"], "Safety notes must be present for trading bots"
    any_paper = any("paper" in n.lower() for n in sd["safety_notes"])
    assert any_paper, "Paper mode note must be in safety notes"
    assert sd["requires_upgrade_confirmation"] is True


def test_stack_pwa_required_files():
    """PWA mode must require manifest.json and service-worker.js."""
    sd = decide_stack(prompt="Build a PWA timer", mode="pwa")
    assert "manifest.json" in sd["required_files"]
    assert "service-worker.js" in sd["required_files"]
    assert sd["preview_strategy"] == "iframe"


def test_stack_research_mode():
    """Research mode: simple, brief_only preview, no required files."""
    sd = decide_stack(prompt="Research the best stack for ecommerce", mode="research")
    assert sd["recommended_mode"] == "research"
    assert sd["preview_strategy"] == "brief_only"
    assert sd["complexity"] == "simple"
    assert sd["required_files"] == []


def test_stack_cheap_tier_complex_warns():
    """Cheap tier on a complex project must require upgrade confirmation."""
    sd = decide_stack(prompt="Build a full-stack app with login", mode="full_stack", quality_tier="cheap")
    assert sd["requires_upgrade_confirmation"] is True
    assert sd["upgrade_reason"] is not None


def test_stack_unknown_mode_defaults_web_app():
    """Unknown mode must fall back to web_app without raising."""
    sd = decide_stack(prompt="Build something", mode="not_a_real_mode")
    assert sd["recommended_mode"] == "web_app"


def test_required_files_by_mode():
    """REQUIRED_FILES must cover all non-research modes with at least README.md."""
    for mode in ALL_MODES:
        if mode == "research":
            continue
        files = REQUIRED_FILES.get(mode, [])
        assert "README.md" in files or mode in ("repo_fix",), \
            f"Mode {mode} is missing README.md in required files"


# ---------- project manifest generation ----------

def test_project_manifest_json_structure():
    """amarktai.project.json content matches expected schema."""
    import json
    manifest = {
        "name": "My App",
        "mode": "web_app",
        "stack": {"frontend": "HTML + CSS + Vanilla JS", "backend": "none"},
        "generated_by": "Amarktai App Builder",
        "version": "1.0.0",
    }
    text = json.dumps(manifest)
    parsed = json.loads(text)
    assert parsed["generated_by"] == "Amarktai App Builder"
    assert "mode" in parsed
    assert "stack" in parsed


# ---------- mode-aware orchestrator ----------

@pytest.mark.asyncio
async def test_research_mode_produces_requirements_md():
    """Research mode must write requirements.md and mark project ready without app files."""
    db, proj, files, events, messages = _make_db()
    research_response = {
        "research_brief": "# Research\nThis is a brief",
        "recommended_mode": "web_app",
        "recommended_tier": "balanced",
        "build_prompt": "Build a task manager",
        "summary": "Research complete",
    }
    provider = _make_provider_ok(research_response)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[{"path": "requirements.md", "content": "# Research"}])
    orch.fs.list = AsyncMock(return_value=[{"path": "requirements.md"}])
    orch.fs.read = AsyncMock(return_value=None)

    await orch.run_full_build("Research ecommerce stacks", mode="research")

    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" in statuses, f"Research mode must reach ready. Got: {statuses}"


@pytest.mark.asyncio
async def test_full_stack_mode_readme_required():
    """Full-stack mode must fail if README.md is not in generated files."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    responses = [
        # scout
        {"summary": "App", "audience": "devs", "core_features": ["api"], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "React", "styling": "Tailwind"}, "file_plan": [{"path": "server.py", "purpose": "backend"}]},
        # coder — no README.md
        {"files": [{"path": "server.py", "language": "python", "content": "# backend"}], "summary": "Done"},
    ]

    async def complete_side_effect(**kwargs):
        idx = call_count[0] % len(responses)
        call_count[0] += 1
        return {"text": json.dumps(responses[idx]), "model_label": "test", "model": "test", "session_id": "s", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_side_effect)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()

    written_files = []

    async def fake_write(path, content, lang="text"):
        written_files.append({"path": path, "content": content, "language": lang})

    orch.fs.write = fake_write

    async def fake_list_full():
        return list(written_files)

    orch.fs.list_full = fake_list_full
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    # Use full_stack mode with reviewer that returns pass
    reviewer_resp = {"verdict": "pass", "issues": [], "patched_files": [], "summary": "OK"}
    call_count_2 = [0]
    all_responses = responses + [reviewer_resp]

    async def complete_se2(**kwargs):
        idx = call_count_2[0] % len(all_responses)
        call_count_2[0] += 1
        return {"text": json.dumps(all_responses[idx]), "model_label": "test", "model": "test", "session_id": "s", "usage": {}}

    provider.complete = AsyncMock(side_effect=complete_se2)

    await orch.run_full_build("Build a full-stack app", mode="full_stack")

    # full_stack mode requires README.md — should fail
    assert proj.get("status") == "failed", f"Expected failed for full_stack without README.md, got {proj.get('status')}"

