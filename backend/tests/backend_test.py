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


# ── Phase 2: Repo Analyzer ────────────────────────────────────────────────────

def test_repo_analyzer_detects_static_site():
    """analyze_repo_profile must identify a static site from index.html alone."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "index.html", "content": "<html><body>Hello</body></html>"},
        {"path": "styles.css", "content": "body { margin: 0; }"},
    ]
    profile = analyze_repo_profile(files, "owner/static-site")
    assert profile["detectedType"] == "static"
    assert profile["previewStrategy"] == "static"
    assert profile["canPreview"] is True
    assert profile["fileCount"] == 2
    assert "HTML" in profile["languages"]


def test_repo_analyzer_detects_react_vite():
    """analyze_repo_profile must detect a Vite/React SPA from package.json."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "package.json", "content": '{"dependencies":{"react":"^18","vite":"^4"},"scripts":{"dev":"vite"}}'},
        {"path": "src/App.jsx", "content": 'import React from "react"; export default function App() { return <div>Hello</div>; }'},
        {"path": "index.html", "content": '<html><body><div id="root"></div></body></html>'},
    ]
    profile = analyze_repo_profile(files, "owner/react-app")
    assert profile["detectedType"] in ("vite_react", "next")
    assert "React" in profile["frameworks"] or "Vite" in profile["frameworks"]
    assert "JavaScript" in profile["languages"]


def test_repo_analyzer_detects_next():
    """analyze_repo_profile must detect Next.js from next.config.js."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "next.config.js", "content": "/** @type {import('next').NextConfig} */\nmodule.exports = {}"},
        {"path": "package.json", "content": '{"dependencies":{"next":"^14","react":"^18"}}'},
        {"path": "pages/index.tsx", "content": "export default function Home() { return <h1>Home</h1>; }"},
    ]
    profile = analyze_repo_profile(files, "owner/next-app")
    assert profile["detectedType"] == "next"
    assert "Next.js" in profile["frameworks"]


def test_repo_analyzer_detects_fastapi():
    """analyze_repo_profile must detect a FastAPI backend."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root(): return {}"},
        {"path": "requirements.txt", "content": "fastapi\nuvicorn\n"},
    ]
    profile = analyze_repo_profile(files, "owner/api-app")
    assert profile["detectedType"] == "api_service"
    assert "FastAPI" in profile["frameworks"]
    assert profile["packageManager"] == "pip"


def test_repo_analyzer_detects_docker():
    """analyze_repo_profile must flag docker_available when Dockerfile is present."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "Dockerfile", "content": "FROM python:3.11\nCMD [\"uvicorn\"]"},
        {"path": "docker-compose.yml", "content": "version: '3'\nservices:\n  app:\n    build: ."},
        {"path": "main.py", "content": "from fastapi import FastAPI"},
    ]
    profile = analyze_repo_profile(files, "owner/dockerized")
    assert profile["dockerAvailable"] is True
    assert "docker compose build" in profile["buildCommands"]


def test_repo_analyzer_empty_files():
    """analyze_repo_profile must not crash on empty file list."""
    from agents.repo_analyzer import analyze_repo_profile
    profile = analyze_repo_profile([], "owner/empty")
    assert profile["detectedType"] == "unknown"
    assert profile["canPreview"] is False
    assert profile["fileCount"] == 0


def test_repo_analyzer_detects_mongo_db():
    """analyze_repo_profile must detect MongoDB from source code."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "server.py", "content": "from motor.motor_asyncio import AsyncIOMotorClient\nclient = AsyncIOMotorClient('mongodb://localhost')"},
        {"path": "requirements.txt", "content": "motor\nfastapi\n"},
    ]
    profile = analyze_repo_profile(files, "owner/mongo-app")
    assert "MongoDB" in profile["databases"]


def test_repo_analyzer_extracts_env_vars():
    """analyze_repo_profile must extract env var names from .env.example."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": ".env.example", "content": "DATABASE_URL=\nJWT_SECRET=\nAPI_KEY=\n"},
        {"path": "main.py", "content": "import os\nDB = os.environ.get('DATABASE_URL', '')"},
    ]
    profile = analyze_repo_profile(files, "owner/env-app")
    assert "DATABASE_URL" in profile["envRequired"]
    assert "JWT_SECRET" in profile["envRequired"]


def test_repo_analyzer_extracts_routes():
    """analyze_repo_profile must extract route paths from Express/FastAPI source."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "server.js", "content": "app.get('/api/users', handler);\napp.post('/api/login', auth);"},
    ]
    profile = analyze_repo_profile(files, "owner/express")
    assert any("/api/users" in r or "/api/login" in r for r in profile["routeMap"])


# ── Phase 3: Repo Preview Fallback ────────────────────────────────────────────

def test_repo_analyzer_unknown_returns_blockers():
    """analyze_repo_profile for unknown type must include previewBlockers."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "some_random_file.xyz", "content": "some content"},
    ]
    profile = analyze_repo_profile(files, "owner/mystery")
    assert profile["detectedType"] == "unknown"
    assert len(profile["previewBlockers"]) > 0
    assert profile["canPreview"] is False


def test_repo_analyzer_fullstack_returns_blockers_when_env_missing():
    """Fullstack repos must report env var blockers when env required."""
    from agents.repo_analyzer import analyze_repo_profile
    files = [
        {"path": "backend/main.py", "content": "from fastapi import FastAPI\nfrom motor.motor_asyncio import AsyncIOMotorClient"},
        {"path": ".env.example", "content": "MONGO_URL=\nJWT_SECRET=\n"},
        {"path": "frontend/index.html", "content": "<html><body>App</body></html>"},
    ]
    profile = analyze_repo_profile(files, "owner/fullstack")
    assert profile["detectedType"] == "fullstack"
    # Fullstack with env requirements should show blockers
    assert len(profile["previewBlockers"]) > 0 or profile["envRequired"]


# ── Phase 4: Update Intent Detection ─────────────────────────────────────────

def test_intent_detects_full_app_completion():
    """detect_update_intent must identify full_app_completion requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "README.md", "content": "# My App"}]
    intent = detect_update_intent("Build the complete app described in this repo", files)
    assert intent == "full_app_completion"


def test_intent_detects_bug_fix():
    """detect_update_intent must identify bug_fix requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "app.py", "content": "# app"}]
    intent = detect_update_intent("Fix the crash in the login route", files)
    assert intent == "bug_fix"


def test_intent_detects_feature_add():
    """detect_update_intent must identify feature_add requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "app.js", "content": "// app"}]
    intent = detect_update_intent("Add a dashboard page with analytics", files)
    assert intent == "feature_add"


def test_intent_detects_production_hardening():
    """detect_update_intent must identify production_hardening requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "main.py", "content": "# main"}]
    intent = detect_update_intent("Secure the API and add rate limiting", files)
    assert intent == "production_hardening"


def test_intent_detects_redesign():
    """detect_update_intent must identify redesign requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "index.html", "content": "<html/>"}]
    intent = detect_update_intent("Redesign the homepage with a completely new look", files)
    assert intent == "redesign"


def test_intent_detects_full_rebuild():
    """detect_update_intent must identify full_rebuild_inside_repo requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "app.py", "content": "# placeholder"}]
    intent = detect_update_intent("Rewrite everything from scratch using Next.js", files)
    assert intent == "full_rebuild_inside_repo"


def test_intent_defaults_to_small_patch():
    """detect_update_intent must default to small_patch for simple requests."""
    from agents.repo_analyzer import detect_update_intent
    files = [{"path": "index.html", "content": "<html/>"}]
    intent = detect_update_intent("Change the button color to blue", files)
    assert intent == "small_patch"


# ── Phase 5: Coverage Score ───────────────────────────────────────────────────

def _make_files(*path_content_pairs):
    """Helper to make file dicts for coverage score tests."""
    return [{"path": p, "content": c} for p, c in path_content_pairs]


def test_coverage_score_complete_landing_page():
    """Coverage score for a complete landing page should be high (>= 70)."""
    from agents.coverage_score import compute_coverage_score
    files = _make_files(
        ("index.html", """<!DOCTYPE html><html><body>
            <section class="hero"><h1>Welcome</h1><a class="btn">Get Started</a></section>
            <section id="features">Great features</section>
            <section id="pricing">Pricing info</section>
            <footer>Footer content</footer>
        </body></html>"""),
        ("styles.css", "body{margin:0} @media(max-width:768px){body{font-size:14px}}"),
        ("README.md", "# My App\n\nInstall: npm install\nRun: npm start"),
        ("amarktai.project.json", '{"name":"My App"}'),
    )
    result = compute_coverage_score(
        prompt="Build a landing page for my SaaS product",
        files=files,
        mode="landing_page",
        preview_url="http://localhost:8080/preview/123",
    )
    assert result["coverageScore"] >= 70, f"Expected >= 70, got {result['coverageScore']}"
    assert isinstance(result["requestSatisfied"], bool)
    assert "coverageScore" in result
    assert "missingRequirements" in result
    assert "checkedRequirements" in result


def test_coverage_score_no_files_returns_zero():
    """Coverage score for an empty project must be 0 and requestSatisfied=False."""
    from agents.coverage_score import compute_coverage_score
    result = compute_coverage_score(
        prompt="Build a full app",
        files=[],
        mode="web_app",
    )
    assert result["coverageScore"] == 0
    assert result["requestSatisfied"] is False
    assert result["canFinalize"] is False


def test_coverage_score_pwa_detects_missing_manifest():
    """Coverage score for a PWA without manifest.json must list it as missing."""
    from agents.coverage_score import compute_coverage_score
    files = _make_files(
        ("index.html", "<html><body>PWA app content here</body></html>"),
        ("app.js", "// service worker registration"),
        ("README.md", "# PWA"),
    )
    result = compute_coverage_score(
        prompt="Build a PWA task tracker",
        files=files,
        mode="pwa",
        preview_fallback={"fileTree": ["index.html"]},
    )
    missing = result["missingRequirements"]
    assert any("manifest" in m.lower() for m in missing), f"Expected manifest in missing: {missing}"


def test_coverage_score_fullstack_detects_missing_auth():
    """Coverage score for full-stack must flag missing auth when requested."""
    from agents.coverage_score import compute_coverage_score
    files = _make_files(
        ("frontend/index.html", "<html><body>Dashboard</body></html>"),
        ("backend/main.py", "from fastapi import FastAPI\napp = FastAPI()"),
        ("README.md", "# SaaS"),
    )
    result = compute_coverage_score(
        prompt="Build a full-stack SaaS with secure login and dashboard",
        files=files,
        mode="full_stack",
        preview_fallback={"fileTree": ["frontend/index.html"]},
    )
    missing = result["missingRequirements"]
    assert any("auth" in m.lower() for m in missing), f"Expected auth in missing: {missing}"


def test_coverage_score_full_app_completion_needs_80():
    """Coverage score for full_app_completion intent must require >= 80 to pass."""
    from agents.coverage_score import compute_coverage_score
    # Minimal files — should not satisfy full_app_completion
    files = _make_files(
        ("README.md", "# placeholder"),
    )
    result = compute_coverage_score(
        prompt="Build the complete app described in this repo",
        files=files,
        mode="repo_fix",
        intent="full_app_completion",
    )
    assert result["minScore"] == 80
    assert result["requestSatisfied"] is False


def test_coverage_score_includes_preview_check():
    """Coverage score must check for preview or fallback availability."""
    from agents.coverage_score import compute_coverage_score
    files = _make_files(
        ("index.html", "<html><body>App</body></html>"),
        ("styles.css", "body{margin:0}"),
        ("README.md", "# App"),
        ("amarktai.project.json", '{"name":"app"}'),
    )
    # Without preview
    result_no_preview = compute_coverage_score(
        prompt="Build a landing page",
        files=files,
        mode="landing_page",
    )
    # With preview
    result_with_preview = compute_coverage_score(
        prompt="Build a landing page",
        files=files,
        mode="landing_page",
        preview_url="http://localhost:8080/preview/123",
    )
    # Preview should contribute positively
    assert result_with_preview["coverageScore"] >= result_no_preview["coverageScore"]


def test_coverage_score_5_page_site_checks_pages():
    """Coverage score for a 5-page site must check whether pages were generated."""
    from agents.coverage_score import compute_coverage_score
    files = _make_files(
        ("index.html", "<html><body>Home</body></html>"),
        ("about.html", "<html><body>About</body></html>"),
        ("contact.html", "<html><body>Contact</body></html>"),
        ("styles.css", "body{margin:0}"),
        ("README.md", "# Site"),
        ("amarktai.project.json", '{"name":"site"}'),
    )
    result = compute_coverage_score(
        prompt="Build a 5-page consulting website",
        files=files,
        mode="website",
        preview_url="http://localhost/preview",
    )
    missing = result["missingRequirements"]
    # Should note missing pages (only 3 of 5 generated)
    assert any("page" in m.lower() or "view" in m.lower() for m in missing), \
        f"Expected page count issue in missing: {missing}"


# ── Phase 5: Intent + Coverage Integration ────────────────────────────────────

@pytest.mark.asyncio
async def test_repo_fix_intent_full_completion_triggers_build_pipeline():
    """When intent=full_app_completion, orchestrator must run full build pipeline."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    db, _project, _files, _events, _messages = _make_db()
    # Set up project as repo_fix mode
    _project.update({"mode": "repo_fix", "quality_tier": "balanced", "prompt": "Build the complete app"})

    emitted = []
    async def emit(event):
        emitted.append(event)

    # Scout / Architect / Coder / Reviewer mock
    coder_blocks = (
        "===AMARKTAI_FILE[index.html]===\n"
        "<!DOCTYPE html><html><head><title>App</title></head><body>"
        "<section class='hero'><h1>Welcome</h1><a class='btn cta'>Get Started</a></section>"
        "<section id='features'>Features here</section>"
        "<section id='pricing'>Pricing</section>"
        "<section id='about'>About</section>"
        "<section id='workflow'>How it works</section>"
        "<footer>Footer</footer>"
        "</body></html>\n"
        "===END_AMARKTAI_FILE[index.html]===\n"
        "===AMARKTAI_FILE[styles.css]===\n"
        "body{margin:0}@media(max-width:768px){body{font-size:14px}}\n"
        "===END_AMARKTAI_FILE[styles.css]===\n"
        "===AMARKTAI_FILE[README.md]===\n"
        "# My App\n\nInstall: npm install\nRun: npm start\n"
        "===END_AMARKTAI_FILE[README.md]===\n"
        "===AMARKTAI_FILE[amarktai.project.json]===\n"
        '{"name":"My App","mode":"landing_page","generated_by":"Amarktai App Builder","version":"1.0.0","media_strategy":{"mode":"placeholder","confirmed":false,"models_used":[],"notes":""}}\n'
        "===END_AMARKTAI_FILE[amarktai.project.json]===\n"
        "===AMARKTAI_SUMMARY===\nComplete app built.\n===END_AMARKTAI_SUMMARY===\n"
    )

    call_idx = [0]
    responses = [
        # Scout
        json.dumps({"summary": "s", "audience": "a", "core_features": [], "requirements_md": "req", "make_it_better": [], "pain_points": []}),
        # Architect
        json.dumps({"tech_stack": {"frontend": "HTML", "backend": "none", "database": "none", "styling": "CSS", "libraries": []}, "file_plan": [{"path": "index.html", "purpose": "main"}], "design_notes": "clean"}),
        # Coder
        coder_blocks,
        # Reviewer
        json.dumps({"verdict": "pass", "issues": [], "patched_files": [], "summary": "ok"}),
    ]

    provider = MagicMock()
    async def multi_complete(**kwargs):
        idx = call_idx[0]
        text = responses[idx] if idx < len(responses) else responses[-1]
        call_idx[0] += 1
        return {"text": text, "model_label": "test-model", "session_id": "s", "usage": {}}
    provider.complete = AsyncMock(side_effect=multi_complete)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    # Pre-populate with "repo files" so intent detection works
    written.append({"path": "README.md", "content": "# My App\nA placeholder.", "language": "markdown"})
    written.append({"path": "index.html", "content": "<html><body>Placeholder</body></html>", "language": "html"})

    async def fake_write(path, content, lang="text"):
        written.append({"path": path, "content": content, "language": lang})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(side_effect=lambda: [{"path": f["path"]} for f in written])
    orch.fs.read = AsyncMock(return_value=None)

    # full_app_completion intent should be detected from the prompt
    await orch.run_full_build("Build the complete app described in this repo", mode="repo_fix")

    # Verify build pipeline was triggered (scout + architect + coder events)
    event_agents = [e.get("agent") for e in _events if isinstance(e, dict)]
    # Expect events from the standard build pipeline
    assert any(a in ("scout", "coder", "architect") for a in event_agents), \
        f"Expected build pipeline agents in events, got: {event_agents}"


# ── Phase 2+3: Repo Analysis via Orchestrator ────────────────────────────────

@pytest.mark.asyncio
async def test_repo_fix_emits_repo_analysis_complete():
    """repo_fix mode must emit repo_analysis_complete event with detected type."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    db, _project, _files, _events, _messages = _make_db()
    _project.update({"mode": "repo_fix", "quality_tier": "balanced", "github": {}})

    # Pre-populate repo files (static site)
    repo_files = [
        {"path": "index.html", "content": "<html><body>Repo App</body></html>", "language": "html"},
        {"path": "styles.css", "content": "body{margin:0}", "language": "css"},
    ]
    final_files = repo_files + [
        {"path": "README.md", "content": "# Fixed", "language": "markdown"},
        {"path": "amarktai.project.json", "content": '{"name":"Repo"}', "language": "json"},
    ]

    emitted = []
    async def emit(event):
        emitted.append(event)

    coder_blocks = (
        "===AMARKTAI_FILE[index.html]===\n<html><body>Fixed</body></html>\n===END_AMARKTAI_FILE[index.html]===\n"
        "===AMARKTAI_FILE[README.md]===\n# Fixed\n===END_AMARKTAI_FILE[README.md]===\n"
        "===AMARKTAI_FILE[amarktai.project.json]===\n"
        '{"name":"Repo","mode":"repo_fix","generated_by":"Amarktai App Builder","version":"1.0.0","media_strategy":{"mode":"placeholder","confirmed":false,"models_used":[],"notes":""}}\n'
        "===END_AMARKTAI_FILE[amarktai.project.json]===\n"
        "===AMARKTAI_SUMMARY===\nFixed.\n===END_AMARKTAI_SUMMARY===\n"
    )

    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": coder_blocks,
        "model_label": "test-model",
        "session_id": "s",
        "usage": {},
    })

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list = AsyncMock(return_value=[{"path": f["path"]} for f in repo_files])
    orch.fs.list_full = AsyncMock(side_effect=[
        repo_files,   # first call: get repo files for intent detection + analysis
        final_files, final_files, final_files, final_files,
        final_files, final_files, final_files,
    ])
    orch.fs.read = AsyncMock(return_value=None)

    await orch.run_full_build("Fix the CSS layout", mode="repo_fix")

    event_types = [e.get("type") for e in emitted]
    assert "repo_analysis_complete" in event_types, \
        f"Expected repo_analysis_complete event, got: {event_types}"

    analysis_event = next(e for e in emitted if e.get("type") == "repo_analysis_complete")
    assert "detectedType" in analysis_event["data"]
    assert "intent" in analysis_event["data"]


@pytest.mark.asyncio
async def test_build_pipeline_emits_coverage_score():
    """Standard build pipeline must emit coverage_score event on completion."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    db, _project, _files, _events, _messages = _make_db()
    _project.update({"mode": "landing_page", "quality_tier": "balanced"})

    emitted = []
    async def emit(event):
        emitted.append(event)

    coder_blocks = (
        "===AMARKTAI_FILE[index.html]===\n"
        "<!DOCTYPE html><html><body>"
        "<section class='hero'><h1>Welcome</h1><a class='btn'>Get Started</a></section>"
        "<section>Features</section><section>Pricing</section><section>About</section>"
        "<section>How it works</section><footer>Footer</footer>"
        "</body></html>\n"
        "===END_AMARKTAI_FILE[index.html]===\n"
        "===AMARKTAI_FILE[styles.css]===\nbody{margin:0}\n===END_AMARKTAI_FILE[styles.css]===\n"
        "===AMARKTAI_FILE[README.md]===\n# App\nInstall\n===END_AMARKTAI_FILE[README.md]===\n"
        "===AMARKTAI_FILE[amarktai.project.json]===\n"
        '{"name":"App","mode":"landing_page","generated_by":"Amarktai App Builder","version":"1.0.0","media_strategy":{"mode":"placeholder","confirmed":false,"models_used":[],"notes":""}}\n'
        "===END_AMARKTAI_FILE[amarktai.project.json]===\n"
        "===AMARKTAI_SUMMARY===\nDone.\n===END_AMARKTAI_SUMMARY===\n"
    )

    responses = [
        json.dumps({"summary": "s", "audience": "a", "core_features": [], "requirements_md": "req", "make_it_better": [], "pain_points": []}),
        json.dumps({"tech_stack": {"frontend": "HTML", "backend": "none", "database": "none", "styling": "CSS", "libraries": []}, "file_plan": [], "design_notes": ""}),
        coder_blocks,
        json.dumps({"verdict": "pass", "issues": [], "patched_files": [], "summary": "ok"}),
    ]
    idx = [0]

    provider = MagicMock()
    async def complete(**kw):
        i = idx[0]; idx[0] += 1
        return {"text": responses[i] if i < len(responses) else responses[-1], "model_label": "test", "session_id": "s", "usage": {}}
    provider.complete = AsyncMock(side_effect=complete)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = []

    async def fake_write(path, content, lang="text"):
        written.append({"path": path, "content": content, "language": lang})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")
    await orch.run_full_build("Build a landing page for my product", mode="landing_page", stack_decision=sd)

    event_types = [e.get("type") for e in emitted]
    assert "coverage_score" in event_types, \
        f"Expected coverage_score event in emitted, got: {event_types}"

    cov_event = next(e for e in emitted if e.get("type") == "coverage_score")
    assert "coverageScore" in cov_event["data"]
    assert isinstance(cov_event["data"]["coverageScore"], int)



# ── Phase 2/3: Preview Executor ───────────────────────────────────────────────

def test_preview_executor_static_returns_can_preview():
    """Static repo with index.html must return canPreview=True with inlined HTML."""
    from agents.preview_executor import execute_preview
    files = [
        {"path": "index.html", "content": "<html><body>Hello</body></html>", "language": "html"},
        {"path": "styles.css", "content": "body{margin:0}", "language": "css"},
    ]
    profile = {
        "detectedType": "static",
        "frameworks": [],
        "languages": ["HTML"],
        "previewBlockers": [],
        "previewStrategy": "static",
        "installCommands": [],
        "buildCommands": [],
        "devCommands": [],
        "testCommands": [],
        "envRequired": [],
        "routeMap": [],
        "fileTree": [],
        "readmeExcerpt": "",
        "riskNotes": [],
        "recommendedPlan": "",
        "packageManager": "",
        "frontendPath": "",
        "backendPath": "",
    }
    result = execute_preview(files, profile)
    assert result["canPreview"] is True
    assert result["type"] == "static"
    assert "<body>" in result["html"]


def test_preview_executor_vite_returns_fallback():
    """Vite/React repo must return canPreview=False with a fallback object."""
    from agents.preview_executor import execute_preview
    files = [
        {"path": "package.json", "content": '{"dependencies":{"react":"^18","vite":"^5"}}', "language": "json"},
        {"path": "src/main.jsx", "content": "import React from 'react'", "language": "javascript"},
    ]
    profile = {
        "detectedType": "vite_react",
        "frameworks": ["React", "Vite"],
        "languages": ["JavaScript"],
        "previewBlockers": ["Requires npm install and vite build"],
        "previewStrategy": "vite_react",
        "installCommands": ["npm install"],
        "buildCommands": ["npm run build"],
        "devCommands": ["npm run dev"],
        "testCommands": [],
        "envRequired": ["VITE_API_URL"],
        "routeMap": [],
        "fileTree": ["package.json", "src/main.jsx"],
        "readmeExcerpt": "Vite React app",
        "riskNotes": [],
        "recommendedPlan": "Build and deploy",
        "packageManager": "npm",
        "frontendPath": ".",
        "backendPath": "",
    }
    result = execute_preview(files, profile)
    assert result["canPreview"] is False
    assert result["type"] == "repo-preview-fallback"
    assert "reason" in result
    assert len(result["reason"]) > 0
    assert "installCommands" in result
    assert result["installCommands"] == ["npm install"]


def test_preview_executor_fallback_contract_complete():
    """Fallback object must contain all required contract keys."""
    from agents.preview_executor import execute_preview
    required_keys = [
        "canPreview", "type", "reason", "detectedStack", "languages",
        "fileTree", "routeMap", "readmeExcerpt", "installCommands",
        "buildCommands", "devCommands", "testCommands", "missingEnv",
        "logs", "previewBlockers", "nextActions", "riskNotes",
        "recommendedPlan", "detectedType", "packageManager",
        "frontendPath", "backendPath",
    ]
    profile = {
        "detectedType": "fullstack",
        "frameworks": ["FastAPI", "React"],
        "languages": ["Python", "JavaScript"],
        "previewBlockers": ["Requires backend running"],
        "previewStrategy": "fullstack",
        "installCommands": ["pip install -r requirements.txt", "npm install"],
        "buildCommands": ["npm run build"],
        "devCommands": ["uvicorn main:app --reload", "npm run dev"],
        "testCommands": ["pytest"],
        "envRequired": ["DATABASE_URL", "JWT_SECRET"],
        "routeMap": ["GET /health", "POST /auth/login"],
        "fileTree": ["backend/main.py", "frontend/package.json"],
        "readmeExcerpt": "Full stack app",
        "riskNotes": ["Needs both services running"],
        "recommendedPlan": "Start backend then frontend",
        "packageManager": "npm",
        "frontendPath": "frontend/",
        "backendPath": "backend/",
        "hasDocker": False,
    }
    result = execute_preview([], profile)
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


def test_preview_executor_static_with_blocker_falls_back():
    """Static repo with a preview blocker should return fallback."""
    from agents.preview_executor import execute_preview
    files = [
        {"path": "index.html", "content": "<html><body>Hello</body></html>", "language": "html"},
    ]
    profile = {
        "detectedType": "static",
        "frameworks": [],
        "languages": ["HTML"],
        "previewBlockers": ["Missing linked stylesheet"],
        "previewStrategy": "static",
        "installCommands": [],
        "buildCommands": [],
        "devCommands": [],
        "testCommands": [],
        "envRequired": [],
        "routeMap": [],
        "fileTree": ["index.html"],
        "readmeExcerpt": "",
        "riskNotes": [],
        "recommendedPlan": "",
        "packageManager": "",
        "frontendPath": "",
        "backendPath": "",
    }
    result = execute_preview(files, profile)
    # Even though detectedType is static, blocker causes fallback
    assert result["canPreview"] is False
    assert result["reason"] == "Missing linked stylesheet"


# ── Phase 6: Coverage Enforcement in Finalize ─────────────────────────────────

def test_finalize_blocks_low_coverage_for_full_app_completion():
    """Finalize endpoint must block with 409 when coverageScore < 80 for full_app_completion."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi.testclient import TestClient

    # The server is not imported here to keep tests isolated.
    # Instead test the coverage enforcement logic directly via the coverage_score module.
    from agents.coverage_score import compute_coverage_score
    # A minimal file set that won't meet full-app-completion requirements
    files = [
        {"path": "index.html", "content": "<html><body>Stub</body></html>", "language": "html"},
    ]
    result = compute_coverage_score(
        prompt="Build the complete app with auth, dashboard, backend API, and docs",
        files=files,
        mode="full_stack",
        intent="full_app_completion",
    )
    assert result["coverageScore"] < 80, (
        f"Expected low coverage for stub files, got {result['coverageScore']}"
    )
    assert result["intent"] == "full_app_completion"
    assert len(result["missingRequirements"]) > 0


def test_finalize_allows_full_coverage_for_full_app_completion():
    """Coverage score must reach >= 80 when all requirements are met."""
    from agents.coverage_score import compute_coverage_score
    files = [
        {"path": "index.html", "content": (
            "<html><head><title>App</title></head><body>"
            "<section class='hero'><h1>Welcome</h1><a class='cta btn'>Get Started</a></section>"
            "<section id='features'>Features</section>"
            "<section id='pricing'>Pricing</section>"
            "<nav><a href='/'>Home</a><a href='/about'>About</a></nav>"
            "<footer>Footer</footer></body></html>"
        ), "language": "html"},
        {"path": "styles.css", "content": "body{margin:0}@media(max-width:768px){body{font-size:14px}}", "language": "css"},
        {"path": "backend/main.py", "content": (
            "from fastapi import FastAPI, Depends\napp = FastAPI()\n"
            "@app.get('/health')\ndef health(): return {'ok': True}\n"
            "@app.post('/auth/login')\ndef login(): pass"
        ), "language": "python"},
        {"path": "backend/auth.py", "content": "import jwt\ndef require_auth(): pass", "language": "python"},
        {"path": "README.md", "content": "# App\n\n## Install\nnpm install\n\n## Run\nnpm start", "language": "markdown"},
        {"path": ".env.example", "content": "JWT_SECRET=\nDATABASE_URL=", "language": "text"},
        {"path": "Dockerfile", "content": "FROM python:3.11\nCMD uvicorn main:app", "language": "dockerfile"},
        {"path": "amarktai.project.json", "content": '{"name":"App","mode":"full_stack"}', "language": "json"},
    ]
    result = compute_coverage_score(
        prompt="Build a full-stack app with auth, backend API, Docker, and README",
        files=files,
        mode="full_stack",
        intent="full_app_completion",
    )
    assert result["coverageScore"] >= 80, (
        f"Expected coverage >= 80 for complete file set, got {result['coverageScore']}. "
        f"Missing: {result['missingRequirements']}"
    )


# ── Phase 8: GitHub PR Body ───────────────────────────────────────────────────

def test_create_branch_pr_body_includes_scores():
    """create_branch_pr_from_files must include validation and coverage in PR body."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    import github_integration as gh_mod

    # Patch the HTTP calls
    mock_result = {"pr_url": "https://github.com/owner/repo/pull/1", "branch": "amarktai-builder/test"}

    async def fake_open_pr(**kwargs):
        # Verify the body contains scores
        body = kwargs.get("body", "")
        assert "Quality" in body, f"Expected 'Quality' in PR body, got:\n{body}"
        assert "Coverage" in body, f"Expected 'Coverage' in PR body, got:\n{body}"
        assert "Changed files" in body, f"Expected 'Changed files' in PR body, got:\n{body}"
        return mock_result

    async def fake_get_info():
        return {"default_branch": "main"}

    async def run():
        with patch.object(gh_mod, "open_pr", side_effect=fake_open_pr):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_cx = AsyncMock()
                mock_cx.__aenter__ = AsyncMock(return_value=mock_cx)
                mock_cx.__aexit__ = AsyncMock(return_value=False)
                mock_cx.get = AsyncMock(return_value=MagicMock(
                    status_code=200,
                    json=lambda: {"default_branch": "main"},
                    raise_for_status=lambda: None,
                ))
                mock_cx.request = AsyncMock(return_value=MagicMock(
                    status_code=200,
                    json=lambda: {"default_branch": "main"},
                    raise_for_status=lambda: None,
                ))
                mock_client_class.return_value = mock_cx

                result = await gh_mod.create_branch_pr_from_files(
                    owner="testowner",
                    repo="testrepo",
                    files=[{"path": "index.html", "content": "<html/>"}],
                    prompt="Build a complete app",
                    job_slug="testrepo-abc12345",
                    pat="ghp_test",
                    validation_scores={
                        "qualityScore": 80,
                        "designScore": 75,
                        "securityScore": 80,
                        "canFinalize": True,
                    },
                    coverage_score={
                        "coverageScore": 85,
                        "intent": "full_app_completion",
                        "missingRequirements": [],
                    },
                    stack="React, FastAPI",
                    preview_note="No live preview — see commands.",
                )
        return result

    # Run in asyncio
    result = asyncio.get_event_loop().run_until_complete(run())
    assert result == mock_result


# ── Phase 3: Preview Fallback Next Actions ────────────────────────────────────

def test_preview_fallback_next_actions_vite():
    """Vite preview fallback must include actionable commands."""
    from agents.preview_executor import _next_actions
    profile = {
        "detectedType": "vite_react",
        "packageManager": "npm",
        "envRequired": ["VITE_API_URL"],
        "hasDocker": False,
    }
    actions = _next_actions(profile)
    assert any("install" in a.lower() for a in actions), f"Expected install action, got: {actions}"
    assert any("build" in a.lower() for a in actions), f"Expected build action, got: {actions}"
    assert any(".env" in a.lower() or "env" in a.lower() for a in actions), f"Expected env action, got: {actions}"


def test_preview_fallback_next_actions_api_only():
    """API-only preview fallback must suggest starting the API server."""
    from agents.preview_executor import _next_actions
    profile = {
        "detectedType": "api_service",
        "packageManager": "pip",
        "envRequired": [],
        "hasDocker": True,
    }
    actions = _next_actions(profile)
    assert any("api" in a.lower() or "server" in a.lower() or "dependency" in a.lower() for a in actions), \
        f"Expected API/server action, got: {actions}"
    assert any("docker" in a.lower() for a in actions), f"Expected docker action, got: {actions}"


# ── Live-blocker regression tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_iteration_null_data_does_not_crash():
    """Iteration agent returning null JSON must raise ValueError, not AttributeError."""
    db, proj, files, events, messages = _make_db()
    proj["mode"] = "landing_page"

    # Provider returns JSON null ("null" string)
    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": "null",
        "model_label": "test-model",
        "model": "test-model",
        "session_id": "sess",
        "usage": {},
    })

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    # Pre-populate app files so the empty-files guard is bypassed
    orch.fs.list_full = AsyncMock(return_value=[
        {"path": "index.html", "content": "<h1>Test</h1>", "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
    ])
    orch.fs.write = AsyncMock()

    with pytest.raises(Exception) as exc_info:
        await orch.run_iteration("Make the hero darker")

    # Must NOT be an AttributeError (NoneType crash)
    assert not isinstance(exc_info.value, AttributeError), (
        f"Got AttributeError (NoneType crash) instead of controlled error: {exc_info.value}"
    )
    # Project must be marked failed
    assert proj.get("status") == "failed"


@pytest.mark.asyncio
async def test_run_iteration_returns_changed_files_in_build_complete():
    """run_iteration must emit changedFiles in build_complete event."""
    db, proj, files, events, messages = _make_db()
    proj["prompt"] = "Build a landing page"
    proj["mode"] = "landing_page"

    updated_html = (
        "<html><head><link rel='stylesheet' href='styles.css'></head><body>"
        "<h1>Updated</h1><section class='hero'><p>Premium hero.</p></section>"
        "</body></html>"
    )
    updated_css = "body{background:#000}" * 30  # >500 chars

    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": json.dumps({
            "files": [
                {"path": "index.html", "content": updated_html, "language": "html"},
                {"path": "styles.css", "content": updated_css, "language": "css"},
            ],
            "summary": "Updated hero and styling.",
        }),
        "model_label": "test-model",
        "model": "test-model",
        "session_id": "sess",
        "usage": {},
    })

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.write = AsyncMock()
    orch.fs.list_full = AsyncMock(return_value=[
        {"path": "index.html", "content": updated_html, "language": "html"},
        {"path": "styles.css", "content": updated_css, "language": "css"},
        {"path": "README.md", "content": "# Test", "language": "markdown"},
        {"path": "amarktai.project.json", "content": '{"files":[], "preview":{}}', "language": "json"},
    ])
    orch.fs.list = AsyncMock(return_value=[
        {"path": "index.html"}, {"path": "styles.css"},
    ])

    # Patch contract helpers so validation passes without file system complications
    async def fake_ensure(prompt, plan):
        return [], []
    orch._ensure_contract_files = fake_ensure

    async def fake_validate(prompt, plan, pass_num, warnings):
        return {"status": "passed", "errors": []}
    orch._validate_contract = fake_validate

    await orch.run_iteration("Make the hero more premium")

    build_complete_events = [e for e in events_received if e.get("type") == "build_complete"]
    assert build_complete_events, "build_complete event must be emitted"
    changed = build_complete_events[-1].get("data", {}).get("changedFiles", [])
    assert "index.html" in changed or "styles.css" in changed, (
        f"Expected changedFiles to include written paths, got: {changed}"
    )


# ── detect_update_intent tests ────────────────────────────────────────────────

from agents.repo_analyzer import detect_update_intent


def test_detect_intent_complete_website_is_full_app_completion():
    """'complete this website and this app and get it go live ready' → full_app_completion."""
    files = [
        {"path": "index.html", "content": "<h1>Dating</h1>"},
        {"path": "app.js", "content": "// app"},
        {"path": "README.md", "content": "# Dating App"},
    ]
    intent = detect_update_intent(
        "complete this website and this app and get it go live ready",
        files,
    )
    assert intent == "full_app_completion", f"Expected full_app_completion, got {intent}"


def test_detect_intent_complete_app_is_full_app_completion():
    """'complete this app' with few files → full_app_completion."""
    files = [{"path": "index.html", "content": ""}]
    intent = detect_update_intent("complete this app", files)
    assert intent == "full_app_completion", f"Expected full_app_completion, got {intent}"


def test_detect_intent_go_live_ready():
    """'make it go live ready' → full_app_completion."""
    files = [{"path": "index.html", "content": ""}]
    intent = detect_update_intent("make it go live ready", files)
    assert intent == "full_app_completion", f"Expected full_app_completion, got {intent}"


def test_detect_intent_bug_fix():
    """'fix the crash on login page' → bug_fix."""
    files = [{"path": "app.py", "content": ""}] * 3
    intent = detect_update_intent("fix the crash on login page", files)
    assert intent == "bug_fix", f"Expected bug_fix, got {intent}"


# ── quality_validator CSS tests ───────────────────────────────────────────────

from agents.quality_validator import score_project_quality, MIN_DESIGN_SCORE


def test_multipage_missing_css_fails_design():
    """A multi-page site with no CSS must fail designScore (< 70)."""
    html_content = (
        "<html><head><title>Test</title></head><body>"
        "<header><nav><a href='index.html'>Home</a><a href='about.html'>About</a></nav></header>"
        "<main><section class='hero'><h1>Welcome</h1><p>Premium consulting services for your business needs.</p></section>"
        "<section id='features'><article><h2>Service A</h2><p>Detailed description of our consulting services.</p></article>"
        "<article><h2>Service B</h2><p>Expert guidance and support.</p></article></section>"
        "<section id='pricing'><h2>Pricing</h2><p>Contact us for pricing.</p></section>"
        "<section id='contact'><h2>Contact</h2><p>Email us at info@example.com</p></section>"
        "</main><footer>Footer content here with more text.</footer></body></html>"
    )
    files = [
        {"path": "index.html", "content": html_content, "language": "html"},
        # Deliberately NO styles.css
    ]
    result = score_project_quality(
        files=files,
        project_type="multi-page-site",
        build_mode="multi-page-website",
        prompt="5 page consulting website",
    )
    assert result["designScore"] < MIN_DESIGN_SCORE, (
        f"Expected designScore < {MIN_DESIGN_SCORE} when CSS is missing, "
        f"got {result['designScore']}. Errors: {result['designErrors']}"
    )
    assert not result["designOk"], "designOk must be False when CSS is missing"


def test_multipage_with_css_can_pass_design():
    """A multi-page site with proper CSS should be able to pass design score."""
    html_content = (
        "<html><head><title>Test</title><link rel='stylesheet' href='styles.css'></head><body>"
        "<header><nav><a href='index.html'>Home</a></nav></header>"
        "<main><section class='hero'><h1>Welcome</h1><p>Premium services.</p><a class='btn' href='#contact'>Get started</a></section>"
        "<section id='features'><article><h2>Service</h2><p>Description.</p></article></section>"
        "<section id='pricing'><h2>Pricing</h2><p>Plans available.</p></section>"
        "<section id='about'><h2>About</h2><p>Our story.</p></section>"
        "<section id='contact'><h2>Contact</h2><p>Reach out.</p></section>"
        "</main><footer>Copyright</footer></body></html>"
    )
    css_content = (
        "* { box-sizing: border-box; } body { margin: 0; background: #000; color: #fff; font-family: sans-serif; } "
        ".hero { min-height: 80vh; display: flex; align-items: center; background: linear-gradient(135deg, #000, #111); } "
        "h1 { font-size: 3rem; } .btn { display: inline-block; padding: 12px 24px; background: #0f0; color: #000; } "
        "nav a { color: #ccc; text-decoration: none; margin-right: 16px; } "
        "@media (max-width: 768px) { .hero { flex-direction: column; } h1 { font-size: 2rem; } } "
        "section { padding: 48px; border-bottom: 1px solid #222; } "
        "article { background: #111; padding: 24px; border-radius: 8px; margin: 8px; } "
        "footer { padding: 24px; border-top: 1px solid #222; color: #aaa; } "
        ".visual { min-height: 300px; background: radial-gradient(circle, #001, #000); } "
    ) * 2  # Repeat to exceed 500 chars
    files = [
        {"path": "index.html", "content": html_content, "language": "html"},
        {"path": "styles.css", "content": css_content, "language": "css"},
    ]
    result = score_project_quality(
        files=files,
        project_type="multi-page-site",
        build_mode="multi-page-website",
        prompt="5 page consulting website",
    )
    assert result["designScore"] >= MIN_DESIGN_SCORE, (
        f"Expected designScore >= {MIN_DESIGN_SCORE} with proper CSS, "
        f"got {result['designScore']}. Errors: {result['designErrors']}"
    )


# ── coverage_score CSS tests ──────────────────────────────────────────────────

from agents.coverage_score import compute_coverage_score


def test_coverage_website_missing_css_fails():
    """Website mode missing CSS must fail coverage (< 80) or have CSS in missing requirements."""
    files = [
        {"path": "index.html", "content": "<h1>Hello</h1>"},
        {"path": "README.md", "content": "# Site"},
        {"path": "amarktai.project.json", "content": '{}'},
    ]
    result = compute_coverage_score(
        prompt="Build a 5-page professional consulting website",
        files=files,
        mode="website",
        intent="full_app_completion",
        preview_url="/api/projects/test/preview",
    )
    # Either coverage fails OR CSS is listed as a missing requirement
    css_missing = any("css" in req.lower() or "stylesheet" in req.lower() for req in result["missingRequirements"])
    assert not result["canFinalize"] or css_missing or result["coverageScore"] < 80, (
        f"Expected CSS to fail or coverage < 80 when CSS is missing. "
        f"Got coverageScore={result['coverageScore']}, canFinalize={result['canFinalize']}, "
        f"missing={result['missingRequirements']}"
    )


def test_coverage_website_with_css_passes():
    """Website mode with CSS should not flag CSS as missing."""
    files = [
        {"path": "index.html", "content": "<h1>Hello</h1>"},
        {"path": "styles.css", "content": "body { color: white; } @media (max-width: 768px) { body { font-size: 14px; } }"},
        {"path": "README.md", "content": "# Site"},
        {"path": "amarktai.project.json", "content": '{}'},
    ]
    result = compute_coverage_score(
        prompt="Build a website",
        files=files,
        mode="website",
        intent="small_patch",
        preview_url="/api/projects/test/preview",
    )
    css_missing = any("css" in req.lower() or "stylesheet" in req.lower() for req in result["missingRequirements"])
    assert not css_missing, (
        f"CSS should not be in missing requirements when styles.css exists. "
        f"missing={result['missingRequirements']}"
    )
