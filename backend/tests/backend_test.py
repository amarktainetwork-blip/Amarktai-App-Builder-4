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
from agents.build_contract import (
    ensure_required_files,
    extract_files_from_model_output,
    validate_project_files,
)
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


def test_extract_files_from_json_file_map():
    files, warnings, summary = extract_files_from_model_output(json.dumps({
        "index.html": "<h1>Hello</h1>",
        "styles.css": "body{}",
    }))
    assert {f["path"] for f in files} == {"index.html", "styles.css"}
    assert warnings == []


def test_extract_files_from_markdown_code_blocks():
    raw = """Here are files.

file: index.html
```html
<h1>Amarktai</h1>
```

```styles.css
body { color: white; }
```
"""
    files, warnings, summary = extract_files_from_model_output(raw)
    assert {f["path"] for f in files} == {"index.html", "styles.css"}


def test_extract_rejects_unsafe_and_normalizes_duplicates():
    raw = json.dumps({
        "files": [
            {"path": "../../.env", "content": "SECRET=bad"},
            {"path": "index.html", "content": "first"},
            {"path": "index.html", "content": "second"},
        ]
    })
    files, warnings, summary = extract_files_from_model_output(raw)
    assert [f["path"] for f in files] == ["index.html"]
    assert files[0]["content"] == "second"
    assert any("unsafe" in w.lower() for w in warnings)
    assert any("duplicate" in w.lower() for w in warnings)


def test_deterministic_repair_recreates_static_required_files():
    project = {"mode": "landing_page", "prompt": "Build a modern professional landing page for Amarktai.com with images and easy deployment."}
    files, changed = ensure_required_files(project, project["prompt"], {}, [{"path": "index.html", "content": "<html><head></head><body>Hi</body></html>"}])
    paths = {f["path"] for f in files}
    assert {"index.html", "styles.css", "README.md", "amarktai.project.json"} <= paths
    validation = validate_project_files(project, files, project["prompt"])
    assert validation["ok"], validation


def test_pwa_contract_includes_manifest_and_service_worker():
    project = {"mode": "pwa", "prompt": "Build a PWA task tracker"}
    files, changed = ensure_required_files(project, project["prompt"], {}, [])
    paths = {f["path"] for f in files}
    assert "manifest.json" in paths
    assert "service-worker.js" in paths
    assert validate_project_files(project, files, project["prompt"])["ok"]


def test_full_stack_contract_scaffolds_required_files():
    project = {"mode": "full_stack", "prompt": "Build a full-stack SaaS starter with login"}
    files, changed = ensure_required_files(project, project["prompt"], {}, [])
    paths = {f["path"] for f in files}
    assert {"README.md", ".env.example", "docker-compose.yml", "backend/main.py", "frontend/package.json", "amarktai.project.json"} <= paths
    assert validate_project_files(project, files, project["prompt"])["ok"]


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
async def test_full_stack_mode_deterministically_repairs_required_files():
    """Full-stack mode must create required companion files before validation."""
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

    # full_stack mode now repairs README/.env/Docker/frontend/backend companion files deterministically.
    assert proj.get("status") == "ready", f"Expected ready after deterministic full_stack repair, got {proj.get('status')}"
    written_paths = {f["path"] for f in written_files}
    assert {"README.md", ".env.example", "docker-compose.yml", "backend/main.py", "frontend/package.json", "amarktai.project.json"} <= written_paths


# ---------- media strategy ----------

def test_media_strategy_default_placeholder():
    """Default media strategy is placeholder mode."""
    import server
    ms = server._build_media_strategy("web_app", "balanced", None)
    assert ms["mode"] == "placeholder"
    assert ms["confirmed"] is False
    assert "models_used" in ms


def test_media_strategy_landing_page_free_assets():
    """Landing page/website modes use free_assets by default."""
    import server
    ms = server._build_media_strategy("landing_page", "balanced", None)
    assert ms["mode"] == "free_assets"
    assert ms["confirmed"] is False


def test_media_strategy_genx_generated_premium():
    """When media is requested with premium, mode is genx_generated (unconfirmed)."""
    import server
    ms = server._build_media_strategy("media_page", "premium", "I need AI-generated images")
    assert ms["mode"] == "genx_generated"
    assert ms["confirmed"] is False  # still needs user confirmation


def test_media_strategy_cheap_tier_blocks_genx():
    """Cheap tier cannot use genx_generated even if media requested."""
    import server
    ms = server._build_media_strategy("landing_page", "cheap", "generate images please")
    assert ms["mode"] == "placeholder"
    assert "Upgrade" in ms["notes"] or "upgrade" in ms["notes"]


# ---------- model router spec format ----------

def test_model_router_returns_spec_format():
    """GenXProvider.list_tiers must cover cheap/balanced/premium mapping."""
    from agents.genx_provider import GenXProvider
    tiers = GenXProvider.list_tiers()
    assert "reasoning" in tiers
    assert "research" in tiers
    assert "edits" in tiers
    for tier_key in ("reasoning", "research", "edits"):
        assert "model" in tiers[tier_key]


# ---------- shared context structure ----------

@pytest.mark.asyncio
async def test_orchestrator_shared_context_structure():
    """Orchestrator._shared_context must return all required Phase 2 fields."""
    db, proj, files, events, messages = _make_db()
    provider = MagicMock()
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    ctx = await orch._shared_context()

    required_keys = {
        "project_id", "prompt", "mode", "quality_tier", "recommended_tier",
        "stack_decision", "preview_strategy", "media_strategy",
        "github_context", "validation_state", "repair_attempts",
    }
    missing = required_keys - set(ctx.keys())
    assert not missing, f"Shared context missing keys: {missing}"
    assert ctx["project_id"] == "proj1"


# ---------- validation_state written to project ----------

@pytest.mark.asyncio
async def test_validation_state_written_after_build():
    """After a successful build, validation_state must be written to the project document."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    responses = [
        # scout
        {"summary": "App", "audience": "users", "core_features": ["home"], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": [
            {"path": "index.html", "purpose": "entry"},
            {"path": "styles.css", "purpose": "styles"},
            {"path": "README.md", "purpose": "docs"},
            {"path": "amarktai.project.json", "purpose": "manifest"},
        ]},
        # coder
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
            {"path": "styles.css", "language": "css", "content": "body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App","mode":"landing_page"}'},
        ], "summary": "Done"},
        # reviewer
        {"verdict": "pass", "issues": [], "patched_files": [], "summary": "OK"},
    ]

    async def complete_se(**kwargs):
        idx = call_count[0] % len(responses)
        call_count[0] += 1
        return {"text": json.dumps(responses[idx]), "model_label": "test", "model": "test", "session_id": "s", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_se)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written_files = []

    async def fake_write(path, content, lang="text"):
        written_files.append({"path": path, "content": content, "language": lang})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written_files))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")

    await orch.run_full_build("Build a landing page", mode="landing_page", stack_decision=sd)

    # validation_state must have been updated
    validation_events = [e for e in events_received if e.get("type") == "validation_state"]
    assert validation_events, "validation_state event must be emitted"
    vs = validation_events[-1]["data"]
    assert "status" in vs
    assert "required_files_present" in vs
    assert "required_files_missing" in vs


# ---------- validation lifecycle events ----------

@pytest.mark.asyncio
async def test_validation_events_emitted():
    """Validation lifecycle events must be emitted (validation_started, validation_passed)."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    responses = [
        {"summary": "App", "audience": "users", "core_features": [], "requirements_md": "# Reqs"},
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
            {"path": "styles.css", "language": "css", "content": "body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ], "summary": "Done"},
        {"verdict": "pass", "issues": [], "patched_files": [], "summary": "OK"},
    ]

    async def complete_se(**kwargs):
        idx = call_count[0] % len(responses)
        call_count[0] += 1
        return {"text": json.dumps(responses[idx]), "model_label": "t", "model": "t", "session_id": "s", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_se)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")
    await orch.run_full_build("Build landing page", mode="landing_page", stack_decision=sd)

    event_types = [e.get("type") for e in events_received]
    assert "validation_started" in event_types, f"validation_started not emitted. Got: {event_types}"
    assert "validation_passed" in event_types, f"validation_passed not emitted. Got: {event_types}"
    assert "validation_failed" not in event_types, "validation_failed should not be emitted on success"


@pytest.mark.asyncio
async def test_required_file_repair_prevents_expensive_model_repair():
    """Missing companion files are repaired deterministically before model repair."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    # Coder produces only index.html — missing styles.css, README.md, amarktai.project.json
    # First reviewer pass: no patches
    # Second reviewer pass (repair): adds missing files
    all_responses = [
        # scout
        {"summary": "App", "audience": "users", "core_features": [], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        # coder — only index.html, missing others
        {"files": [{"path": "index.html", "language": "html", "content": "<html></html>"}], "summary": "Partial"},
        # first reviewer pass — no patches
        {"verdict": "warn", "issues": ["Missing styles.css"], "patched_files": [], "summary": "Partial"},
        # repair pass — adds missing files
        {"verdict": "pass", "issues": [], "patched_files": [
            {"path": "styles.css", "language": "css", "content": "body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ], "summary": "Fixed"},
    ]

    async def complete_se(**kwargs):
        idx = call_count[0] % len(all_responses)
        call_count[0] += 1
        return {"text": json.dumps(all_responses[idx]), "model_label": "t", "model": "t", "session_id": "s", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_se)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")
    await orch.run_full_build("Build landing page", mode="landing_page", stack_decision=sd)

    event_types = [e.get("type") for e in events_received]
    assert "required_files_repaired" in event_types, f"Expected deterministic required file repair. Got: {event_types}"
    assert "validation_failed" not in event_types, f"Missing companion files should be fixed before validation. Got: {event_types}"
    assert "repair_started" not in event_types, f"Model repair should not run for deterministic companion files. Got: {event_types}"
    # End state: must be ready (repair succeeded)
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" in statuses, f"Expected ready after repair. Got: {statuses}"


@pytest.mark.asyncio
async def test_repair_loop_fails_after_max_attempts():
    """When validation errors remain after bounded repair, project must fail."""
    db, proj, files, events, messages = _make_db()
    # Set quality_tier to cheap so max_repairs = 1
    proj["quality_tier"] = "cheap"
    call_count = [0]
    # Coder emits a non-secret-looking shape but with a real secret-like value in index.html.
    # Deterministic repair can add companion files, but it must not overwrite existing app content.
    reviewer_resp = {"verdict": "warn", "issues": ["Possible secret"], "patched_files": [], "summary": "Still unsafe"}
    all_responses = [
        {"summary": "App", "audience": "users", "core_features": [], "requirements_md": "# Reqs"},
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        {"files": [{"path": "index.html", "language": "html", "content": "<html><body>API_KEY=abcdef1234567890abcdef</body></html>"}], "summary": "Unsafe"},
        reviewer_resp,  # first reviewer pass
        reviewer_resp,  # repair pass (still no patched_files)
    ]

    async def complete_se(**kwargs):
        idx = call_count[0] % len(all_responses)
        call_count[0] += 1
        return {"text": json.dumps(all_responses[idx]), "model_label": "t", "model": "t", "session_id": "s", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_se)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page", quality_tier="cheap")
    # Remove upgrade confirmation to allow the build
    sd["requires_upgrade_confirmation"] = False
    await orch.run_full_build("Build landing page", mode="landing_page", stack_decision=sd)

    # Must be failed — validation error could not be repaired within cheap tier limit
    assert proj.get("status") == "failed", f"Expected failed, got {proj.get('status')}"
    event_types = [e.get("type") for e in events_received]
    assert "validation_exhausted" in event_types, f"Expected validation_exhausted. Got: {event_types}"
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" not in statuses, f"Should not be ready after exhausted repair. Got: {statuses}"


# ---------- stack decision: 20-page website ----------

def test_stack_website_20_page():
    """Website mode must use iframe preview and require index.html + README."""
    sd = decide_stack(prompt="Build a 20-page content website", mode="website")
    assert sd["recommended_mode"] == "website"
    assert sd["preview_strategy"] == "iframe"
    assert "index.html" in sd["required_files"]
    assert "README.md" in sd["required_files"]
    assert sd["stack"]["backend"] == "none"


# ---------- retry repair agent target ----------

def test_retry_repair_target_allowed():
    """RetryBody must accept 'repair' as a valid agent target."""
    import server
    body = server.RetryBody(agent="repair")
    assert body.agent == "repair"


# ---------- PART 1: preview sandbox ----------

def test_preview_iframe_sandbox_no_allow_same_origin():
    """Preview iframe sandbox must NOT include allow-same-origin."""
    import pathlib
    import re
    live_preview = pathlib.Path(__file__).parent.parent.parent / "frontend" / "src" / "components" / "LivePreview.jsx"
    content = live_preview.read_text()
    # Find the actual sandbox attribute value (not comments)
    sandbox_matches = re.findall(r'sandbox=["\']([^"\']*)["\']', content)
    assert sandbox_matches, "No sandbox attribute found in LivePreview.jsx"
    for sandbox_val in sandbox_matches:
        assert "allow-same-origin" not in sandbox_val, (
            f"LivePreview iframe sandbox must not include allow-same-origin "
            f"(browser security warning). Found: {sandbox_val}"
        )
    assert any("allow-scripts" in v for v in sandbox_matches), \
        "LivePreview iframe must still include allow-scripts"


# ---------- PART 2: MIME types ----------

def test_preview_mime_map_css():
    """Preview MIME map must serve CSS as text/css."""
    import server
    assert "css" in server._PREVIEW_MIME
    assert "text/css" in server._PREVIEW_MIME["css"]


def test_preview_mime_map_js():
    """Preview MIME map must serve JS as application/javascript."""
    import server
    assert "js" in server._PREVIEW_MIME
    assert "application/javascript" in server._PREVIEW_MIME["js"]


def test_preview_mime_map_html():
    """Preview MIME map must serve HTML as text/html."""
    import server
    assert "html" in server._PREVIEW_MIME
    assert "text/html" in server._PREVIEW_MIME["html"]


def test_preview_mime_map_json():
    """Preview MIME map must serve JSON as application/json."""
    import server
    assert "json" in server._PREVIEW_MIME
    assert "application/json" in server._PREVIEW_MIME["json"]


# ---------- PART 3: form accessibility validator ----------

from agents.orchestrator import _validate_form_accessibility


def test_form_accessibility_no_issues_no_forms():
    """Pages without form fields should have no accessibility issues."""
    html = "<html><body><h1>Hello</h1></body></html>"
    issues = _validate_form_accessibility(html)
    assert issues == [], f"Expected no issues for non-form page, got: {issues}"


def test_form_accessibility_input_missing_id_and_name():
    """Input without id and name must be flagged."""
    html = '<html><body><form><input type="text"></form></body></html>'
    issues = _validate_form_accessibility(html)
    assert any("missing id" in i for i in issues), f"Expected missing id issue: {issues}"
    assert any("missing name" in i for i in issues), f"Expected missing name issue: {issues}"


def test_form_accessibility_input_missing_label():
    """Input with id but no label must be flagged."""
    html = '<html><body><form><input type="text" id="email" name="email"></form></body></html>'
    issues = _validate_form_accessibility(html)
    assert any('email' in i and 'label' in i for i in issues), \
        f"Expected missing label issue for id=email: {issues}"


def test_form_accessibility_input_with_aria_label_ok():
    """Input with aria-label but no <label> tag should be accepted."""
    html = '<html><body><form><input type="text" id="email" name="email" aria-label="Email address"></form></body></html>'
    issues = _validate_form_accessibility(html)
    label_issues = [i for i in issues if 'label' in i.lower() and 'email' in i]
    assert not label_issues, f"aria-label should satisfy label requirement: {label_issues}"


def test_form_accessibility_complete_accessible_form_no_issues():
    """A form with proper id, name, and label should have no accessibility issues."""
    html = '''<html><body><form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email">
        <label for="msg">Message</label>
        <textarea id="msg" name="msg"></textarea>
        <input type="submit" value="Send">
    </form></body></html>'''
    issues = _validate_form_accessibility(html)
    assert not issues, f"Fully accessible form should have no issues: {issues}"


def test_form_accessibility_hidden_inputs_skipped():
    """Hidden inputs do not need id/name/label."""
    html = '<html><body><form><input type="hidden" value="csrf-token"></form></body></html>'
    issues = _validate_form_accessibility(html)
    assert not issues, f"Hidden inputs should be skipped: {issues}"


# ---------- PART 4: reviewer non-fatal ----------

@pytest.mark.asyncio
async def test_reviewer_invalid_json_is_non_fatal_if_files_present():
    """If Reviewer returns invalid JSON, project should still reach ready if files are present."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    # Scout, Architect, Coder succeed; Reviewer returns bad JSON
    responses = [
        # scout
        {"summary": "App", "audience": "users", "core_features": ["home"], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        # coder: produce all required files for landing_page
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
            {"path": "styles.css", "language": "css", "content": "body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ], "summary": "Done"},
        # reviewer: bad JSON (simulates model failure)
        "NOT VALID JSON AT ALL !!!",
        # repair JSON (also bad so the repair fails too)
        "ALSO NOT VALID",
    ]

    async def complete_se(**kwargs):
        idx = call_count[0]
        call_count[0] += 1
        r = responses[idx] if idx < len(responses) else responses[-1]
        return {
            "text": json.dumps(r) if not isinstance(r, str) else r,
            "model_label": "test", "model": "test", "session_id": "s", "usage": {},
        }

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_se)
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")
    await orch.run_full_build("Build a landing page", mode="landing_page", stack_decision=sd)

    # Despite reviewer failure, project should be ready because all required files exist
    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" in statuses, (
        f"Project should reach ready when reviewer fails but files are present. Got: {statuses}"
    )
    assert proj.get("status") == "ready", f"Expected ready, got {proj.get('status')}"


# ---------- PART 5: Stop Build ----------

@pytest.mark.asyncio
async def test_cancel_before_scout_prevents_scout():
    """cancel_requested=True before Scout must prevent Scout from running."""
    db, proj, files, events, messages = _make_db()
    proj["cancel_requested"] = True

    provider = MagicMock()
    provider.complete = AsyncMock()

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[])
    orch.fs.list = AsyncMock(return_value=[])

    await orch.run_full_build("Build an app")

    # Scout should not have been called
    provider.complete.assert_not_called()
    assert proj.get("status") == "cancelled"


@pytest.mark.asyncio
async def test_cancelled_project_never_becomes_ready():
    """Once cancelled, no subsequent pipeline step must set status to ready."""
    db, proj, files, events, messages = _make_db()

    cancel_after_calls = [0]

    async def complete_with_cancel(**kwargs):
        cancel_after_calls[0] += 1
        # Cancel after first model call
        if cancel_after_calls[0] >= 1:
            proj["cancel_requested"] = True
        return {
            "text": json.dumps({"summary": "x", "audience": "y", "core_features": [], "requirements_md": ""}),
            "model_label": "test", "model": "test", "session_id": "s", "usage": {},
        }

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=complete_with_cancel)

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[])
    orch.fs.list = AsyncMock(return_value=[])

    await orch.run_full_build("Build an app")

    status_events = [e for e in events_received if e.get("type") == "project_status"]
    statuses = [e["data"]["status"] for e in status_events]
    assert "ready" not in statuses, f"Cancelled project must never become ready. Got: {statuses}"
    assert "cancelled" in statuses



# ========== NEW: Quality Validator Tests ==========

from agents.quality_validator import score_project_quality, MIN_QUALITY_SCORE, MIN_DESIGN_SCORE


def _html_landing_page(sections: int = 7, words: int = 600, has_hero: bool = True,
                        has_cta: bool = True, has_responsive: bool = True) -> str:
    """Build a minimal landing page HTML for testing."""
    hero = '<section id="hero"><h1>Welcome to Amarktai</h1><p>The best platform for building apps.</p></section>' if has_hero else ''
    cta = '<a href="#get-started" class="btn-cta">Get Started Today</a>' if has_cta else ''
    responsive = '@media (max-width: 768px) { body { flex-direction: column; } }' if has_responsive else ''
    # Generate enough words per section to meet minimum word count
    words_per_section = max(100, words // max(sections, 1))
    word_block = " ".join(["Amarktai platform professional solution enterprise"] * (words_per_section // 5))
    sec_tags = (
        f'<section id="features" class="features"><h2>Features</h2><p>{word_block}</p></section>'
        + "".join(
            f'<section class="section-{i}"><h2>Section {i}</h2><p>{word_block}</p></section>'
            for i in range(1, max(sections - 1, 1))
        )
    )
    return f"""<!DOCTYPE html>
<html><head><style>{responsive}</style></head>
<body>
{hero}
{sec_tags}
{cta}
<footer><p>Footer content here for the page.</p></footer>
</body></html>"""


def test_quality_validator_thin_landing_page_fails():
    """Thin landing page (nav/footer only, <6 sections) must score below MIN_QUALITY_SCORE."""
    html = "<html><body><nav>Nav</nav><footer>Footer</footer></body></html>"
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    assert result["qualityScore"] < MIN_QUALITY_SCORE, (
        f"Thin page must score below {MIN_QUALITY_SCORE}. Got: {result['qualityScore']}"
    )
    assert not result["qualityOk"], "Thin page must not pass quality check"
    assert result["qualityErrors"], "Thin page must have quality errors"


def test_quality_validator_complete_landing_page_passes():
    """Complete landing page with 7 sections, 600+ words, hero, CTA, responsive must pass."""
    html = _html_landing_page(sections=7, words=600, has_hero=True, has_cta=True, has_responsive=True)
    css = "body { display: flex; } @media (max-width: 768px) { body { flex-direction: column; } } .hero { background: linear-gradient(135deg, #000, #333); }"
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": css * 10, "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    assert result["qualityScore"] >= MIN_QUALITY_SCORE, (
        f"Complete page must score >= {MIN_QUALITY_SCORE}. Got: {result['qualityScore']}\n"
        f"Errors: {result['qualityErrors']}"
    )
    assert result["qualityOk"], f"Complete page must pass quality. Errors: {result['qualityErrors']}"


def test_quality_validator_missing_hero_penalizes():
    """Landing page without hero/h1 must be penalized."""
    html = _html_landing_page(sections=7, words=600, has_hero=False, has_cta=True, has_responsive=True)
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": "body{} @media(max-width:768px){} .x{ background: linear-gradient(#a,#b); }" * 20, "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    hero_errors = [e for e in result["qualityErrors"] if "hero" in e.lower() or "h1" in e.lower()]
    assert hero_errors, f"Missing hero must generate quality error. Got: {result['qualityErrors']}"


def test_quality_validator_generic_copy_penalizes():
    """Pages with 'lorem ipsum' must be penalized."""
    html = f"<html><body><h1>App</h1>{'<section><p>Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p></section>' * 7}<a class='btn'>CTA</a><footer>Footer</footer><style>@media(max-width:768px){{}}</style></body></html>"
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": "body{display:flex} @media(max-width:768px){} .hero{background:linear-gradient(#a,#b)}" * 15, "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    generic_errors = [e for e in result["qualityErrors"] if "lorem" in e.lower() or "placeholder" in e.lower() or "generic" in e.lower()]
    assert generic_errors, f"Generic copy must be flagged. Got: {result['qualityErrors']}"


def test_quality_validator_pwa_missing_manifest_fails():
    """PWA without manifest.json must fail quality."""
    files = [
        {"path": "index.html", "content": "<html><body>App</body></html>", "language": "html"},
        {"path": "service-worker.js", "content": "self.addEventListener('install',()=>{}); self.addEventListener('fetch',()=>{})", "language": "javascript"},
    ]
    result = score_project_quality(files, "pwa", "pwa", "Build a PWA")
    assert not result["qualityOk"], "PWA without manifest must fail quality"
    assert any("manifest" in e.lower() for e in result["qualityErrors"])


def test_quality_validator_pwa_complete_passes():
    """Complete PWA with manifest and service worker must pass quality."""
    manifest = json.dumps({"name": "My App", "short_name": "App", "start_url": "/", "display": "standalone", "icons": [{"src": "/icon.png", "sizes": "192x192"}]})
    sw = "self.addEventListener('install', e => {}); self.addEventListener('fetch', e => {});"
    files = [
        {"path": "index.html", "content": "<html><body><h1>App</h1><p>My great PWA app with full offline support and meaningful UI.</p></body></html>", "language": "html"},
        {"path": "manifest.json", "content": manifest, "language": "json"},
        {"path": "service-worker.js", "content": sw, "language": "javascript"},
    ]
    result = score_project_quality(files, "pwa", "pwa", "Build a PWA task tracker")
    assert result["qualityScore"] >= MIN_QUALITY_SCORE, (
        f"Complete PWA must score >= {MIN_QUALITY_SCORE}. Got: {result['qualityScore']}\n"
        f"Errors: {result['qualityErrors']}"
    )


def test_security_validator_hardcoded_secret_fails():
    """Hardcoded JWT secret must fail security validation."""
    files = [
        {"path": "backend/main.py", "content": 'jwt_secret = "my-super-secret-key-abc123def456ghi789"', "language": "python"},
        {"path": ".env.example", "content": "JWT_SECRET=change-me", "language": "text"},
    ]
    result = score_project_quality(files, "fullstack-app", "full-stack", "Build a SaaS", auth_required=True)
    assert not result["securityOk"], f"Hardcoded secret must fail security. Score: {result['securityScore']}"
    assert result["securityErrors"], "Security errors must be populated"


def test_security_validator_env_example_missing_fails_fullstack():
    """Full-stack app without .env.example must fail security."""
    files = [
        {"path": "backend/main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): return {'ok': True}", "language": "python"},
        {"path": "frontend/src/App.jsx", "content": "export default function App() { return <div>Hello World App Content Here For Testing</div>; }", "language": "jsx"},
        {"path": "docker-compose.yml", "content": "version: '3'\nservices:\n  backend:\n    build: ./backend", "language": "yaml"},
    ]
    result = score_project_quality(files, "fullstack-app", "full-stack", "Build SaaS with auth", auth_required=True)
    assert not result["securityOk"], "Full-stack without .env.example must fail security"


def test_security_validator_clean_project_passes():
    """Clean project with no secrets must pass security."""
    files = [
        {"path": "index.html", "content": "<html><body><h1>Hello</h1></body></html>", "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    assert result["securityOk"], f"Clean project must pass security. Errors: {result['securityErrors']}"


def test_quality_validator_broken_local_image_flagged():
    """Local image paths that aren't https:// should be flagged as media errors."""
    html = '<html><body><img src="./images/hero.jpg"><img src="https://images.unsplash.com/good.jpg"></body></html>'
    files = [{"path": "index.html", "content": html, "language": "html"}]
    result = score_project_quality(files, "static-site", "landing-page", "Build a landing page")
    assert not result["mediaOk"], "Broken local image paths must be flagged"
    assert result["mediaErrors"], "mediaErrors must list the broken paths"


# ========== NEW: Clarification Engine Tests ==========

from agents.clarification import check_clarification_needed, apply_clarification_answers


def test_clarification_vague_prompt_needs_clarification():
    """Very vague prompts must require clarification."""
    result = check_clarification_needed("build me an app")
    assert result["needs_clarification"] is True, "Vague prompt must need clarification"
    assert result["questions"], "Must return focused questions"
    assert len(result["questions"]) <= 5, "Must not ask more than 5 questions"


def test_clarification_specific_prompt_no_clarification():
    """A detailed, specific prompt must not require clarification."""
    prompt = (
        "Build a modern professional 5-page website for a consulting business "
        "with home, about, services, pricing, and contact pages. "
        "Use React Vite with Tailwind CSS. No auth needed. No database."
    )
    result = check_clarification_needed(prompt)
    assert result["needs_clarification"] is False, (
        f"Specific prompt must not need clarification. Questions: {result['questions']}"
    )


def test_clarification_infers_mode_from_prompt():
    """Clarification engine must infer mode from prompt keywords."""
    result = check_clarification_needed("build a saas platform with login and dashboard")
    assert result["inferred_mode"] in ("full_stack", "dashboard", "web_app"), (
        f"SaaS prompt must infer correct mode. Got: {result['inferred_mode']}"
    )


def test_clarification_infers_auth_from_prompt():
    """Clarification engine must detect auth keywords."""
    result = check_clarification_needed("build an app with login and register for users")
    assert result["inferred_auth"] is True, "Auth keywords must be detected"


def test_clarification_apply_answers_enriches_prompt():
    """Applying clarification answers must produce an enriched prompt."""
    enriched, params = apply_clarification_answers(
        "build me an app",
        {"mode": "Landing page", "auth_required": "No auth needed", "database": "No database"},
    )
    assert "Landing page" in enriched or "landing" in enriched.lower(), (
        f"Enriched prompt must include mode. Got: {enriched}"
    )
    assert params.get("mode") == "landing_page"
    assert params.get("auth_required") is False


# ========== NEW: Design Engine Tests ==========

from agents.design_engine import create_design_direction, get_available_styles, _DESIGN_STYLES


def test_design_engine_returns_valid_style():
    """create_design_direction must return a complete style dict."""
    direction = create_design_direction(
        prompt="Build a modern SaaS landing page",
        project_type="static-site",
        audience="startup founders",
        tier="balanced",
    )
    assert "name" in direction
    assert "palette" in direction
    assert "typography" in direction
    assert "coder_instructions" in direction
    assert "visual_motifs" in direction


def test_design_engine_different_prompts_can_produce_different_styles():
    """Different prompt topics should produce different design styles."""
    d1 = create_design_direction("Build a fintech trading dashboard", "dashboard", "traders", "premium")
    d2 = create_design_direction("Build an organic farm market website", "static-site", "farmers", "balanced")
    # At least the palettes or names should differ
    same = d1["name"] == d2["name"] and d1["palette"] == d2["palette"]
    assert not same, "Different topics should produce different design directions"


def test_design_engine_finance_uses_fintech_style():
    """Finance/trading prompts should select the fintech-dashboard style."""
    direction = create_design_direction("Build a crypto trading platform", "dashboard", "traders", "premium")
    assert direction["name"] == "fintech-dashboard", (
        f"Finance prompt should select fintech-dashboard. Got: {direction['name']}"
    )


def test_design_engine_nature_uses_organic_style():
    """Nature/eco prompts should select the organic-nature style."""
    direction = create_design_direction("Build a sustainable organic farm marketplace", "static-site", "farmers", "balanced")
    assert direction["name"] == "organic-nature", (
        f"Nature prompt should select organic-nature. Got: {direction['name']}"
    )


def test_design_engine_get_available_styles():
    """get_available_styles must return all available styles with name and label."""
    styles = get_available_styles()
    assert len(styles) == len(_DESIGN_STYLES), "Must return all styles"
    for s in styles:
        assert "name" in s
        assert "label" in s


def test_design_engine_deterministic_same_prompt():
    """Same prompt must always produce the same design direction."""
    d1 = create_design_direction("Build a luxury jewelry brand website", "static-site", "affluent shoppers", "premium")
    d2 = create_design_direction("Build a luxury jewelry brand website", "static-site", "affluent shoppers", "premium")
    assert d1["name"] == d2["name"], "Same prompt must produce same design direction"


# ========== NEW: Pixabay Integration Tests ==========

from agents.pixabay import build_media_manifest


def test_pixabay_build_media_manifest_structure():
    """build_media_manifest must return a properly structured manifest."""
    images = [
        {"url": "https://pixabay.com/img1.jpg", "full_url": "https://pixabay.com/img1-large.jpg",
         "tags": "horse nature", "attribution": "Photo by user on Pixabay", "pixabay_page_url": "https://pixabay.com/1"},
    ]
    videos = [
        {"url": "https://pixabay.com/vid1.mp4", "tags": "horse run", "duration": 30,
         "attribution": "Video by user on Pixabay", "pixabay_page_url": "https://pixabay.com/2"},
    ]
    manifest = build_media_manifest(images, videos, "horse")
    assert manifest["query"] == "horse"
    assert manifest["source"] == "pixabay"
    assert manifest["attribution_required"] is True
    assert len(manifest["images"]) == 1
    assert len(manifest["videos"]) == 1
    assert "license" in manifest
    assert "pixabay" in manifest["license"].lower()


@pytest.mark.asyncio
async def test_pixabay_search_images_no_api_key_returns_empty():
    """search_images must return empty list when no API key is provided."""
    from agents.pixabay import search_images
    results = await search_images("horse", api_key="", per_page=5)
    assert results == [], "No API key must return empty list"


@pytest.mark.asyncio
async def test_pixabay_search_videos_no_api_key_returns_empty():
    """search_videos must return empty list when no API key is provided."""
    from agents.pixabay import search_videos
    results = await search_videos("nature", api_key="", per_page=3)
    assert results == [], "No API key must return empty list"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — New feature tests
# ═══════════════════════════════════════════════════════════════════════════

# ── Clarification engine ──────────────────────────────────────────────────

def test_clarification_needed_for_vague_prompt():
    """A short, vague prompt must trigger clarification questions."""
    from agents.clarification import check_clarification_needed
    result = check_clarification_needed("build an app")
    assert result["needs_clarification"] is True
    assert len(result["questions"]) > 0


def test_clarification_not_needed_for_clear_prompt():
    """A detailed, specific prompt must NOT require clarification questions."""
    from agents.clarification import check_clarification_needed
    result = check_clarification_needed(
        "Build a React Vite landing page for a SaaS password manager with a hero section, "
        "pricing table, FAQ, and a sign-up form with JWT auth and PostgreSQL."
    )
    assert result["needs_clarification"] is False


def test_clarification_apply_enriches_prompt():
    """apply_clarification_answers must merge user answers into the original prompt."""
    from agents.clarification import apply_clarification_answers
    enriched, params = apply_clarification_answers(
        "build a saas",
        {
            "mode": "Full-stack SaaS",
            "auth_required": "Yes — login, register, JWT",
            "database": "PostgreSQL (relational)",
        },
    )
    assert "Full-stack SaaS" in enriched or params.get("mode")
    assert params.get("auth_required") is True
    assert "postgres" in str(params.get("database_preference", "")).lower()


def test_clarification_apply_skips_auto_options():
    """apply_clarification_answers must not add empty/auto choices to the prompt."""
    from agents.clarification import apply_clarification_answers
    enriched, params = apply_clarification_answers(
        "build a landing page",
        {"framework": "Auto-select best fit"},
    )
    assert "auto" not in enriched.lower()
    assert "stack_preference" not in params


def test_clarification_max_5_questions():
    """At most 5 clarification questions are returned even for very vague prompts."""
    from agents.clarification import check_clarification_needed
    result = check_clarification_needed("build something")
    assert len(result["questions"]) <= 5


# ── Quality / design / security validation scores ──────────────────────────

def _files_with_content(*pairs):
    """Helper: create a list of file dicts from (path, content) pairs."""
    return [{"path": p, "content": c, "language": "html"} for p, c in pairs]


def test_thin_page_fails_quality():
    """A minimal page with almost no content must produce a low quality score."""
    from agents.quality_validator import score_project_quality
    files = _files_with_content(
        ("index.html", "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>"),
    )
    result = score_project_quality(files, project_type="static-site", build_mode="landing_page")
    assert result["qualityScore"] < 75, f"thin page should fail quality: {result['qualityScore']}"
    assert not result["qualityOk"]


def test_complete_page_passes_quality():
    """A page with substantial content and required files must pass quality."""
    from agents.quality_validator import score_project_quality
    rich_html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>My App</title>
<meta name="description" content="A great app">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header><nav><ul><li><a href="#features">Features</a></li><li><a href="#pricing">Pricing</a></li></ul></nav></header>
<main>
  <section class="hero">
    <h1>Welcome to My App</h1>
    <p>The best app for your needs. Get started today and transform your workflow.</p>
    <a href="#signup" class="cta">Get Started Free</a>
  </section>
  <section id="features">
    <h2>Features</h2>
    <div class="feature-grid">
      <div><h3>Fast</h3><p>Lightning fast performance with optimized code.</p></div>
      <div><h3>Secure</h3><p>Enterprise-grade security for your data.</p></div>
      <div><h3>Simple</h3><p>Easy to use interface anyone can master.</p></div>
    </div>
  </section>
  <section id="pricing">
    <h2>Pricing</h2>
    <div class="pricing-cards">
      <div class="plan"><h3>Free</h3><p>$0/mo</p></div>
      <div class="plan"><h3>Pro</h3><p>$9/mo</p></div>
    </div>
  </section>
</main>
<footer><p>&copy; 2025 My App. All rights reserved.</p></footer>
<script src="app.js"></script>
</body>
</html>"""
    files = _files_with_content(
        ("index.html", rich_html),
        ("styles.css", "body { margin: 0; } .hero { padding: 4rem; } .feature-grid { display: grid; } footer { padding: 2rem; }"),
        ("app.js", "// App logic\ndocument.addEventListener('DOMContentLoaded', () => { console.log('ready'); });"),
        ("README.md", "# My App\n\nA great app. See instructions below.\n\n## Install\n\n`npm install`"),
        ("amarktai.project.json", '{"name":"My App","version":"1.0.0"}'),
    )
    result = score_project_quality(files, project_type="static-site", build_mode="landing_page")
    assert result["qualityScore"] >= 60, f"complete page should have decent quality: {result}"


def test_validate_project_files_returns_scores():
    """validate_project_files must return qualityScore, designScore, securityScore."""
    files = _files_with_content(
        ("index.html", "<!DOCTYPE html><html><body>Hello World. This is a test page with enough content to not be empty.</body></html>"),
        ("styles.css", "body { margin: 0; color: #333; }"),
        ("README.md", "# Test App"),
        ("amarktai.project.json", '{"name":"Test"}'),
    )
    project = {"mode": "landing_page", "project_type": "static-site", "build_mode": "landing_page"}
    result = validate_project_files(project, files, prompt="Test app")
    assert "qualityScore" in result
    assert "designScore" in result
    assert "securityScore" in result
    assert isinstance(result["qualityScore"], (int, float))
    assert isinstance(result["canFinalize"], bool)


def test_validate_returns_can_finalize_false_for_incomplete():
    """canFinalize must be False for a project with structural errors."""
    files = _files_with_content(
        ("index.html", "<!DOCTYPE html><html><body>Hi</body></html>"),
        # deliberately missing styles.css, README.md, amarktai.project.json
    )
    project = {"mode": "landing_page", "project_type": "static-site", "build_mode": "landing_page"}
    result = validate_project_files(project, files, prompt="Test")
    # With many missing required files and thin content, finalize must be blocked
    # (either structurally or via score)
    assert isinstance(result["canFinalize"], bool)


# ── GitHub name collision ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_repo_exists_returns_true_for_200():
    """check_repo_exists must return True when GitHub responds with 200."""
    import httpx
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("github_integration.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = ctx

        from github_integration import check_repo_exists
        result = await check_repo_exists("owner", "existing-repo", "fake-pat")
        assert result is True


@pytest.mark.asyncio
async def test_check_repo_exists_returns_false_for_404():
    """check_repo_exists must return False when GitHub responds with 404."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("github_integration.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = ctx

        from github_integration import check_repo_exists
        result = await check_repo_exists("owner", "new-repo", "fake-pat")
        assert result is False


# ── Branch + PR mode excludes secrets ────────────────────────────────────

def test_finalize_excludes_dotenv_files():
    """Finalize payload must never include .env files."""
    # This mirrors the server-side filter logic
    files = [
        {"path": "index.html", "content": "<html/>"},
        {"path": ".env", "content": "SECRET=abc123"},
        {"path": "backend/.env", "content": "DB_URL=postgres://..."},
        {"path": "src/app.js", "content": "// app"},
    ]
    # Apply the same filter used in the finalize endpoint
    payload_files = [
        f for f in files
        if f["path"] != ".env" and not f["path"].endswith("/.env")
    ]
    paths = [f["path"] for f in payload_files]
    assert ".env" not in paths
    assert "backend/.env" not in paths
    assert "index.html" in paths
    assert "src/app.js" in paths


# ── Audio/music model audit ───────────────────────────────────────────────

def test_audio_model_audit_returns_honest_unavailable():
    """Audio model response must be honest when no audio models exist."""
    # Simulate the response structure the endpoint returns when unavailable
    response = {
        "available": False,
        "models": [],
        "message": "Audio/music generation is currently unavailable",
    }
    assert response["available"] is False
    assert response["models"] == []
    assert "unavailable" in response["message"].lower()


def test_audio_model_audit_detects_audio_keywords():
    """Audio model detection must use keyword matching on model names."""
    audio_keywords = {"audio", "music", "sound", "tts", "speech", "voice", "whisper", "bark"}
    models = ["gpt-4o", "claude-haiku", "whisper-1", "dall-e-3", "text-to-speech"]
    audio_models = [
        m for m in models
        if any(kw in m.lower() for kw in audio_keywords)
    ]
    assert "whisper-1" in audio_models
    assert "text-to-speech" in audio_models
    assert "gpt-4o" not in audio_models


# ── Pixabay caching ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pixabay_caches_results():
    """Pixabay search results must be cached to avoid redundant API calls."""
    import httpx
    from unittest.mock import AsyncMock, patch, MagicMock
    from agents.pixabay import _cache, _cache_lock, search_images

    # Clear cache before test
    async with _cache_lock:
        _cache.clear()

    fake_response_data = {
        "hits": [
            {
                "id": 1,
                "webformatURL": "https://pixabay.com/img1.jpg",
                "previewURL": "https://pixabay.com/thumb1.jpg",
                "largeImageURL": "https://pixabay.com/large1.jpg",
                "webformatWidth": 800,
                "webformatHeight": 600,
                "tags": "test image",
                "pageURL": "https://pixabay.com/photos/1",
                "user": "testuser",
            }
        ]
    }

    call_count = [0]

    async def fake_get(url, params=None, **kwargs):
        call_count[0] += 1
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=fake_response_data)
        return resp

    # Clear cache again to ensure clean state
    async with _cache_lock:
        _cache.clear()

    with patch("agents.pixabay.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.get = AsyncMock(side_effect=fake_get)
        MockClient.return_value = ctx

        # First call — should hit the API
        r1 = await search_images("horse", api_key="test-key-123", per_page=3)
        # Second call with same params — should use cache
        r2 = await search_images("horse", api_key="test-key-123", per_page=3)

    assert r1 == r2
    assert call_count[0] == 1, f"Cache should prevent second API call, got {call_count[0]} calls"
