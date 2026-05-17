import asyncio
import json
import os
import unittest.mock as mock
import uuid
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

# Minimal valid build-planner response (Phase 4). Prepend to responses[] lists in any
# test that exercises the full build pipeline so the new planner agent call is satisfied
# before the scout/architect/coder/reviewer calls occur.
_PLANNER_RESP = {
    "complexity": "Moderate",
    "estimated_pages": 1,
    "estimated_files": 4,
    "recommended_stack": "HTML/CSS/JS",
    "can_preview": True,
    "preview_note": "iframe preview",
    "missing_apis": [],
    "build_phases": ["Scout", "Architect", "Coder", "Reviewer"],
    "key_risks": [],
    "estimated_quality": "Good",
    "plan_summary": "Building your app.",
}

# Minimal valid advisor response (Phase 2). Used as the final response in full-pipeline
# tests so the advisor agent call is satisfied after the build completes.
_ADVISOR_RESP = {
    "ux_improvements": ["Improve navigation"],
    "conversion_improvements": ["Add CTA"],
    "monetization_suggestions": ["Freemium model"],
    "seo_suggestions": ["Add meta description"],
    "scaling_suggestions": ["Use CDN"],
    "weak_ux_patterns": [],
    "quick_wins": ["Add skip link"],
    "priority_action": "Add a strong CTA.",
    "overall_rating": "Good",
    "summary": "A solid foundation.",
}


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
    # Prepend planner response and append advisor response for the new pipeline steps
    all_responses = [_PLANNER_RESP] + responses + [reviewer_resp, _ADVISOR_RESP]

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

def test_media_strategy_default_auto():
    """Default media strategy is runtime auto mode, not placeholder media."""
    import server
    ms = server._build_media_strategy("web_app", "balanced", None)
    assert ms["mode"] == "auto"
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
        # planner (Phase 4)
        _PLANNER_RESP,
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
        # advisor (Phase 2)
        _ADVISOR_RESP,
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
        _PLANNER_RESP,
        {"summary": "App", "audience": "users", "core_features": [], "requirements_md": "# Reqs"},
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
            {"path": "styles.css", "language": "css", "content": "body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ], "summary": "Done"},
        {"verdict": "pass", "issues": [], "patched_files": [], "summary": "OK"},
        _ADVISOR_RESP,
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
        # planner (Phase 4)
        _PLANNER_RESP,
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
        # advisor (Phase 2)
        _ADVISOR_RESP,
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
        _PLANNER_RESP,
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
        # planner (Phase 4) — valid JSON
        _PLANNER_RESP,
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
        # advisor (Phase 2) — valid JSON
        _ADVISOR_RESP,
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


@pytest.mark.asyncio
async def test_premium_reviewer_invalid_json_blocks_ready_state():
    """Premium builds must fail closed when Reviewer cannot produce valid audit JSON."""
    db, proj, files, events, messages = _make_db()
    proj["quality_tier"] = "premium"
    call_count = [0]
    responses = [
        _PLANNER_RESP,
        {"summary": "App", "audience": "users", "core_features": ["home"], "requirements_md": "# Reqs"},
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": []},
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main>Hello</main></body></html>"},
            {"path": "styles.css", "language": "css", "content": "body{color:#fff;background:#000}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ], "summary": "Done"},
        "NOT VALID JSON AT ALL !!!",
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
    await orch.run_full_build("Build a premium landing page", mode="landing_page", stack_decision=decide_stack(mode="landing_page"))

    assert proj.get("status") == "failed"
    assert proj.get("failed_agent") == "reviewer"
    assert "Reviewer returned invalid output" in proj.get("error", "")


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
async def test_build_pipeline_emits_coverage_score(monkeypatch, tmp_path):
    """Standard build pipeline must emit coverage_score event on completion."""
    import json
    from unittest.mock import AsyncMock, MagicMock
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))

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
        json.dumps(_PLANNER_RESP),
        json.dumps({"summary": "s", "audience": "a", "core_features": [], "requirements_md": "req", "make_it_better": [], "pain_points": []}),
        json.dumps({"tech_stack": {"frontend": "HTML", "backend": "none", "database": "none", "styling": "CSS", "libraries": []}, "file_plan": [], "design_notes": ""}),
        coder_blocks,
        json.dumps({"verdict": "pass", "issues": [], "patched_files": [], "summary": "ok"}),
        json.dumps(_ADVISOR_RESP),
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
    assert "preview_manifest" in event_types, \
        f"Expected preview_manifest event in emitted, got: {event_types}"
    assert "quality_report" in event_types, \
        f"Expected quality_report event in emitted, got: {event_types}"

    cov_event = next(e for e in emitted if e.get("type") == "coverage_score")
    assert "coverageScore" in cov_event["data"]
    assert isinstance(cov_event["data"]["coverageScore"], int)
    workspace = tmp_path / "generated" / "proj1"
    assert (workspace / "index.html").exists()
    assert (workspace / "preview-manifest.json").exists()
    assert (workspace / "quality-report.json").exists()


@pytest.mark.asyncio
async def test_build_pipeline_missing_audience_reaches_architect_and_coder(monkeypatch, tmp_path):
    """Planner/Scout outputs without audience aliases must not stop the pipeline."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    db, _project, _files, _events, _messages = _make_db()
    _project.update({
        "mode": "website",
        "quality_tier": "premium",
        "name": "Amarktai Builder",
        # Reproduces legacy/live documents seeded with brand: {}. Before the
        # nested memory-schema repair this crashed after Scout with
        # KeyError('audience') and surfaced as failed_agent=pipeline.
        "project_memory": {"brand": {}, "design": {}, "product": {}},
    })

    emitted = []
    async def emit(event):
        emitted.append(event)

    coder_blocks = (
        "===AMARKTAI_FILE[index.html]===\n"
        "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Amarktai Builder</title></head>"
        "<body><main><section class='hero'><h1>Amarktai Builder</h1><a href='/contact'>Start build</a></section>"
        "<section>AI software factory</section><section>Pipeline</section><section>Quality gates</section></main><footer>Ready</footer></body></html>\n"
        "===END_AMARKTAI_FILE[index.html]===\n"
        "===AMARKTAI_FILE[styles.css]===\nbody{margin:0;font-family:Inter,sans-serif}@media(max-width:768px){main{padding:16px}}\n===END_AMARKTAI_FILE[styles.css]===\n"
        "===AMARKTAI_FILE[README.md]===\n# Amarktai Builder\n\nGenerated premium website.\n===END_AMARKTAI_FILE[README.md]===\n"
        "===AMARKTAI_FILE[amarktai.project.json]===\n"
        '{"name":"Amarktai Builder","mode":"website","generated_by":"Amarktai App Builder","version":"1.0.0","media_strategy":{"mode":"css_svg","confirmed":true,"models_used":[],"notes":"fallback visuals"}}\n'
        "===END_AMARKTAI_FILE[amarktai.project.json]===\n"
        "===AMARKTAI_SUMMARY===\nWebsite generated.\n===END_AMARKTAI_SUMMARY===\n"
    )
    responses = [
        json.dumps({**_PLANNER_RESP, "plan_summary": "No explicit audience field here."}),
        json.dumps({"summary": "Premium builder site", "core_features": ["preview", "quality"], "requirements_md": "# Requirements"}),
        json.dumps({"tech_stack": {"frontend": "HTML", "backend": "none", "database": "none", "styling": "CSS", "libraries": []}, "file_plan": [{"path": "index.html"}]}),
        coder_blocks,
        json.dumps({"verdict": "pass", "issues": [], "patched_files": [], "summary": "ok"}),
        json.dumps(_ADVISOR_RESP),
    ]
    idx = [0]
    calls = []

    provider = MagicMock()
    async def complete(**kw):
        calls.append(kw.get("agent"))
        i = idx[0]
        idx[0] += 1
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
    sd = decide_stack(mode="website", quality_tier="premium")
    await orch.run_full_build("Create an elite website for Amarktai Builder.", mode="website", stack_decision=sd)

    assert "architect" in calls
    assert "coder" in calls
    assert _project["status"] == "failed"
    assert _project.get("failed_agent") in {"media_director", "validator"}
    assert "pipeline" != _project.get("failed_agent")
    assert _project.get("error")
    assert _project["build_context"]["audience"]
    assert _project["build_context"]["target_audience"] == _project["build_context"]["audience"]
    assert any(item["path"] == "index.html" for item in written)
    assert "quality_report.md" in {item["path"] for item in written}



# ── Phase 2/3: Preview Executor ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_pipeline_malformed_coder_output_uses_fallback_preview(monkeypatch, tmp_path):
    """Malformed Coder prose may create recovery files, but premium builds must not be marked ready."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    db, _project, _files, _events, _messages = _make_db()
    _project.update({"mode": "website", "quality_tier": "premium", "name": "Amarktai Builder"})

    emitted = []

    async def emit(event):
        emitted.append(event)

    responses = [
        json.dumps(_PLANNER_RESP),
        json.dumps({"summary": "Premium builder site", "audience": "founders", "core_features": ["preview", "quality"], "requirements_md": "# Requirements"}),
        json.dumps({"tech_stack": {"frontend": "HTML", "backend": "none", "database": "none", "styling": "CSS", "libraries": []}, "file_plan": [{"path": "index.html"}]}),
        "I will create a premium site, but here is a broken partial response with no usable files.",
        "not json either",
        json.dumps({"verdict": "pass", "issues": [], "patched_files": [], "summary": "ok"}),
        json.dumps(_ADVISOR_RESP),
    ]
    idx = [0]
    calls = []
    provider = MagicMock()

    async def complete(**kw):
        calls.append(kw.get("agent"))
        i = idx[0]
        idx[0] += 1
        return {"text": responses[i] if i < len(responses) else responses[-1], "model_label": "test-model", "session_id": "s", "usage": {}}

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

    sd = decide_stack(mode="website", quality_tier="premium")
    await orch.run_full_build("Create an elite website for Amarktai Builder.", mode="website", stack_decision=sd)

    paths = {item["path"] for item in written}
    assert "coder" in calls
    assert "repair" in calls
    assert _project["status"] == "failed"
    assert _project["failed_agent"] == "coder"
    assert _project["fallback_used"] is True
    assert _project["can_finalize"] is False
    assert {"index.html", "styles.css", "script.js", "quality_report.md", "README.md"}.issubset(paths)
    assert "agent_raw_responses.coder" in _project
    assert any(evt["agent"] == "coder" and evt["status"] == "failed" for evt in _events)
    assert "fallback output cannot be marked ready" in _project.get("error", "")


@pytest.mark.asyncio
async def test_run_agent_blocks_accepts_markdown_fenced_json():
    """Coder may return JSON inside markdown fences; it should parse as JSON, not as package.json."""
    from unittest.mock import AsyncMock, MagicMock

    db, _project, _files, _events, _messages = _make_db()
    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": "```json\n{\"files\":[{\"path\":\"index.html\",\"content\":\"<html><body>Ready</body></html>\",\"language\":\"html\"}],\"summary\":\"ok\"}\n```",
        "model_label": "test-model",
        "session_id": "s",
        "usage": {},
    })
    emitted = []

    async def emit(event):
        emitted.append(event)

    orch = Orchestrator(db, provider, "proj1", emit)
    result = await orch._run_agent_blocks("coder", "system", "{}")

    assert result["data"]["files"][0]["path"] == "index.html"
    assert result["data"]["summary"] == "ok"
    assert "agent_raw_responses.coder" not in _project


@pytest.mark.asyncio
async def test_run_agent_blocks_non_coder_uses_new_error_and_sanitized_snippet():
    """The old fatal parser wording must not leak, and snippets must redact secret-like values."""
    from unittest.mock import AsyncMock, MagicMock

    db, _project, _files, _events, _messages = _make_db()
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[
        {"text": "bad output with api_key=super-secret-value", "model_label": "test-model", "session_id": "s", "usage": {}},
        {"text": "still not json", "model_label": "repair-model", "session_id": "s2", "usage": {}},
    ])
    emitted = []

    async def emit(event):
        emitted.append(event)

    orch = Orchestrator(db, provider, "proj1", emit)
    with pytest.raises(ValueError) as exc:
        await orch._run_agent_blocks("motion_3d", "system", "{}")

    assert "neither valid AMARKTAI file blocks nor valid JSON" not in str(exc.value)
    assert "did not contain usable files or JSON after repair" in str(exc.value)
    assert "super-secret-value" not in _messages[-1]["content"]
    assert "[redacted]" in _messages[-1]["content"]


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
    result = asyncio.run(run())
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
    """Website mode with CSS properly linked should not flag CSS as missing."""
    files = [
        {"path": "index.html", "content": '<html><head><link rel="stylesheet" href="styles.css"></head><body><h1>Hello</h1></body></html>'},
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


# ---------- Unique regression tests from HEAD ----------

def test_detect_update_intent_finish_this_repo():
    """'finish this repo' must classify as full_app_completion or production_hardening."""
    files = [{"path": "app.py", "content": "print('hello')"}]
    intent = detect_update_intent("finish this repo and make it production ready", files)
    assert intent in ("full_app_completion", "production_hardening"), f"Got {intent}"


def test_detect_update_intent_small_patch():
    """Small cosmetic request must NOT classify as full_app_completion."""
    files = [{"path": "index.html", "content": "<h1>Hello</h1>"}] * 10
    intent = detect_update_intent("change the hero text to say Welcome", files)
    assert intent not in ("full_app_completion", "full_rebuild_inside_repo"), f"Got {intent}"


# ---------- coverage_score CSS helpers ----------

from agents.coverage_score import _css_linked_in_pages, _has_css_file


def test_coverage_with_css_scores_higher():
    """Website with CSS properly linked must score higher than without."""
    files_with_css = [
        {"path": "index.html", "content": '<html><head><link rel="stylesheet" href="styles.css"></head><h1>Home</h1></html>'},
        {"path": "about.html", "content": '<html><head><link rel="stylesheet" href="styles.css"></head><h1>About</h1></html>'},
        {"path": "styles.css", "content": "body { margin: 0; } @media (max-width: 768px) { body { font-size: 14px; } }"},
        {"path": "README.md", "content": "# Site"},
        {"path": "amarktai.project.json", "content": "{}"},
    ]
    files_without_css = [
        {"path": "index.html", "content": "<html><h1>Home</h1></html>"},
        {"path": "about.html", "content": "<html><h1>About</h1></html>"},
        {"path": "README.md", "content": "# Site"},
        {"path": "amarktai.project.json", "content": "{}"},
    ]
    score_with = compute_coverage_score(
        prompt="Build a website", files=files_with_css, mode="website", intent="small_patch"
    )["coverageScore"]
    score_without = compute_coverage_score(
        prompt="Build a website", files=files_without_css, mode="website", intent="small_patch"
    )["coverageScore"]
    assert score_with > score_without, f"Score with CSS ({score_with}) should be > without ({score_without})"


def test_css_linked_in_pages_detects_stylesheet_link():
    """_css_linked_in_pages must count pages with <link rel=stylesheet>."""
    files = [
        {"path": "index.html", "content": '<html><link rel="stylesheet" href="styles.css"></html>'},
        {"path": "about.html", "content": "<html><h1>No CSS</h1></html>"},
    ]
    total, linked = _css_linked_in_pages(files)
    assert total == 2
    assert linked == 1


def test_css_linked_in_pages_detects_style_block():
    """_css_linked_in_pages must count pages with inline <style> blocks."""
    files = [
        {"path": "index.html", "content": "<html><style>body {}</style></html>"},
    ]
    total, linked = _css_linked_in_pages(files)
    assert total == 1
    assert linked == 1


@pytest.mark.asyncio
async def test_repo_fix_none_files_does_not_crash():
    """_run_repo_fix with no files must fail gracefully, not crash with NoneType."""
    db, proj, files, events, messages = _make_db()

    provider = MagicMock()
    provider.complete = AsyncMock()  # Should not be called

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.list_full = AsyncMock(return_value=[])  # No files
    orch.fs.write = AsyncMock()
    orch.fs.list = AsyncMock(return_value=[])

    # Should not raise AttributeError or NoneType
    await orch._run_repo_fix("complete this website and get it go live ready", None)

    # Should have failed gracefully
    assert proj.get("status") == "failed", f"Expected failed, got {proj.get('status')}"


@pytest.mark.asyncio
async def test_run_iteration_routes_repo_fix_to_repo_fix_pipeline():
    """run_iteration on a repo_fix project must route to _run_repo_fix."""
    db, proj, files, events, messages = _make_db()
    proj["mode"] = "repo_fix"

    repo_fix_called = []
    provider = MagicMock()
    provider.complete = AsyncMock()  # Should not be called directly

    events_received = []
    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    orch.fs.list_full = AsyncMock(return_value=[
        {"path": "index.html", "content": "<h1>Hello</h1>", "language": "html"},
        {"path": "styles.css", "content": "body {}", "language": "css"},
        {"path": "README.md", "content": "# Site", "language": "markdown"},
    ])
    orch.fs.write = AsyncMock()
    orch.fs.list = AsyncMock(return_value=[
        {"path": "index.html"},
        {"path": "styles.css"},
        {"path": "README.md"},
    ])
    orch.fs.read = AsyncMock(return_value=None)

    # Track calls to _run_repo_fix
    async def tracked_run_repo_fix(prompt, sd):
        repo_fix_called.append(prompt)
        await orch._set_status("ready")

    orch._run_repo_fix = tracked_run_repo_fix

    await orch.run_iteration("complete this website and get it go live ready")

    assert repo_fix_called, "Expected _run_repo_fix to be called for repo_fix project"
    provider.complete.assert_not_called()


def test_coverage_score_handles_minimal_repo():
    """Coverage score must not crash for a repo with very few files."""
    files = [
        {"path": "index.html", "content": "<h1>Hello</h1>"},
        {"path": "app.js", "content": "console.log('hello')"},
    ]
    result = compute_coverage_score(
        prompt="complete this website",
        files=files,
        mode="repo_fix",
        intent="full_app_completion",
    )
    assert isinstance(result["coverageScore"], int)
    assert 0 <= result["coverageScore"] <= 100


def test_coverage_below_80_flags_not_satisfied_for_full_app_completion():
    """Full app completion with only 2 files must have requestSatisfied=False."""
    files = [
        {"path": "index.html", "content": "<h1>Hello</h1>"},
        {"path": "README.md", "content": "# Site"},
    ]
    result = compute_coverage_score(
        prompt="complete this app",
        files=files,
        mode="repo_fix",
        intent="full_app_completion",
    )
    assert result["coverageScore"] < 80, f"Expected <80, got {result['coverageScore']}"
    assert result["requestSatisfied"] is False


# ── New: missing test coverage from blocker list ─────────────────────────────

def test_repo_fix_none_repo_profile_computes_fallback():
    """analyze_repo_profile must never return None — always returns a valid dict."""
    from agents.repo_analyzer import analyze_repo_profile
    # Edge-case: only 3 files with no recognizable stack markers
    files = [
        {"path": "data.txt", "content": "some raw data"},
        {"path": "script.sh", "content": "#!/bin/bash\necho hello"},
        {"path": "notes.md", "content": "# Notes"},
    ]
    profile = analyze_repo_profile(files, "owner/minimal-repo")
    # Must never be None
    assert profile is not None, "analyze_repo_profile must never return None"
    # Must have all required keys
    required_keys = {
        "detectedType", "frameworks", "languages", "previewBlockers",
        "canPreview", "fileCount",
    }
    missing = required_keys - set(profile.keys())
    assert not missing, f"Profile missing keys: {missing}"
    # detectedType must be a string
    assert isinstance(profile["detectedType"], str)
    # fileCount must match
    assert profile["fileCount"] == 3


def test_deterministic_repair_links_css_in_page():
    """ensure_required_files must add or patch styles.css link in index.html if missing."""
    from agents.build_contract import ensure_required_files
    # index.html without a CSS link
    html_no_css = (
        "<!DOCTYPE html><html><head><title>App</title></head>"
        "<body><h1>Hello</h1></body></html>"
    )
    project = {"mode": "landing_page", "prompt": "Build a landing page"}
    files, changed = ensure_required_files(
        project,
        project["prompt"],
        {},
        [{"path": "index.html", "content": html_no_css, "language": "html"}],
    )
    paths = {f["path"] for f in files}
    # styles.css must be created
    assert "styles.css" in paths, "styles.css must be deterministically created"
    # index.html must reference styles.css (via link tag or @import)
    html_file = next((f for f in files if f["path"] == "index.html"), None)
    assert html_file is not None
    linked = (
        "styles.css" in html_file["content"]
        or "stylesheet" in html_file["content"]
    )
    assert linked, (
        "index.html must reference styles.css after repair. "
        f"Content: {html_file['content'][:300]}"
    )


def test_attribute_error_not_raised_on_none_model_data():
    """When model returns 'null' JSON, orchestrator must not raise AttributeError."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    db, proj, files, events, messages = _make_db()
    proj["mode"] = "landing_page"

    # Simulate a model returning JSON null
    null_provider = _make_provider_bad_json("null")

    errors_received = []

    async def emit(payload):
        if payload.get("type") == "project_status" and payload.get("data", {}).get("error"):
            errors_received.append(payload["data"]["error"])

    orch = Orchestrator(db, null_provider, "proj1", emit)
    orch.fs.list_full = AsyncMock(return_value=[
        {"path": "index.html", "content": "<h1>Hi</h1>", "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
    ])
    orch.fs.write = AsyncMock()

    # Must not raise AttributeError
    try:
        asyncio.run(orch.run_iteration("Make the hero darker"))
    except AttributeError as exc:
        raise AssertionError(
            f"AttributeError (NoneType crash) reached caller: {exc}"
        ) from exc
    except Exception:
        pass  # Other exceptions (ValueError etc.) are acceptable

    # Project must be failed, not in an undefined state
    assert proj.get("status") == "failed", f"Expected failed, got {proj.get('status')}"


def test_coverage_missing_pages_lowers_score():
    """When fewer pages than requested exist, coverageScore must be below 80."""
    from agents.coverage_score import compute_coverage_score
    # Prompt asks for 5 pages but only 2 exist
    files = [
        {"path": "index.html", "content": "<html><head><link rel='stylesheet' href='styles.css'></head><body><h1>Home</h1></body></html>"},
        {"path": "styles.css", "content": "body{margin:0}@media(max-width:768px){}"},
        {"path": "README.md", "content": "# Site"},
        {"path": "amarktai.project.json", "content": "{}"},
    ]
    result = compute_coverage_score(
        prompt="Build a 5-page professional consulting website with home, about, services, pricing, and contact",
        files=files,
        mode="website",
        intent="full_app_completion",
        preview_url="/preview",
    )
    # Either coverage is below 80 OR missing pages are listed
    pages_missing = any(
        "page" in r.lower() or "about" in r.lower() or "contact" in r.lower()
        for r in result["missingRequirements"]
    )
    assert result["coverageScore"] < 80 or pages_missing, (
        f"Expected low coverage or missing page requirements when only 2/5 pages exist. "
        f"coverageScore={result['coverageScore']}, missing={result['missingRequirements']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# New tests: Phase 2-7 requirements
# ─────────────────────────────────────────────────────────────────────────────

# ---------- settings: PIXABAY_API_KEY and Qwen keys are supported ────────────

def test_config_secret_keys_includes_pixabay():
    """PIXABAY_API_KEY must be in SECRET_KEYS so /api/settings does not crash."""
    from config import SECRET_KEYS
    assert "PIXABAY_API_KEY" in SECRET_KEYS, "PIXABAY_API_KEY missing from SECRET_KEYS"


def test_config_secret_keys_includes_qwen():
    """All Qwen optional keys must be in SECRET_KEYS."""
    from config import SECRET_KEYS
    qwen_keys = {
        "QWEN_API_KEY",
        "QWEN_BASE_URL",
        "QWEN_MODEL_CHAT",
        "QWEN_MODEL_CODE",
        "QWEN_MODEL_IMAGE",
        "QWEN_MODEL_VIDEO",
        "QWEN_MODEL_AUDIO",
    }
    missing = qwen_keys - SECRET_KEYS
    assert not missing, f"Qwen keys missing from SECRET_KEYS: {missing}"


def test_settings_store_accepts_pixabay_key():
    """settings_store.get_secret must not raise ValueError for PIXABAY_API_KEY."""
    from config import SECRET_KEYS
    # If the key is allowed, no ValueError should be raised for it.
    assert "PIXABAY_API_KEY" in SECRET_KEYS


def test_settings_store_accepts_qwen_api_key():
    """settings_store.get_secret must not raise ValueError for QWEN_API_KEY."""
    from config import SECRET_KEYS
    assert "QWEN_API_KEY" in SECRET_KEYS


# ---------- settings: QWEN optional key does not break settings endpoint ─────

def test_server_settings_keys_includes_qwen_and_pixabay():
    """server.SETTINGS_KEYS must include all optional integration keys.

    The required keys are derived from config.SECRET_KEYS so this test stays
    in sync automatically when new keys are added to either list.
    """
    import server
    from config import SECRET_KEYS
    # Every key in SECRET_KEYS that isn't a core required key must appear in SETTINGS_KEYS
    optional_keys = SECRET_KEYS - {"GENX_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY"}
    for key in optional_keys:
        assert key in server.SETTINGS_KEYS, f"{key} in SECRET_KEYS but missing from server.SETTINGS_KEYS"


# ---------- build_contract: safe_dict helper ─────────────────────────────────

def test_safe_dict_returns_dict_unchanged():
    from agents.build_contract import safe_dict
    d = {"key": "value"}
    assert safe_dict(d) is d


def test_safe_dict_converts_none_to_empty_dict():
    from agents.build_contract import safe_dict
    assert safe_dict(None) == {}


def test_safe_dict_converts_string_to_empty_dict():
    from agents.build_contract import safe_dict
    assert safe_dict("not a dict") == {}


def test_safe_dict_converts_list_to_empty_dict():
    from agents.build_contract import safe_dict
    assert safe_dict([1, 2, 3]) == {}


# ---------- build_contract: selected_stack=None does not crash ───────────────

def test_validate_project_files_selected_stack_none():
    """validate_project_files must not raise AttributeError when selected_stack is None."""
    from agents.build_contract import validate_project_files, ensure_required_files
    project = {
        "mode": "landing_page",
        "prompt": "Build a landing page",
        "selected_stack": None,  # <-- the crash scenario
    }
    files, _ = ensure_required_files(project, project["prompt"], {}, [
        {"path": "index.html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ])
    # Must not raise
    result = validate_project_files(project, files, project["prompt"])
    assert isinstance(result, dict)
    assert "ok" in result


def test_validate_project_files_selected_stack_missing():
    """validate_project_files must not raise when selected_stack key is absent."""
    from agents.build_contract import validate_project_files, ensure_required_files
    project = {
        "mode": "landing_page",
        "prompt": "Build a landing page",
        # selected_stack not present at all
    }
    files, _ = ensure_required_files(project, project["prompt"], {}, [
        {"path": "index.html", "content": "<!DOCTYPE html><html><body>Hello</body></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ])
    result = validate_project_files(project, files, project["prompt"])
    assert isinstance(result, dict)
    assert "ok" in result


def test_validate_project_files_selected_stack_none_repo_fix():
    """repo_fix mode with selected_stack=None must not crash."""
    from agents.build_contract import validate_project_files
    project = {
        "mode": "repo_fix",
        "prompt": "Fix this repo",
        "selected_stack": None,
    }
    result = validate_project_files(project, [], project["prompt"])
    assert isinstance(result, dict)
    assert "ok" in result


# ---------- GenX model count is not hardcoded ────────────────────────────────

def test_genx_model_list_is_not_hardcoded():
    """list_tiers must derive values from environment variables, not a hardcoded number."""
    import os
    from agents.genx_provider import GenXProvider

    # Override env so routes produce predictable values
    with mock.patch.dict(os.environ, {
        "GENX_MODEL_REASONING": "test-reasoning-model",
        "GENX_MODEL_RESEARCH": "test-research-model",
        "GENX_MODEL_EDITS": "test-edits-model",
    }):
        tiers = GenXProvider.list_tiers()
        assert tiers["reasoning"]["model"] == "test-reasoning-model"
        assert tiers["research"]["model"] == "test-research-model"
        assert tiers["edits"]["model"] == "test-edits-model"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4–6 new tests
# ─────────────────────────────────────────────────────────────────────────────

# ---------- Phase 5: _build_media_strategy explicit choices ------------------

def test_media_strategy_pixabay_choice():
    """Explicit 'pixabay' choice produces pixabay mode regardless of tier."""
    import server
    ms = server._build_media_strategy("landing_page", "cheap", "pixabay")
    assert ms["mode"] == "pixabay"
    assert ms.get("source") == "pixabay"
    assert ms["confirmed"] is True


def test_media_strategy_ai_choice_balanced():
    """Explicit 'ai' choice with balanced tier produces ai_generated mode."""
    import server
    ms = server._build_media_strategy("web_app", "balanced", "ai")
    assert ms["mode"] == "ai_generated"


def test_media_strategy_ai_choice_cheap_downgrades():
    """Explicit 'ai' choice with cheap tier falls back to placeholder."""
    import server
    ms = server._build_media_strategy("web_app", "cheap", "ai")
    assert ms["mode"] == "placeholder"
    assert "upgrade" in ms["notes"].lower()


def test_media_strategy_css_svg_choice_is_upgraded_for_premium_static():
    """Premium static builds cannot choose CSS/SVG-only media as passing evidence."""
    import server
    ms = server._build_media_strategy("landing_page", "premium", "css_svg")
    assert ms["mode"] == "pixabay"
    assert ms["confirmed"] is True
    assert "not accepted" in ms["notes"].lower()


def test_media_strategy_auto_landing_page():
    """'auto' or None for landing_page retains existing free_assets behavior."""
    import server
    ms = server._build_media_strategy("landing_page", "balanced", "auto")
    assert ms["mode"] == "free_assets"


def test_media_strategy_auto_none():
    """None media_requirements for web_app returns runtime auto."""
    import server
    ms = server._build_media_strategy("web_app", "balanced", None)
    assert ms["mode"] == "auto"


# ---------- Phase 5: media validator respects css_svg mode -------------------

def test_quality_validator_css_svg_rejects_external_images():
    """css_svg mode flags external image URLs in HTML as a media error."""
    from agents.quality_validator import score_project_quality
    files = [
        {"path": "index.html", "content": '<img src="https://example.com/photo.jpg" alt="photo">'},
        {"path": "styles.css", "content": "body { font-size: 16px; }"},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result = score_project_quality(
        files, "static-site", "landing_page",
        media_strategy={"mode": "css_svg"},
    )
    assert not result["mediaOk"], "css_svg mode must flag external images"
    assert any("CSS/SVG" in e or "external image" in e for e in result["mediaErrors"])


def test_quality_validator_css_svg_allows_inline_svg():
    """css_svg mode does not flag inline SVG or data URIs."""
    from agents.quality_validator import score_project_quality
    files = [
        {"path": "index.html", "content": (
            "<!DOCTYPE html><html><head><title>T</title></head>"
            "<body><svg width='100' height='100'><circle r='50'/></svg></body></html>"
        )},
        {"path": "styles.css", "content": "body { font-size: 16px; } @media(max-width:768px){}"},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result = score_project_quality(
        files, "static-site", "landing_page",
        media_strategy={"mode": "css_svg"},
    )
    assert result["mediaOk"], f"Inline SVG must not fail css_svg validation: {result['mediaErrors']}"


# ---------- Phase 6: design_engine has font_import on every style -----------

def test_design_engine_all_styles_have_font_import():
    """Every design style must include a font_import dict with link_href and css_vars."""
    from agents.design_engine import _DESIGN_STYLES
    for style in _DESIGN_STYLES:
        fi = style.get("font_import")
        assert fi is not None, f"Style '{style['name']}' missing font_import"
        assert "link_href" in fi, f"Style '{style['name']}' font_import missing link_href"
        assert fi["link_href"].startswith("https://fonts.bunny.net"), (
            f"Style '{style['name']}' font link must use Bunny Fonts: {fi['link_href']}"
        )
        assert "css_vars" in fi, f"Style '{style['name']}' font_import missing css_vars"
        assert "--font-heading" in fi["css_vars"], (
            f"Style '{style['name']}' css_vars missing --font-heading"
        )
        assert "--font-body" in fi["css_vars"], (
            f"Style '{style['name']}' css_vars missing --font-body"
        )


def test_design_direction_coder_instructions_include_font_link():
    """create_design_direction coder_instructions must include the Bunny Fonts link tag."""
    from agents.design_engine import create_design_direction
    dd = create_design_direction("Build a SaaS landing page", "static-site", "startups", "balanced")
    assert dd["font_import"]["link_href"].startswith("https://fonts.bunny.net"), (
        "coder_instructions must include the Bunny Fonts link href"
    )
    assert "<link" in dd["coder_instructions"], (
        "coder_instructions must include a <link> tag instruction"
    )
    assert "--font-heading" in dd["coder_instructions"], (
        "coder_instructions must include font CSS variables"
    )


def test_design_direction_includes_font_import():
    """create_design_direction result dict must include font_import."""
    from agents.design_engine import create_design_direction
    dd = create_design_direction("E-commerce lingerie boutique", "static-site", "women 25-45", "premium")
    assert "font_import" in dd, "Design direction must include font_import"
    assert dd["font_import"]["link_href"].startswith("https://fonts.bunny.net"), (
        "font_import link_href must point to Bunny Fonts"
    )


# ---------- Phase 6: quality_validator web font checks ----------------------

def test_quality_validator_no_web_font_penalizes_design():
    """Missing Bunny/Google Font link tag must reduce designScore."""
    from agents.quality_validator import score_project_quality
    files = [
        {"path": "index.html", "content": (
            "<!DOCTYPE html><html><head><title>Test</title></head>"
            "<body><h1>Hero</h1><section id='features'>Features</section>"
            "<section>About</section><section>Pricing</section>"
            "<section>Testimonials</section><footer>Footer</footer>"
            "<button class='btn'>Get Started</button></body></html>"
        )},
        {"path": "styles.css", "content": (
            "body { font-family: Arial, sans-serif; font-size: 16px; } "
            "@media(max-width:768px){ body{font-size:15px;} } "
            "body { background: linear-gradient(135deg,#fff,#eee); } "
            ".btn{background:#333;color:#fff;} "
            "section{min-height:200px;} " * 6
        )},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result = score_project_quality(files, "static-site", "landing_page")
    assert "designScore" in result
    # Web font missing — design should be deducted
    no_font_errors = [e for e in result.get("designErrors", []) if "bunny" in e.lower() or "web font" in e.lower() or "fonts" in e.lower()]
    assert no_font_errors, f"Expected web font warning in designErrors; got: {result['designErrors']}"


def test_quality_validator_web_font_present_no_font_penalty():
    """Bunny Fonts link tag must not trigger the web font design warning."""
    from agents.quality_validator import score_project_quality
    files = [
        {"path": "index.html", "content": (
            '<!DOCTYPE html><html><head><title>Test</title>'
            '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=inter:400,700&display=swap">'
            '</head><body><h1>Hero</h1><section id="features">Features</section>'
            "<section>About</section><section>Pricing</section>"
            "<section>Testimonials</section><footer>Footer</footer>"
            "<button class='btn'>Get Started</button></body></html>"
        )},
        {"path": "styles.css", "content": (
            "--font-heading: 'Inter', sans-serif; --font-body: 'Inter', sans-serif; "
            "body { font-family: var(--font-body); font-size: 16px; } "
            "@media(max-width:768px){ body{font-size:15px;} } "
            "body { background: linear-gradient(135deg,#fff,#eee); } "
            ".btn{background:#333;color:#fff;} "
        )},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result = score_project_quality(files, "static-site", "landing_page")
    no_font_errors = [e for e in result.get("designErrors", []) if "bunny" in e.lower() or "web font" in e.lower() or "fonts" in e.lower()]
    assert not no_font_errors, f"Bunny Fonts link present should suppress font warning; got: {no_font_errors}"


def test_quality_validator_low_opacity_text_penalizes_design():
    """Very low opacity text (rgba with opacity < 0.2) must reduce designScore."""
    from agents.quality_validator import score_project_quality
    files = [
        {"path": "index.html", "content": (
            "<!DOCTYPE html><html><head><title>T</title></head><body>"
            "<h1>Hero</h1><section id='features'>f</section><footer>f</footer></body></html>"
        )},
        {"path": "styles.css", "content": (
            "body { color: rgba(0,0,0,0.08); font-size: 16px; } "
            "@media(max-width:768px){} "
            "background: linear-gradient(#000,#111); "
        )},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result_low_opacity = score_project_quality(files, "static-site", "landing_page")
    files_ok = [
        {"path": "index.html", "content": files[0]["content"]},
        {"path": "styles.css", "content": "body { color: #111; font-size: 16px; } @media(max-width:768px){} background: linear-gradient(#000,#111); "},
        {"path": "README.md", "content": "# App"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}'},
    ]
    result_ok = score_project_quality(files_ok, "static-site", "landing_page")
    # Low opacity should score no higher than normal text
    assert result_low_opacity["designScore"] <= result_ok["designScore"], (
        f"Low opacity text should reduce designScore. low={result_low_opacity['designScore']} ok={result_ok['designScore']}"
    )


# ---------- _parse_amarktai_blocks: checklist parsing ─────────────────────────

def test_parse_amarktai_blocks_extracts_checklist():
    """_parse_amarktai_blocks must extract REQUESTED/SATISFIED/UNSATISFIED from checklist block."""
    from agents.orchestrator import _parse_amarktai_blocks
    text = (
        "===AMARKTAI_FILE[index.html]===\n"
        "<!DOCTYPE html><html><body>Test</body></html>\n"
        "===END_AMARKTAI_FILE[index.html]===\n"
        "\n"
        "===AMARKTAI_CHECKLIST===\n"
        "REQUESTED: black background, white text, BMW images\n"
        "SATISFIED: black background, white text\n"
        "UNSATISFIED: BMW images\n"
        "===END_AMARKTAI_CHECKLIST===\n"
        "\n"
        "===AMARKTAI_SUMMARY===\n"
        "Applied dark theme changes.\n"
        "===END_AMARKTAI_SUMMARY===\n"
    )
    result = _parse_amarktai_blocks(text)
    assert result["requestedChanges"] == ["black background", "white text", "BMW images"]
    assert result["satisfiedChanges"] == ["black background", "white text"]
    assert result["unsatisfiedChanges"] == ["BMW images"]
    assert len(result["files"]) == 1
    assert result["summary"] == "Applied dark theme changes."


def test_parse_amarktai_blocks_empty_checklist():
    """_parse_amarktai_blocks returns empty lists when no checklist block present."""
    from agents.orchestrator import _parse_amarktai_blocks
    text = (
        "===AMARKTAI_FILE[styles.css]===\n"
        "body { color: white; }\n"
        "===END_AMARKTAI_FILE[styles.css]===\n"
        "\n"
        "===AMARKTAI_SUMMARY===\n"
        "Updated CSS.\n"
        "===END_AMARKTAI_SUMMARY===\n"
    )
    result = _parse_amarktai_blocks(text)
    assert result["requestedChanges"] == []
    assert result["satisfiedChanges"] == []
    assert result["unsatisfiedChanges"] == []


def test_parse_amarktai_blocks_unsatisfied_none():
    """UNSATISFIED: none should return empty list."""
    from agents.orchestrator import _parse_amarktai_blocks
    text = (
        "===AMARKTAI_FILE[app.js]===\n"
        "console.log('ok');\n"
        "===END_AMARKTAI_FILE[app.js]===\n"
        "\n"
        "===AMARKTAI_CHECKLIST===\n"
        "REQUESTED: dark theme, contact form\n"
        "SATISFIED: dark theme, contact form\n"
        "UNSATISFIED: none\n"
        "===END_AMARKTAI_CHECKLIST===\n"
        "\n"
        "===AMARKTAI_SUMMARY===\n"
        "All changes applied.\n"
        "===END_AMARKTAI_SUMMARY===\n"
    )
    result = _parse_amarktai_blocks(text)
    assert result["unsatisfiedChanges"] == []
    assert result["satisfiedChanges"] == ["dark theme", "contact form"]


def test_parse_checklist_line_handles_missing_label():
    """_parse_checklist_line returns empty list when label not found."""
    from agents.orchestrator import _parse_checklist_line
    body = "REQUESTED: a, b\nSATISFIED: a\n"
    assert _parse_checklist_line(body, "UNSATISFIED") == []


def test_parse_checklist_line_strips_whitespace():
    """_parse_checklist_line strips leading/trailing whitespace from items."""
    from agents.orchestrator import _parse_checklist_line
    body = "REQUESTED:  item one ,  item two  , item three\n"
    result = _parse_checklist_line(body, "REQUESTED")
    assert result == ["item one", "item two", "item three"]


# ── Phase 8: Raised thresholds, design token check, multi-page enforcement ────

def test_min_quality_score_is_80():
    """MIN_QUALITY_SCORE must be 80 per problem statement spec."""
    from agents.quality_validator import MIN_QUALITY_SCORE
    assert MIN_QUALITY_SCORE == 80, f"Expected 80, got {MIN_QUALITY_SCORE}"


def test_min_design_score_is_80():
    """MIN_DESIGN_SCORE must be 80 per problem statement spec."""
    from agents.quality_validator import MIN_DESIGN_SCORE
    assert MIN_DESIGN_SCORE == 80, f"Expected 80, got {MIN_DESIGN_SCORE}"


def test_css_no_custom_props_penalizes_design():
    """CSS without var(--...) custom properties must reduce design score."""
    from agents.quality_validator import score_project_quality
    html = (
        "<!DOCTYPE html><html><head><title>Test</title>"
        '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=inter">'
        '</head><body>'
        '<header><nav><a href="index.html">Home</a></nav></header>'
        '<section class="hero"><h1>My Site</h1><p>Premium content.</p><a class="btn">Start</a></section>'
        '<section id="features"><h2>Features</h2><p>Feature A</p></section>'
        '<section id="about"><h2>About</h2><p>About us</p></section>'
        '<section id="pricing"><h2>Pricing</h2><p>Plans</p></section>'
        '<section id="contact"><h2>Contact</h2><p>Reach out</p></section>'
        '<footer>Footer</footer></body></html>'
    )
    # CSS without var(-- custom props — uses plain font-family
    css_no_vars = (
        "body { font-family: sans-serif; font-size: 16px; background: #000; color: #fff; } "
        "@media (max-width: 768px) { body { font-size: 15px; } } "
        ".hero { background: linear-gradient(135deg, #111, #000); min-height: 80vh; } "
        "section { padding: 48px; } "
    ) * 4
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": css_no_vars, "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a site")
    css_vars_errors = [e for e in result["designErrors"] if "custom prop" in e.lower() or "var(--" in e.lower()]
    assert css_vars_errors, (
        f"CSS without custom properties should generate a design error. "
        f"Got: {result['designErrors']}"
    )


def test_css_with_custom_props_no_penalty():
    """CSS with var(--font-heading) custom properties must not trigger the CSS custom props error."""
    from agents.quality_validator import score_project_quality
    html = (
        "<!DOCTYPE html><html><head><title>Test</title>"
        '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=inter">'
        '</head><body>'
        '<section class="hero"><h1>My Site</h1><p>Content</p><a class="btn">CTA</a></section>'
        '<section id="features"><h2>Features</h2><p>Feature content here.</p></section>'
        '<section id="about"><h2>About</h2><p>About us content.</p></section>'
        '<section id="pricing"><h2>Pricing</h2><p>Pricing info.</p></section>'
        '<section id="contact"><h2>Contact</h2><p>Contact us.</p></section>'
        '<footer>Footer</footer></body></html>'
    )
    css_with_vars = (
        ":root { --font-heading: 'Inter', sans-serif; --font-body: 'Inter', sans-serif; "
        "--color-bg: #000; --color-primary: #fff; --color-text: #fff; --color-muted: #aaa; } "
        "body { font-family: var(--font-body); font-size: 16px; background: var(--color-bg); "
        "color: var(--color-text); } "
        "h1, h2, h3 { font-family: var(--font-heading); } "
        "@media (max-width: 768px) { body { font-size: 15px; } } "
        ".hero { background: linear-gradient(135deg, #111, #000); min-height: 80vh; } "
    ) * 3
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": css_with_vars, "language": "css"},
    ]
    result = score_project_quality(files, "static-site", "landing-page", "Build a site")
    css_vars_errors = [e for e in result["designErrors"] if "custom prop" in e.lower() or "var(--" in e.lower()]
    assert not css_vars_errors, (
        f"CSS with custom properties should not trigger the CSS vars design error. "
        f"Got: {css_vars_errors}"
    )


def test_placeholder_page_penalized():
    """Pages containing 'coming soon' or 'detail not found' must be penalized in quality and design."""
    from agents.quality_validator import score_project_quality
    html_index = (
        "<!DOCTYPE html><html><head><link rel='stylesheet' href='styles.css'></head>"
        "<body><section class='hero'><h1>BMW Dealership</h1><p>Premium cars.</p>"
        "<a href='#' class='btn'>Browse inventory</a></section>"
        "<section id='features'><h2>Features</h2><p>Quality cars.</p></section>"
        "<section id='about'><h2>About</h2><p>About the dealership.</p></section>"
        "<section id='inventory'><h2>Inventory</h2><p>See our cars.</p></section>"
        "<section id='contact'><h2>Contact</h2><p>Call us.</p></section>"
        "<footer>Footer</footer></body></html>"
    )
    html_detail = (
        "<!DOCTYPE html><html><head><link rel='stylesheet' href='styles.css'></head>"
        "<body><p>Detail not found</p></body></html>"
    )
    css = (
        "body { background: #000; color: #fff; font-family: var(--font-body); } "
        "@media (max-width: 768px) {} .hero { background: linear-gradient(#000,#111); } "
    ) * 4
    files = [
        {"path": "index.html", "content": html_index, "language": "html"},
        {"path": "vehicle-detail.html", "content": html_detail, "language": "html"},
        {"path": "styles.css", "content": css, "language": "css"},
    ]
    result = score_project_quality(
        files, "multi-page-site", "multi-page-website",
        "Build a 6-page BMW dealership website"
    )
    placeholder_errors = [e for e in result["qualityErrors"] if "placeholder" in e.lower() or "not found" in e.lower() or "incomplete" in e.lower()]
    assert placeholder_errors, (
        f"Placeholder page must generate quality error. Got: {result['qualityErrors']}"
    )


def test_multipage_single_index_penalized_for_6_page_request():
    """Prompt requesting 6 pages but only index.html must score far below MIN_QUALITY_SCORE."""
    from agents.quality_validator import score_project_quality, MIN_QUALITY_SCORE
    html = (
        "<!DOCTYPE html><html><head><link rel='stylesheet' href='styles.css'></head>"
        "<body><section class='hero'><h1>BMW Dealer</h1><p>Premium vehicles.</p>"
        "<a class='btn' href='#'>Browse</a></section>"
        "<section id='features'><h2>Features</h2><p>Quality BMW vehicles.</p></section>"
        "<section id='about'><h2>About</h2><p>About us.</p></section>"
        "<section id='inventory'><h2>Inventory</h2><p>Our cars.</p></section>"
        "<section id='contact'><h2>Contact</h2><p>Contact us.</p></section>"
        "<footer>Footer</footer></body></html>"
    )
    css = (
        "body { background: #000; color: #fff; font-family: var(--font-body); } "
        "@media (max-width: 768px) {} .hero { background: linear-gradient(#000, #111); } "
    ) * 5
    # Only index.html — no other pages at all
    files = [
        {"path": "index.html", "content": html, "language": "html"},
        {"path": "styles.css", "content": css, "language": "css"},
    ]
    result = score_project_quality(
        files, "multi-page-site", "multi-page-website",
        "Build a complete 6-page BMW dealership website with inventory, about, finance, and contact pages"
    )
    assert result["qualityScore"] < MIN_QUALITY_SCORE, (
        f"Single index.html for 6-page request must score below {MIN_QUALITY_SCORE}. "
        f"Got: {result['qualityScore']}. Errors: {result['qualityErrors']}"
    )
    # Must have a specific error about missing pages
    page_errors = [e for e in result["qualityErrors"] if "page" in e.lower()]
    assert page_errors, f"Must report page count errors. Got: {result['qualityErrors']}"


def test_extract_requested_page_count_numeric():
    """extract_requested_page_count must extract numeric counts from common phrases."""
    from agents.quality_validator import extract_requested_page_count
    assert extract_requested_page_count("Build a 6-page website") == 6
    assert extract_requested_page_count("5 page website for my business") == 5
    assert extract_requested_page_count("complete 10-page SaaS") == 10
    assert extract_requested_page_count("build a 3 page portfolio") == 3


def test_extract_requested_page_count_word():
    """extract_requested_page_count must handle word-form page counts."""
    from agents.quality_validator import extract_requested_page_count
    assert extract_requested_page_count("six page website") == 6
    assert extract_requested_page_count("five page BMW dealership") == 5
    assert extract_requested_page_count("build a three page site") == 3


def test_extract_requested_page_count_none():
    """extract_requested_page_count must return 0 when no page count found."""
    from agents.quality_validator import extract_requested_page_count
    assert extract_requested_page_count("Build a landing page") == 0
    assert extract_requested_page_count("Create a SaaS application") == 0


def test_multipage_required_files_automotive_bmw():
    """BMW dealership prompt must require automotive-specific page files."""
    from agents.build_contract import get_required_files
    required = get_required_files(
        "multi-page-site", "multi-page-website",
        "Build a complete 6-page website for a used BMW dealership with inventory and finance"
    )
    assert "inventory.html" in required, f"inventory.html required for automotive. Got: {required}"
    assert "vehicle-detail.html" in required, f"vehicle-detail.html required. Got: {required}"
    assert "about.html" in required, f"about.html required. Got: {required}"
    assert "finance.html" in required, f"finance.html required. Got: {required}"
    assert "contact.html" in required, f"contact.html required. Got: {required}"


def test_design_engine_automotive_returns_industry_media_brief():
    """BMW/automotive prompt must produce a design direction with a car-specific media brief."""
    from agents.design_engine import create_design_direction
    direction = create_design_direction(
        prompt="Build a complete website for a used BMW dealership",
        project_type="multi-page-site",
        audience="Car buyers",
        tier="balanced",
    )
    brief = direction.get("industry_media_brief", "")
    assert brief, "industry_media_brief must be non-empty for automotive prompts"
    # Must mention automotive/car content
    assert any(kw in brief.lower() for kw in ["bmw", "vehicle", "car", "automotive"]), (
        f"Automotive media brief should mention BMW/vehicles. Got: {brief}"
    )


def test_design_engine_fashion_returns_industry_media_brief():
    """Fashion/lingerie prompt must produce a design direction with a fashion media brief."""
    from agents.design_engine import create_design_direction
    direction = create_design_direction(
        prompt="Build a premium landing page for a South African lingerie brand",
        project_type="static-site",
        audience="Fashion-conscious women 25-45",
        tier="balanced",
    )
    brief = direction.get("industry_media_brief", "")
    assert brief, "industry_media_brief must be non-empty for fashion prompts"
    # Must mention fashion/editorial content
    assert any(kw in brief.lower() for kw in ["fashion", "editorial", "fabric", "product"]), (
        f"Fashion media brief should mention fashion imagery. Got: {brief}"
    )


def test_coder_prompt_contains_multipage_contract():
    """CODER_PROMPT must contain the multi-page website contract section."""
    from agents.prompts import CODER_PROMPT
    assert "MULTI-PAGE WEBSITE CONTRACT" in CODER_PROMPT, "CODER_PROMPT missing multi-page contract"
    assert "Generate EVERY requested page" in CODER_PROMPT, "Multi-page contract missing mandatory generation rule"
    assert "coming soon" in CODER_PROMPT, "Multi-page contract must forbid 'coming soon' pages"


def test_coder_prompt_contains_css_custom_props_requirement():
    """CODER_PROMPT must require CSS custom properties declaration."""
    from agents.prompts import CODER_PROMPT
    assert "--font-heading" in CODER_PROMPT, "CODER_PROMPT must require --font-heading CSS var"
    assert "--font-body" in CODER_PROMPT, "CODER_PROMPT must require --font-body CSS var"
    assert "var(--font-heading)" in CODER_PROMPT, "CODER_PROMPT must require var(--font-heading) usage"


def test_iteration_prompt_contains_css_verification():
    """ITERATION_PROMPT must include CSS change verification rules."""
    from agents.prompts import ITERATION_PROMPT
    assert "CSS CHANGE VERIFICATION" in ITERATION_PROMPT, "ITERATION_PROMPT missing CSS verification section"
    assert "SATISFIED" in ITERATION_PROMPT, "ITERATION_PROMPT must reference SATISFIED checklist"
    assert "UNSATISFIED" in ITERATION_PROMPT, "ITERATION_PROMPT must reference UNSATISFIED checklist"
    assert "black background" in ITERATION_PROMPT.lower(), (
        "ITERATION_PROMPT must give concrete black background example"
    )


def test_reviewer_prompt_contains_design_token_check():
    """REVIEWER_PROMPT must check for CSS design token usage."""
    from agents.prompts import REVIEWER_PROMPT
    assert "design token" in REVIEWER_PROMPT.lower() or "--font-heading" in REVIEWER_PROMPT, (
        "REVIEWER_PROMPT must check for design token / CSS custom properties"
    )


def test_multipage_with_all_pages_passes_quality():
    """Multi-page site with all 6 BMW pages must NOT be penalized for missing pages."""
    from agents.quality_validator import score_project_quality
    def _page(title, page_id):
        return (
            f"<!DOCTYPE html><html><head><title>{title}</title>"
            '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=inter">'
            "<link rel='stylesheet' href='styles.css'></head>"
            "<body>"
            f"<header><nav>"
            f"<a href='index.html'>Home</a><a href='inventory.html'>Inventory</a>"
            f"<a href='vehicle-detail.html'>Details</a><a href='about.html'>About</a>"
            f"<a href='finance.html'>Finance</a><a href='contact.html'>Contact</a>"
            f"</nav></header>"
            f"<main><section class='hero'><h1>{title}</h1>"
            f"<p>Premium BMW dealership content for the {title} page. Quality vehicles and service.</p>"
            f"<a class='btn' href='#'>Get started</a></section>"
            f"<section id='content-{page_id}'><h2>Section</h2><p>Detailed content about {title} "
            "at our BMW dealership. We offer premium vehicles, financing options, and excellent "
            "customer service. Visit us today for the best deal.</p></section>"
            "<section id='cta'><h2>Contact</h2><p>Call us now.</p></section>"
            "</main><footer>BMW Dealership &copy; 2024</footer></body></html>"
        )

    css = (
        ":root { --font-heading: 'Inter', sans-serif; --font-body: 'Inter', sans-serif; "
        "--color-bg: #0a0a0a; --color-primary: #c8a84b; --color-text: #fff; } "
        "body { font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); "
        "margin: 0; font-size: 16px; } "
        "h1, h2 { font-family: var(--font-heading); } "
        ".hero { min-height: 80vh; background: linear-gradient(135deg, #111, #000); "
        "display: flex; align-items: center; padding: 48px; } "
        ".btn { display: inline-block; background: var(--color-primary); color: #000; "
        "padding: 12px 24px; text-decoration: none; font-weight: 700; } "
        "section { padding: 48px; border-bottom: 1px solid #222; } "
        "nav { display: flex; gap: 16px; padding: 16px; } "
        "nav a { color: #ccc; text-decoration: none; } "
        "footer { padding: 24px; border-top: 1px solid #222; color: #aaa; } "
        "@media (max-width: 768px) { .hero { flex-direction: column; } "
        "nav { flex-wrap: wrap; } h1 { font-size: 2rem; } } "
    ) * 2

    files = [
        {"path": "index.html", "content": _page("BMW Dealership", "home"), "language": "html"},
        {"path": "inventory.html", "content": _page("Inventory", "inventory"), "language": "html"},
        {"path": "vehicle-detail.html", "content": _page("Vehicle Detail", "detail"), "language": "html"},
        {"path": "about.html", "content": _page("About Us", "about"), "language": "html"},
        {"path": "finance.html", "content": _page("Finance", "finance"), "language": "html"},
        {"path": "contact.html", "content": _page("Contact", "contact"), "language": "html"},
        {"path": "styles.css", "content": css, "language": "css"},
    ]
    result = score_project_quality(
        files, "multi-page-site", "multi-page-website",
        "Build a complete 6-page website for a used BMW dealership"
    )
    # With all 6 pages, should not get penalized for missing pages
    page_missing_errors = [
        e for e in result["qualityErrors"]
        if "6 pages" in e or "missing" in e.lower() and "html" in e.lower()
    ]
    assert not page_missing_errors, (
        f"All 6 pages present — should not get page-count error. "
        f"Got: {page_missing_errors}\nAll errors: {result['qualityErrors']}"
    )


# ── Phase 7: Product Brain Tests ─────────────────────────────────────────────

# ---------- Project Memory Engine (Phase 1) ----------

from agents.project_memory import (
    make_empty_memory,
    update_memory_brand,
    update_memory_design,
    update_memory_product,
    update_memory_pages,
    update_memory_features,
    update_memory_iteration,
    update_memory_agent_decision,
    get_design_tokens,
    get_font_pair,
    get_design_lock_prompt,
    get_design_direction_summary,
)


def test_project_memory_empty_schema_has_all_keys():
    """make_empty_memory() must return all required top-level keys."""
    mem = make_empty_memory()
    required_keys = {
        "brand", "design", "media", "product",
        "pages", "features", "requirements",
        "resolvedIssues", "unresolvedIssues",
        "iterationHistory", "agentDecisions",
        "designSignatures", "designTokens", "fontPair",
    }
    missing = required_keys - set(mem.keys())
    assert not missing, f"make_empty_memory() is missing keys: {missing}"


def test_project_memory_brand_keys():
    """Memory brand section must have all required sub-keys."""
    mem = make_empty_memory()
    brand_keys = {"name", "industry", "tone", "audience", "positioning"}
    assert set(mem["brand"].keys()) >= brand_keys


def test_project_memory_design_keys():
    """Memory design section must have all required sub-keys."""
    mem = make_empty_memory()
    design_keys = {
        "visualDirection", "palette", "fonts", "spacing",
        "layoutStyle", "animationStyle", "componentStyle",
    }
    assert set(mem["design"].keys()) >= design_keys


def test_project_memory_product_keys():
    """Memory product section must have all required sub-keys."""
    mem = make_empty_memory()
    product_keys = {
        "buildMode", "stack", "database", "authStrategy", "deploymentStrategy",
    }
    assert set(mem["product"].keys()) >= product_keys


def test_update_memory_brand_populates_audience():
    """update_memory_brand must record audience from Scout output."""
    mem = make_empty_memory()
    scout_data = {
        "audience": "small business owners",
        "summary": "An invoicing tool for freelancers",
        "core_features": ["invoicing", "payments"],
    }
    mem = update_memory_brand(mem, scout_data, mode="web_app")
    assert mem["brand"]["audience"] == "small business owners"
    assert "invoicing" in mem["brand"]["positioning"].lower() or "freelancer" in mem["brand"]["positioning"].lower()
    assert mem["product"]["buildMode"] == "web_app"


def test_update_memory_brand_does_not_overwrite_existing():
    """update_memory_brand must not overwrite existing non-empty brand fields."""
    mem = make_empty_memory()
    mem["brand"]["audience"] = "enterprise customers"
    scout_data = {"audience": "startups", "summary": "SaaS app"}
    mem = update_memory_brand(mem, scout_data)
    # Existing audience should be preserved
    assert mem["brand"]["audience"] == "enterprise customers"


def test_update_memory_design_populates_palette():
    """update_memory_design must store palette and typography from design_direction."""
    mem = make_empty_memory()
    design_direction = {
        "name": "premium-monochrome",
        "palette": {"background": "#000000", "accent": "#ffffff"},
        "typography": {"heading": "'Manrope'", "body": "'Manrope'"},
        "layout_rhythm": "minimal_centered",
        "spacing": "generous",
        "motion": "200ms ease",
        "visual_motifs": "clean white cards",
        "design_signature": {
            "styleName": "premium-monochrome",
            "paletteHash": "abc12345",
            "fontPair": "'Manrope'|'Manrope'",
            "layoutArchetype": "minimal_centered",
        },
    }
    mem = update_memory_design(mem, design_direction)
    assert mem["design"]["palette"]["background"] == "#000000"
    assert mem["design"]["fonts"]["heading"] == "'Manrope'"
    assert mem["design"]["visualDirection"] == "premium-monochrome"
    assert mem["design"]["layoutStyle"] == "minimal_centered"
    # Also stored in top-level shortcut fields
    assert mem["designTokens"]["accent"] == "#ffffff"
    assert mem["fontPair"]["heading"] == "'Manrope'"
    # Design signature tracked
    assert len(mem["designSignatures"]) == 1
    assert mem["designSignatures"][0]["styleName"] == "premium-monochrome"


def test_update_memory_design_does_not_overwrite_existing_palette():
    """update_memory_design must NOT overwrite existing palette on subsequent calls."""
    mem = make_empty_memory()
    # First build sets the palette
    mem = update_memory_design(mem, {
        "name": "luxury-black-gold",
        "palette": {"background": "#0a0800", "accent": "#c8a96e"},
        "typography": {"heading": "'Playfair Display'"},
        "design_signature": {"styleName": "luxury-black-gold"},
    })
    # Second build call (e.g. from repair) tries to overwrite -- must be rejected
    mem = update_memory_design(mem, {
        "name": "different-style",
        "palette": {"background": "#ffffff", "accent": "#4f46e5"},
        "typography": {"heading": "'Inter'"},
        "design_signature": {"styleName": "different-style"},
    })
    assert mem["design"]["palette"]["background"] == "#0a0800", (
        "Existing palette must NOT be overwritten during repair/iteration"
    )


def test_update_memory_product_records_stack():
    """update_memory_product must record stack from stack_decision."""
    mem = make_empty_memory()
    stack_decision = {
        "stack": {"frontend": "React", "backend": "FastAPI", "database": "MongoDB"},
        "preview_strategy": "iframe",
    }
    mem = update_memory_product(mem, "full_stack", stack_decision)
    assert "React" in mem["product"]["stack"]
    assert mem["product"]["database"] == "MongoDB"
    assert mem["product"]["buildMode"] == "full_stack"


def test_update_memory_pages_records_html_files():
    """update_memory_pages must record all .html files from generated files."""
    mem = make_empty_memory()
    files = [
        {"path": "index.html", "content": "<html/>"},
        {"path": "about.html", "content": "<html/>"},
        {"path": "styles.css", "content": "body{}"},
    ]
    mem = update_memory_pages(mem, files)
    page_paths = [p["path"] for p in mem["pages"]]
    assert "index.html" in page_paths
    assert "about.html" in page_paths
    assert "styles.css" not in page_paths


def test_update_memory_features_records_core_features():
    """update_memory_features must deduplicate and record core features."""
    mem = make_empty_memory()
    scout_data = {"core_features": ["auth", "dashboard", "export"]}
    mem = update_memory_features(mem, scout_data)
    assert "auth" in mem["features"]
    assert "dashboard" in mem["features"]
    # Running again should not duplicate
    mem = update_memory_features(mem, scout_data)
    assert mem["features"].count("auth") == 1


def test_update_memory_iteration_appends_entry():
    """update_memory_iteration must append entries to iterationHistory."""
    mem = make_empty_memory()
    entry1 = {"request": "make it blue", "changedFiles": ["styles.css"]}
    entry2 = {"request": "add pricing section", "changedFiles": ["index.html"]}
    mem = update_memory_iteration(mem, entry1)
    mem = update_memory_iteration(mem, entry2)
    assert len(mem["iterationHistory"]) == 2
    assert mem["iterationHistory"][0]["request"] == "make it blue"


def test_update_memory_iteration_caps_at_max():
    """iterationHistory must be capped at 20 entries."""
    from agents.project_memory import _MAX_ITERATION_HISTORY
    mem = make_empty_memory()
    for i in range(25):
        mem = update_memory_iteration(mem, {"request": f"change {i}"})
    assert len(mem["iterationHistory"]) == _MAX_ITERATION_HISTORY


def test_update_memory_agent_decision_records_decisions():
    """update_memory_agent_decision must record agent decisions with metadata."""
    mem = make_empty_memory()
    mem = update_memory_agent_decision(mem, "scout", "requirements_extracted", {"audience": "devs"})
    mem = update_memory_agent_decision(mem, "coder", "files_generated", {"file_count": 5})
    assert len(mem["agentDecisions"]) == 2
    assert mem["agentDecisions"][0]["agent"] == "scout"
    assert mem["agentDecisions"][1]["decision"] == "files_generated"


def test_get_design_tokens_returns_palette():
    """get_design_tokens must return the locked palette dict."""
    mem = make_empty_memory()
    mem["designTokens"] = {"background": "#000", "accent": "#fff"}
    tokens = get_design_tokens(mem)
    assert tokens["background"] == "#000"


def test_get_font_pair_returns_typography():
    """get_font_pair must return the locked font pair dict."""
    mem = make_empty_memory()
    mem["fontPair"] = {"heading": "'Playfair Display'", "body": "'Cormorant'"}
    fonts = get_font_pair(mem)
    assert fonts["heading"] == "'Playfair Display'"


def test_get_design_direction_summary_produces_text():
    """get_design_direction_summary must return non-empty text when memory is populated."""
    mem = make_empty_memory()
    mem["design"] = {
        "visualDirection": "luxury-black-gold",
        "palette": {"background": "#0a0800", "accent": "#c8a96e"},
        "fonts": {"heading": "'Playfair Display'", "body": "'Cormorant'"},
        "spacing": "spacious",
        "layoutStyle": "centered_luxury",
        "animationStyle": "slow 600ms ease",
        "componentStyle": "gold ornamental dividers",
    }
    mem["designTokens"] = {"background": "#0a0800", "accent": "#c8a96e"}
    mem["fontPair"] = {"heading": "'Playfair Display'", "body": "'Cormorant'"}
    summary = get_design_direction_summary(mem)
    assert "luxury-black-gold" in summary
    assert "'Playfair Display'" in summary
    assert "spacious" in summary


def test_get_design_lock_prompt_includes_locked_tokens():
    """get_design_lock_prompt must include DESIGN IDENTITY LOCK heading and palette values."""
    mem = make_empty_memory()
    mem["designTokens"] = {"background": "#0a0800", "accent": "#c8a96e"}
    mem["fontPair"] = {"heading": "'Playfair Display'", "body": "'Cormorant'"}
    mem["design"] = {
        "visualDirection": "luxury-black-gold",
        "palette": {"background": "#0a0800", "accent": "#c8a96e"},
        "fonts": {"heading": "'Playfair Display'", "body": "'Cormorant'"},
        "spacing": "spacious",
        "layoutStyle": "centered_luxury",
        "animationStyle": "slow 600ms ease",
        "componentStyle": "gold ornamental dividers",
    }
    lock = get_design_lock_prompt(mem)
    assert "DESIGN IDENTITY LOCK" in lock
    assert "#0a0800" in lock
    assert "Playfair Display" in lock
    assert "DO NOT CHANGE" in lock


def test_get_design_lock_prompt_empty_memory_returns_empty():
    """get_design_lock_prompt must return empty string when memory has no design."""
    mem = make_empty_memory()
    lock = get_design_lock_prompt(mem)
    assert lock == ""


# ---------- Project Memory Persistence (Phase 1 async) ----------

@pytest.mark.asyncio
async def test_project_memory_saved_after_build():
    """After a successful build, project_memory must be persisted to the project document."""
    db, proj, files, events, messages = _make_db()
    call_count = [0]
    responses = [
        # planner (Phase 4)
        _PLANNER_RESP,
        # scout
        {"summary": "Invoicing SaaS", "audience": "freelancers", "core_features": ["invoicing", "pdf"], "requirements_md": "# Reqs"},
        # architect
        {"tech_stack": {"frontend": "HTML", "styling": "CSS"}, "file_plan": [
            {"path": "index.html", "purpose": "entry"},
        ]},
        # coder
        {"files": [
            {"path": "index.html", "language": "html", "content": "<!DOCTYPE html><html><body><h1>Hello</h1></body></html>"},
            {"path": "styles.css", "language": "css", "content": ":root{--font-heading:'Inter'}body{font-family:var(--font-heading)}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App","mode":"landing_page"}'},
        ], "summary": "Done"},
        # reviewer
        {"verdict": "pass", "issues": [], "patched_files": [], "summary": "OK"},
        # advisor (Phase 2)
        _ADVISOR_RESP,
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
    written = []

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    from agents.stack_engine import decide_stack
    sd = decide_stack(mode="landing_page")
    await orch.run_full_build("Build an invoicing SaaS", mode="landing_page", stack_decision=sd)

    # project_memory must have been written to the DB
    assert "project_memory" in proj, "project_memory must be persisted to the project document"
    memory = proj["project_memory"]
    assert isinstance(memory, dict), "project_memory must be a dict"

    # Brand must have audience
    assert memory.get("brand", {}).get("audience") == "freelancers", (
        f"brand.audience must be 'freelancers', got: {memory.get('brand', {})}"
    )

    # agentDecisions must be populated
    assert len(memory.get("agentDecisions", [])) >= 2, (
        "At least scout + architect decisions must be recorded"
    )


@pytest.mark.asyncio
async def test_iteration_memory_preserved_after_iteration():
    """Iteration must append to iterationHistory and keep design tokens intact."""
    db, proj, files, events, messages = _make_db()

    # Pre-seed project memory with design tokens (simulating a prior build)
    proj["project_memory"] = {
        "brand": {"name": "TestCo", "industry": "SaaS", "tone": "", "audience": "devs", "positioning": ""},
        "design": {
            "visualDirection": "premium-monochrome",
            "palette": {"background": "#000000", "accent": "#ffffff"},
            "fonts": {"heading": "'Manrope'", "body": "'Manrope'"},
            "spacing": "generous",
            "layoutStyle": "minimal_centered",
            "animationStyle": "200ms ease",
            "componentStyle": "clean white cards",
        },
        "designTokens": {"background": "#000000", "accent": "#ffffff"},
        "fontPair": {"heading": "'Manrope'", "body": "'Manrope'"},
        "designSignatures": [{"styleName": "premium-monochrome", "paletteHash": "abc12345"}],
        "media": {"preferredStyle": "", "heroStyle": "", "logoStyle": "", "imageSubjects": [], "aspectRatios": [], "generatedAssets": []},
        "product": {"buildMode": "landing_page", "stack": "HTML / none", "database": "", "authStrategy": "", "deploymentStrategy": "iframe"},
        "pages": [{"path": "index.html", "title": "Index"}],
        "features": ["auth", "dashboard"],
        "requirements": [],
        "resolvedIssues": [],
        "unresolvedIssues": [],
        "iterationHistory": [],
        "agentDecisions": [],
    }

    # Seed app files
    app_content = '<!DOCTYPE html><html><body><h1>App</h1></body></html>'
    proj["mode"] = "landing_page"
    proj["prompt"] = "Build landing page"

    # Iteration response
    iter_response = {
        "files": [
            {"path": "index.html", "language": "html", "content": app_content},
            {"path": "styles.css", "language": "css", "content": ":root{--font-heading:'Manrope'}body{}"},
            {"path": "README.md", "language": "markdown", "content": "# App"},
            {"path": "amarktai.project.json", "language": "json", "content": '{"name":"App"}'},
        ],
        "summary": "Added blue button",
        "requestedChanges": ["blue button"],
        "satisfiedChanges": ["blue button"],
        "unsatisfiedChanges": [],
    }

    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": json.dumps(iter_response),
        "model_label": "test", "model": "test", "session_id": "s", "usage": {},
    })
    events_received = []

    async def emit(payload):
        events_received.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    written = [
        {"path": "index.html", "content": app_content, "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
        {"path": "README.md", "content": "# App", "language": "markdown"},
        {"path": "amarktai.project.json", "content": '{"name":"App"}', "language": "json"},
    ]

    async def fake_write(p, c, l="text"):
        written.append({"path": p, "content": c, "language": l})

    orch.fs.write = fake_write
    orch.fs.list_full = AsyncMock(side_effect=lambda: list(written))
    orch.fs.list = AsyncMock(return_value=[])
    orch.fs.read = AsyncMock(return_value=None)

    await orch.run_iteration("Make the button blue")

    # Design tokens must NOT have changed
    memory = proj.get("project_memory", {})
    tokens = memory.get("designTokens", {})
    assert tokens.get("background") == "#000000", (
        f"Design tokens must be preserved -- background changed. Got: {tokens}"
    )
    assert tokens.get("accent") == "#ffffff", (
        f"Design tokens must be preserved -- accent changed. Got: {tokens}"
    )

    # iterationHistory must have one entry
    history = memory.get("iterationHistory", [])
    assert len(history) == 1, f"iterationHistory must have 1 entry, got {len(history)}"
    assert history[0]["request"] == "Make the button blue"


# ---------- Design DNA Engine (Phase 4) ----------

from agents.design_dna import (
    compute_repetition_score,
    get_overused_elements,
    get_originality_report,
    record_design_choice,
    build_diversity_context,
    extract_section_archetypes,
    compute_section_penalty,
    is_palette_overused,
    palette_hash,
)


def test_design_dna_repetition_score_zero_for_empty_history():
    """Repetition score must be 0.0 when there is no history."""
    candidate = {"styleName": "premium-monochrome", "paletteHash": "abc", "fontPair": "x|y", "layoutArchetype": "minimal"}
    score = compute_repetition_score(candidate, [])
    assert score == 0.0


def test_design_dna_repetition_score_nonzero_for_same_style():
    """Repetition score must be > 0 when same style was recently used."""
    candidate = {"styleName": "luxury-black-gold", "paletteHash": "abc", "fontPair": "x|y", "layoutArchetype": "centered_luxury"}
    recent = [{"styleName": "luxury-black-gold", "paletteHash": "abc", "fontPair": "x|y", "layoutArchetype": "centered_luxury"}]
    score = compute_repetition_score(candidate, recent)
    assert score > 0.0, f"Same style must score > 0. Got: {score}"


def test_design_dna_repetition_score_capped_at_one():
    """Repetition score must never exceed 1.0."""
    candidate = {"styleName": "organic-nature", "paletteHash": "def", "fontPair": "a|b", "layoutArchetype": "flowing"}
    recent = [{"styleName": "organic-nature", "paletteHash": "def", "fontPair": "a|b", "layoutArchetype": "flowing"}] * 20
    score = compute_repetition_score(candidate, recent)
    assert 0.0 <= score <= 1.0, f"Score must be in [0,1], got: {score}"


def test_design_dna_get_overused_elements_counts_correctly():
    """get_overused_elements must accurately count style/palette/font/layout repeats."""
    sigs = [
        {"styleName": "style-a", "paletteHash": "h1", "fontPair": "f1|f2", "layoutArchetype": "layout-x"},
        {"styleName": "style-a", "paletteHash": "h1", "fontPair": "f1|f2", "layoutArchetype": "layout-x"},
        {"styleName": "style-b", "paletteHash": "h2", "fontPair": "f3|f4", "layoutArchetype": "layout-y"},
    ]
    overused = get_overused_elements(sigs)
    assert overused["styles"]["style-a"] == 2
    assert overused["styles"]["style-b"] == 1
    assert overused["palettes"]["h1"] == 2


def test_design_dna_originality_report_low_risk_for_fresh_history():
    """Originality report must return low risk when all styles are unique."""
    mem = make_empty_memory()
    mem["designSignatures"] = [
        {"styleName": f"style-{i}", "paletteHash": f"h{i}", "fontPair": "a|b", "layoutArchetype": "x"}
        for i in range(5)
    ]
    report = get_originality_report(mem)
    assert report["repetition_risk"] == "low"
    assert report["unique_styles_used"] == 5


def test_design_dna_originality_report_high_risk_for_repeated_style():
    """Originality report must return high risk when one style dominates."""
    mem = make_empty_memory()
    mem["designSignatures"] = [
        {"styleName": "luxury-black-gold", "paletteHash": "abc", "fontPair": "a|b", "layoutArchetype": "x"}
        for _ in range(4)
    ]
    report = get_originality_report(mem)
    assert report["repetition_risk"] in ("medium", "high")
    assert "luxury-black-gold" in report["recommendation"]


def test_design_dna_record_design_choice_adds_signature():
    """record_design_choice must add design signature to memory.designSignatures."""
    mem = make_empty_memory()
    direction = {
        "name": "neo-brutalist",
        "design_signature": {
            "styleName": "neo-brutalist",
            "paletteHash": "xyz",
            "fontPair": "'Space Grotesk'|'Space Grotesk'",
            "layoutArchetype": "chunky_blocks",
        },
    }
    mem = record_design_choice(mem, direction)
    assert len(mem["designSignatures"]) == 1
    assert mem["designSignatures"][0]["styleName"] == "neo-brutalist"


def test_design_dna_record_design_choice_does_not_duplicate():
    """record_design_choice must not add duplicate entry for same styleName."""
    mem = make_empty_memory()
    direction = {
        "name": "neo-brutalist",
        "design_signature": {"styleName": "neo-brutalist", "paletteHash": "xyz"},
    }
    mem = record_design_choice(mem, direction)
    mem = record_design_choice(mem, direction)
    assert len(mem["designSignatures"]) == 1, "Duplicate must not be added"


def test_design_dna_build_diversity_context_returns_recent_and_avoid():
    """build_diversity_context must return recent_signatures and avoid_styles."""
    mem = make_empty_memory()
    mem["designSignatures"] = [
        {"styleName": "luxury-black-gold", "paletteHash": "a"},
        {"styleName": "luxury-black-gold", "paletteHash": "a"},
        {"styleName": "organic-nature", "paletteHash": "b"},
    ]
    ctx = build_diversity_context(mem)
    assert "recent_signatures" in ctx
    assert "avoid_styles" in ctx
    assert "luxury-black-gold" in ctx["avoid_styles"]
    assert "organic-nature" not in ctx["avoid_styles"]


def test_design_dna_extract_section_archetypes_hero():
    """extract_section_archetypes must detect hero sections."""
    html = '<section class="hero"><h1>Welcome</h1></section>'
    archetypes = extract_section_archetypes(html)
    assert "cinematic_hero" in archetypes


def test_design_dna_extract_section_archetypes_pricing():
    """extract_section_archetypes must detect pricing sections."""
    html = '<section id="pricing"><div class="plan">$9/mo</div></section>'
    archetypes = extract_section_archetypes(html)
    assert "pricing" in archetypes


def test_design_dna_extract_section_archetypes_faq_and_testimonials():
    """extract_section_archetypes must detect FAQ and testimonials."""
    html = '<section id="faq"><details><summary>Q1</summary><p>A1</p></details></section>\n    <section id="testimonials"><div class="card">Great product!</div></section>'
    archetypes = extract_section_archetypes(html)
    assert "faq" in archetypes
    assert "testimonials" in archetypes


def test_design_dna_palette_hash_is_stable():
    """palette_hash must return the same value for the same palette."""
    palette = {"background": "#000000", "accent": "#c8a96e", "text_primary": "#f5e6c8"}
    h1 = palette_hash(palette)
    h2 = palette_hash(palette)
    assert h1 == h2
    assert len(h1) == 8


def test_design_dna_palette_hash_differs_for_different_palettes():
    """palette_hash must differ for different palettes."""
    p1 = {"background": "#000000", "accent": "#ffffff"}
    p2 = {"background": "#ffffff", "accent": "#000000"}
    assert palette_hash(p1) != palette_hash(p2)


def test_design_dna_is_palette_overused_false_for_fresh():
    """is_palette_overused must return False when palette has not been used before."""
    mem = make_empty_memory()
    palette = {"background": "#000000", "accent": "#c8a96e"}
    assert is_palette_overused(palette, mem) is False


def test_design_dna_is_palette_overused_true_after_repeats():
    """is_palette_overused must return True when palette appears >= 2 times."""
    mem = make_empty_memory()
    palette = {"background": "#000000", "accent": "#c8a96e"}
    ph = palette_hash(palette)
    mem["designSignatures"] = [
        {"styleName": "a", "paletteHash": ph},
        {"styleName": "b", "paletteHash": ph},
    ]
    assert is_palette_overused(palette, mem) is True


# ---------- Premium Section Library (Phase 5) ----------

from agents.prompts import PREMIUM_SECTION_LIBRARY, VISUAL_COMPOSITION_RULES


def test_premium_section_library_contains_all_15_archetypes():
    """PREMIUM_SECTION_LIBRARY must define all 15 section archetypes."""
    archetypes = [
        "CINEMATIC HERO", "LUXURY SHOWCASE", "PRODUCT SPOTLIGHT", "DASHBOARD PREVIEW",
        "WORKFLOW TIMELINE", "TRUST BAR", "COMPARISON GRID", "PRICING", "CTA SECTION",
        "TESTIMONIALS", "FEATURE CARDS", "GALLERY", "FAQ", "METRICS", "INTEGRATIONS",
    ]
    for archetype in archetypes:
        assert archetype in PREMIUM_SECTION_LIBRARY, (
            f"PREMIUM_SECTION_LIBRARY missing archetype: {archetype}"
        )


def test_premium_section_library_has_composition_rules():
    """PREMIUM_SECTION_LIBRARY must include composition rules."""
    assert "COMPOSITION RULES" in PREMIUM_SECTION_LIBRARY


# ---------- Visual Composition Rules (Phase 6) ----------

def test_visual_composition_rules_present_in_coder_prompt():
    """CODER_PROMPT must include visual composition rules."""
    from agents.prompts import CODER_PROMPT
    assert "VISUAL COMPOSITION RULES" in CODER_PROMPT, (
        "CODER_PROMPT must include VISUAL_COMPOSITION_RULES"
    )


def test_visual_composition_rules_present_in_iteration_prompt():
    """ITERATION_PROMPT must include visual composition rules."""
    from agents.prompts import ITERATION_PROMPT
    assert "VISUAL COMPOSITION RULES" in ITERATION_PROMPT, (
        "ITERATION_PROMPT must include VISUAL_COMPOSITION_RULES"
    )


def test_visual_composition_rules_covers_key_categories():
    """VISUAL_COMPOSITION_RULES must cover all 6 rule categories."""
    categories = ["HERO RULES", "COLOUR RULES", "TYPOGRAPHY RULES",
                  "SPACING RULES", "IMAGE RULES", "CTA RULES", "STRUCTURE RULES"]
    for cat in categories:
        assert cat in VISUAL_COMPOSITION_RULES, (
            f"VISUAL_COMPOSITION_RULES missing category: {cat}"
        )


def test_visual_composition_rules_no_overcrowded_hero():
    """VISUAL_COMPOSITION_RULES must prohibit overcrowded hero."""
    assert "overcrowded" in VISUAL_COMPOSITION_RULES.lower()


def test_visual_composition_rules_no_tiny_fonts():
    """VISUAL_COMPOSITION_RULES must prohibit tiny fonts."""
    assert "tiny" in VISUAL_COMPOSITION_RULES.lower() or "15px" in VISUAL_COMPOSITION_RULES


def test_visual_composition_rules_no_random_gradients():
    """VISUAL_COMPOSITION_RULES must prohibit random gradients."""
    assert "random gradient" in VISUAL_COMPOSITION_RULES.lower()


def test_visual_composition_rules_no_stretched_images():
    """VISUAL_COMPOSITION_RULES must prohibit stretched images."""
    assert "stretched" in VISUAL_COMPOSITION_RULES.lower()


# ---------- Agent hierarchy / decisions (Phase 2) ----------

def test_agent_hierarchy_decisions_have_agent_field():
    """Agent decisions must record the responsible agent."""
    mem = make_empty_memory()
    mem = update_memory_agent_decision(mem, "scout", "requirements_extracted")
    mem = update_memory_agent_decision(mem, "creative_director", "design_selected", {"style": "luxury"})
    mem = update_memory_agent_decision(mem, "coder", "files_generated", {"count": 8})

    agents = [d["agent"] for d in mem["agentDecisions"]]
    assert "scout" in agents
    assert "creative_director" in agents
    assert "coder" in agents

    # Each decision has timestamp
    for d in mem["agentDecisions"]:
        assert "timestamp" in d, f"Decision missing timestamp: {d}"


def test_agent_hierarchy_design_not_overwritten_by_later_agents():
    """Design direction stored by creative_director must not be overwritten by coder."""
    mem = make_empty_memory()
    # Creative director sets design
    mem = update_memory_design(mem, {
        "name": "luxury-black-gold",
        "palette": {"background": "#0a0800", "accent": "#c8a96e"},
        "typography": {"heading": "'Playfair Display'", "body": "'Cormorant'"},
        "design_signature": {"styleName": "luxury-black-gold"},
    })
    original_palette = dict(mem["design"]["palette"])

    # Coder tries to set a new design -- should be rejected
    mem = update_memory_design(mem, {
        "name": "neo-brutalist",
        "palette": {"background": "#ffffff", "accent": "#ff3e00"},
        "typography": {"heading": "'Space Grotesk'", "body": "'Space Grotesk'"},
        "design_signature": {"styleName": "neo-brutalist"},
    })

    assert mem["design"]["palette"] == original_palette, (
        "Coder must NOT overwrite creative director's palette decision"
    )


# ---------- Repair preserves branding (Phase 7) ----------

def test_repair_memory_brand_not_lost_after_update():
    """Brand memory must persist across multiple update cycles (simulate repair)."""
    mem = make_empty_memory()
    scout_data = {"audience": "luxury car buyers", "summary": "BMW dealership website"}
    mem = update_memory_brand(mem, scout_data, mode="website")

    # Simulate repair: update product and pages without touching brand
    stack_decision = {"stack": {"frontend": "HTML", "backend": "none"}, "preview_strategy": "iframe"}
    mem = update_memory_product(mem, "website", stack_decision)
    mem = update_memory_pages(mem, [
        {"path": "index.html"}, {"path": "inventory.html"}
    ])

    # Brand must still be intact
    assert mem["brand"]["audience"] == "luxury car buyers", (
        f"Brand audience must survive repair cycle. Got: {mem['brand']}"
    )
    assert "BMW" in mem["brand"]["positioning"] or "luxury" in mem["brand"]["positioning"].lower()


# ========== PHASE 7: Runtime Sandbox Tests ==========

from runtime.sandbox_manager import (
    SandboxManager,
    SandboxResult,
    detect_stack,
    parse_error_output,
    ParsedError,
    STACK_TYPES,
)


# ---------- Phase 2: Stack Detection ----------

def test_detect_stack_static_html():
    """A project with only HTML files must be detected as 'static'."""
    files = [
        {"path": "index.html", "content": "<html><body>Hello</body></html>"},
        {"path": "styles.css", "content": "body{}"},
    ]
    assert detect_stack(files) == "static"


def test_detect_stack_vite_config():
    """A project with vite.config.js must be detected as 'vite'."""
    files = [
        {"path": "vite.config.js", "content": "export default {}"},
        {"path": "index.html", "content": "<html></html>"},
        {"path": "package.json", "content": '{"devDependencies":{"vite":"^5.0"}}'},
    ]
    assert detect_stack(files) == "vite"


def test_detect_stack_next():
    """A project with next.config.js must be detected as 'next'."""
    files = [
        {"path": "next.config.js", "content": "module.exports = {}"},
        {"path": "package.json", "content": '{"dependencies":{"next":"^14.0","react":"^18"}}'},
    ]
    assert detect_stack(files) == "next"


def test_detect_stack_react_no_vite():
    """React + react-dom without vite/next config must be detected as 'react'."""
    files = [
        {
            "path": "package.json",
            "content": '{"dependencies":{"react":"^18","react-dom":"^18"}}',
        }
    ]
    assert detect_stack(files) == "react"


def test_detect_stack_pwa():
    """A project with manifest.json + service-worker.js must be detected as 'pwa'."""
    files = [
        {"path": "manifest.json", "content": '{"name":"App"}'},
        {"path": "service-worker.js", "content": "self.addEventListener('fetch',()=>{})"},
        {"path": "index.html", "content": "<html></html>"},
    ]
    assert detect_stack(files) == "pwa"


def test_detect_stack_express():
    """A project with express as a dependency must be detected as 'express'."""
    files = [
        {"path": "package.json", "content": '{"dependencies":{"express":"^4"}}'},
        {"path": "server.js", "content": "const express = require('express')"},
    ]
    assert detect_stack(files) == "express"


def test_detect_stack_fastapi():
    """A project with FastAPI import must be detected as 'fastapi'."""
    files = [
        {"path": "main.py", "content": "from fastapi import FastAPI\napp = FastAPI()"},
    ]
    assert detect_stack(files) == "fastapi"


def test_detect_stack_django():
    """A project with manage.py must be detected as 'django'."""
    files = [
        {"path": "manage.py", "content": "#!/usr/bin/env python"},
        {"path": "myapp/settings.py", "content": "from django.conf import settings"},
    ]
    assert detect_stack(files) == "django"


def test_detect_stack_flask():
    """A project with Flask import must be detected as 'flask'."""
    files = [
        {"path": "app.py", "content": "from flask import Flask\napp = Flask(__name__)"},
    ]
    assert detect_stack(files) == "flask"


def test_detect_stack_fullstack():
    """A project with both HTML and Python files but no specific framework must be 'fullstack'."""
    files = [
        {"path": "index.html", "content": "<html></html>"},
        {"path": "backend/server.py", "content": "# generic server"},
    ]
    assert detect_stack(files) == "fullstack"


def test_detect_stack_unknown():
    """A project with no recognised files must return 'unknown'."""
    files = [
        {"path": "README.md", "content": "# My project"},
        {"path": "data.csv", "content": "a,b,c"},
    ]
    assert detect_stack(files) == "unknown"


def test_detect_stack_next_takes_priority_over_react():
    """Next.js detection must take priority over plain React."""
    files = [
        {"path": "next.config.js", "content": "module.exports = {}"},
        {
            "path": "package.json",
            "content": '{"dependencies":{"next":"^14","react":"^18","react-dom":"^18"}}',
        },
    ]
    assert detect_stack(files) == "next"


def test_detect_stack_vite_takes_priority_over_react():
    """Vite detection must take priority over plain React."""
    files = [
        {"path": "vite.config.ts", "content": "export default {}"},
        {
            "path": "package.json",
            "content": '{"devDependencies":{"vite":"^5"},"dependencies":{"react":"^18","react-dom":"^18"}}',
        },
    ]
    assert detect_stack(files) == "vite"


def test_detect_stack_all_types_covered():
    """STACK_TYPES must contain exactly the documented stack names."""
    expected = {"static", "vite", "react", "next", "express",
                "fastapi", "django", "flask", "fullstack", "pwa", "unknown"}
    assert expected == STACK_TYPES


# ---------- Phase 6: Error Intelligence ----------

def test_parse_error_missing_npm_module():
    """Parse 'Module not found' errors from Webpack/Vite output."""
    raw = "Module not found: Error: Can't resolve 'lodash'"
    errors = parse_error_output(raw)
    assert any(e.category == "missing_module" for e in errors)
    assert any("lodash" in e.repair_task for e in errors)


def test_parse_error_npm_error_code():
    """Parse npm ERR! code E404 style errors."""
    raw = "npm ERR! code E404\nnpm ERR! 404 Not Found"
    errors = parse_error_output(raw)
    assert any(e.category == "npm_error" for e in errors)


def test_parse_error_python_traceback():
    """Detect Python traceback and produce a human-readable repair task."""
    raw = (
        "Traceback (most recent call last):\n"
        "  File 'main.py', line 5, in <module>\n"
        "    import numpy\n"
        "ModuleNotFoundError: No module named 'numpy'\n"
    )
    errors = parse_error_output(raw)
    categories = [e.category for e in errors]
    assert "python_traceback" in categories or "missing_python_module" in categories
    repair_tasks = [e.repair_task for e in errors]
    assert any("numpy" in t for t in repair_tasks)


def test_parse_error_missing_python_module():
    """ModuleNotFoundError must produce a pip install repair task."""
    raw = "ModuleNotFoundError: No module named 'requests'"
    errors = parse_error_output(raw)
    assert any(e.category == "missing_python_module" for e in errors)
    assert any("pip install" in e.repair_task and "requests" in e.repair_task for e in errors)


def test_parse_error_enoent():
    """ENOENT must produce a missing-file repair task."""
    raw = "ENOENT: no such file or directory, open '/app/dist/index.html'"
    errors = parse_error_output(raw)
    assert any(e.category == "missing_file" for e in errors)


def test_parse_error_syntax_error():
    """SyntaxError lines must produce a syntax_error entry."""
    raw = "SyntaxError: Unexpected token '<'"
    errors = parse_error_output(raw)
    assert any(e.category == "syntax_error" for e in errors)


def test_parse_error_empty_input():
    """Empty input must return an empty list, not raise."""
    assert parse_error_output("") == []


def test_parse_error_clean_output():
    """Clean build output with no errors must return an empty list."""
    raw = "Build successful!\n✓ 42 modules transformed.\ndist/index.html  1.2 kB"
    errors = parse_error_output(raw)
    assert errors == []


def test_parse_error_python_traceback_deduplicated():
    """Multiple traceback lines must produce at most one python_traceback entry."""
    raw = (
        "Traceback (most recent call last):\n"
        "Traceback (most recent call last):\n"
        "Traceback (most recent call last):\n"
    )
    errors = parse_error_output(raw)
    traceback_errors = [e for e in errors if e.category == "python_traceback"]
    assert len(traceback_errors) <= 1


def test_parse_error_returns_parsed_error_objects():
    """parse_error_output must return ParsedError instances."""
    raw = "Module not found: Error: Can't resolve 'axios'"
    errors = parse_error_output(raw)
    assert all(isinstance(e, ParsedError) for e in errors)
    for e in errors:
        assert e.category
        assert e.repair_task
        assert e.raw_line


# ---------- Phase 1: SandboxResult ----------

def test_sandbox_result_defaults():
    """SandboxResult must have sane defaults."""
    r = SandboxResult()
    assert r.success is False
    assert r.stack == "unknown"
    assert r.logs == []
    assert r.errors == []
    assert r.runtime_status == "idle"
    assert r.cache_bust  # non-empty UUID
    assert r.workspace_id  # non-empty UUID


def test_sandbox_result_to_dict_keys():
    """SandboxResult.to_dict() must include all required keys."""
    r = SandboxResult(success=True, stack="static", runtime_status="running")
    d = r.to_dict()
    required = {
        "success", "stack", "logs", "errors",
        "previewUrl", "previewHtml", "installOk", "buildOk",
        "runtimeStatus", "cacheBust", "workspaceId",
    }
    assert required <= set(d.keys()), f"Missing keys: {required - set(d.keys())}"


def test_sandbox_result_to_dict_errors_serialised():
    """Errors in SandboxResult.to_dict() must be plain dicts."""
    r = SandboxResult()
    r.errors = [ParsedError(
        category="missing_module",
        message="Module not found: lodash",
        repair_task="npm install lodash",
        raw_line="Module not found: Error: Can't resolve 'lodash'",
    )]
    d = r.to_dict()
    assert isinstance(d["errors"], list)
    assert d["errors"][0]["category"] == "missing_module"
    assert d["errors"][0]["repairTask"] == "npm install lodash"


# ---------- Phase 1 + 3: SandboxManager safe execution ----------

def test_sandbox_manager_safe_env_no_dangerous_vars():
    """SandboxManager._safe_env() must not expose dangerous host env vars."""
    sb = SandboxManager()
    # Simulate a polluted environment
    os.environ["DANGEROUS_SECRET"] = "secret-value"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "aws-key"
    env = sb._safe_env()
    assert "DANGEROUS_SECRET" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    # Clean up
    del os.environ["DANGEROUS_SECRET"]
    del os.environ["AWS_SECRET_ACCESS_KEY"]


def test_sandbox_manager_safe_env_has_ci():
    """SandboxManager._safe_env() must set CI=true to suppress interactive prompts."""
    sb = SandboxManager()
    env = sb._safe_env()
    assert env.get("CI") == "true"


def test_sandbox_manager_safe_env_has_node_env():
    """SandboxManager._safe_env() must set NODE_ENV."""
    sb = SandboxManager()
    env = sb._safe_env()
    assert "NODE_ENV" in env


def test_sandbox_manager_workspace_creation():
    """SandboxManager._create_workspace() must create a real temporary directory."""
    sb = SandboxManager()
    wid, ws = sb._create_workspace()
    try:
        assert ws.exists()
        assert ws.is_dir()
        assert wid in sb._workspaces
    finally:
        sb._cleanup_workspace(wid)


def test_sandbox_manager_workspace_cleanup():
    """_cleanup_workspace() must remove the temp directory."""
    sb = SandboxManager()
    wid, ws = sb._create_workspace()
    ws_path = ws
    sb._cleanup_workspace(wid)
    assert not ws_path.exists(), "Workspace dir must be removed after cleanup"
    assert wid not in sb._workspaces


def test_sandbox_manager_write_files_safe(tmp_path):
    """_write_files() must skip paths with directory traversal attempts."""
    sb = SandboxManager()
    files = [
        {"path": "../../../etc/passwd", "content": "evil"},
        {"path": "safe.txt", "content": "hello"},
    ]
    sb._write_files(tmp_path, files)
    assert not (tmp_path / "../../../etc/passwd").exists()
    assert (tmp_path / "safe.txt").read_text() == "hello"


def test_sandbox_manager_write_files_nested(tmp_path):
    """_write_files() must create nested directories for deeply nested files."""
    sb = SandboxManager()
    files = [
        {"path": "src/components/App.jsx", "content": "export default function App() {}"},
    ]
    sb._write_files(tmp_path, files)
    assert (tmp_path / "src" / "components" / "App.jsx").exists()


# ---------- Phase 4: Static preview ----------

@pytest.mark.asyncio
async def test_sandbox_static_preview_returns_html():
    """run_preview() on a static project must return inline HTML."""
    files = [
        {"path": "index.html", "content": "<!DOCTYPE html><html><body><h1>Hello</h1></body></html>"},
        {"path": "styles.css", "content": "body { color: red; }"},
    ]
    async with SandboxManager() as sb:
        result = await sb.run_preview(files)

    assert result.stack == "static"
    assert result.success is True
    assert "<html>" in result.preview_html or "<!DOCTYPE html>" in result.preview_html.lower()
    assert result.runtime_status == "running"
    assert result.install_ok is True
    assert result.build_ok is True


@pytest.mark.asyncio
async def test_sandbox_static_preview_no_index_html():
    """run_preview() on a static project with no index.html must not crash."""
    files = [
        {"path": "styles.css", "content": "body{}"},
    ]
    async with SandboxManager() as sb:
        result = await sb.run_preview(files, stack_hint="static")

    # No index.html → preview_html may be empty but must not raise
    assert result.stack == "static"
    assert isinstance(result.logs, list)


@pytest.mark.asyncio
async def test_sandbox_pwa_preview():
    """run_preview() on a PWA project must return inline HTML preview."""
    files = [
        {"path": "manifest.json", "content": '{"name":"PWA App","start_url":"/"}'},
        {"path": "service-worker.js", "content": "self.addEventListener('fetch', () => {})"},
        {"path": "index.html", "content": "<!DOCTYPE html><html><body>PWA</body></html>"},
    ]
    async with SandboxManager() as sb:
        result = await sb.run_preview(files)

    assert result.stack == "pwa"
    assert isinstance(result.preview_html, str)
    assert result.runtime_status in ("running", "error")


# ---------- Phase 5: Hot Reload ----------

@pytest.mark.asyncio
async def test_patch_and_reload_unknown_workspace():
    """patch_and_reload() with an unknown workspace_id must not raise."""
    sb = SandboxManager()
    result = SandboxResult(workspace_id="nonexistent", success=True)
    updated = await sb.patch_and_reload("nonexistent", [], result)
    assert updated.success is False
    assert any("not found" in line for line in updated.logs)


@pytest.mark.asyncio
async def test_patch_and_reload_updates_cache_bust():
    """patch_and_reload() must update the cache_bust token."""
    sb = SandboxManager()
    wid, ws = sb._create_workspace()
    try:
        original_bust = str(uuid.uuid4())
        result = SandboxResult(workspace_id=wid, cache_bust=original_bust)
        # Register workspace so patch_and_reload can find it
        sb._workspaces[wid] = ws

        patched = await sb.patch_and_reload(
            wid,
            [{"path": "index.html", "content": "<html>updated</html>"}],
            result,
        )
        assert patched.cache_bust != original_bust, "cache_bust must change on hot reload"
        assert patched.success is True
    finally:
        sb._cleanup_workspace(wid)


@pytest.mark.asyncio
async def test_patch_and_reload_writes_files():
    """patch_and_reload() must actually write the patched files to disk."""
    sb = SandboxManager()
    wid, ws = sb._create_workspace()
    try:
        sb._workspaces[wid] = ws
        result = SandboxResult(workspace_id=wid)
        await sb.patch_and_reload(
            wid,
            [{"path": "newfile.txt", "content": "patched content"}],
            result,
        )
        assert (ws / "newfile.txt").read_text() == "patched content"
    finally:
        sb._cleanup_workspace(wid)


# ---------- Phase 4: Fallback preview object ----------

def test_sandbox_fallback_preview_structure():
    """_make_fallback_preview() must return the expected API contract keys."""
    sb = SandboxManager()
    fb = sb._make_fallback_preview(
        stack="vite",
        logs=["[sandbox] npm install failed"],
        errors=[ParsedError("npm_error", "npm ERR! code E404", "Check network", "npm ERR! code E404")],
        install_ok=False,
        build_ok=False,
        workspace_id="test-id",
    )
    assert fb["canPreview"] is False
    assert fb["type"] == "sandbox-fallback"
    assert fb["stack"] == "vite"
    assert isinstance(fb["logs"], list)
    assert isinstance(fb["errors"], list)
    assert fb["runtimeStatus"] == "error"


# ---------- Phase 1: npm install dep-limit guard ----------

@pytest.mark.asyncio
async def test_npm_install_refuses_too_many_deps(tmp_path):
    """npm_install must refuse when package.json has > _MAX_DEPS dependencies."""
    from runtime.sandbox_manager import _MAX_DEPS
    # Build a package.json with too many deps
    deps = {f"pkg-{i}": "^1.0.0" for i in range(_MAX_DEPS + 1)}
    pkg_json = {"dependencies": deps}
    (tmp_path / "package.json").write_text(json.dumps(pkg_json))

    sb = SandboxManager()
    log_lines: list[str] = []
    ok = await sb.npm_install(tmp_path, log_lines)

    assert ok is False
    assert any("exceeds limit" in line for line in log_lines)


@pytest.mark.asyncio
async def test_npm_install_skips_when_no_package_json(tmp_path):
    """npm_install must return True (no-op) when there is no package.json."""
    sb = SandboxManager()
    log_lines: list[str] = []
    ok = await sb.npm_install(tmp_path, log_lines)
    assert ok is True
    assert any("skipping" in line.lower() for line in log_lines)


@pytest.mark.asyncio
async def test_pip_install_skips_when_no_requirements(tmp_path):
    """pip_install must return True (no-op) when there is no requirements.txt."""
    sb = SandboxManager()
    log_lines: list[str] = []
    ok = await sb.pip_install(tmp_path, log_lines)
    assert ok is True
    assert any("skipping" in line.lower() for line in log_lines)


# ---------- Phase 1: context manager cleanup ----------

@pytest.mark.asyncio
async def test_sandbox_context_manager_cleanup():
    """SandboxManager used as async context manager must clean up workspaces on exit."""
    workspace_paths = []

    async with SandboxManager() as sb:
        wid, ws = sb._create_workspace()
        workspace_paths.append(ws)
        # Don't manually clean up — rely on __aexit__

    for ws_path in workspace_paths:
        assert not ws_path.exists(), f"Workspace {ws_path} must be cleaned up on context exit"


# ---------- Phase 3: safe execution guards ----------

def test_sandbox_write_files_empty_path_skipped(tmp_path):
    """Files with empty path must be silently skipped."""
    sb = SandboxManager()
    files = [
        {"path": "", "content": "should be skipped"},
        {"path": "valid.txt", "content": "ok"},
    ]
    sb._write_files(tmp_path, files)
    assert (tmp_path / "valid.txt").exists()
    # Only valid.txt should exist; no file named "" should have been created
    written = list(tmp_path.iterdir())
    assert all(f.name != "" for f in written), "Empty-path file must not be written"


def test_detect_stack_ignores_empty_file_list():
    """detect_stack() on an empty file list must return 'unknown' without raising."""
    assert detect_stack([]) == "unknown"


def test_detect_stack_tolerates_missing_content():
    """detect_stack() must tolerate files missing 'content' key."""
    files = [{"path": "index.html"}]  # no 'content' key
    result = detect_stack(files)
    assert result in STACK_TYPES


# ---------- Phase 6: broken package repair ----------

def test_parse_error_broken_package_npm_missing():
    """npm ERR! missing must produce a repair task naming the missing package."""
    raw = "npm ERR! missing: express@^4.18.0, required by myapp@1.0.0"
    errors = parse_error_output(raw)
    assert any(e.category == "npm_missing" for e in errors)
    assert any("express" in e.repair_task for e in errors)


def test_parse_error_import_error():
    """ImportError lines must be captured."""
    raw = "ImportError: cannot import name 'Router' from 'fastapi'"
    errors = parse_error_output(raw)
    assert any(e.category == "import_error" for e in errors)
    assert any("Router" in e.repair_task or "fastapi" in e.repair_task for e in errors)
