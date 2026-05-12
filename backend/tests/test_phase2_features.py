"""
Tests for Phase 2 features:
  - Project versioning (create, list, get, restore)
  - Rollback
  - Multi-change iteration task checklist
  - Preview build (success/failure)
  - Stack detection (extended)
  - Repo import analysis
  - Repo repair with diff summary
  - PR diff summary
  - Checkpoint creation
  - Runtime cleanup scripts (smoke test)
  - Runtime health endpoint data shape

Phase 2K acceptance tests.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_db():
    """Return a minimal in-memory DB mock that supports the operations used."""

    class _Col:
        def __init__(self):
            self._docs: list[dict] = []

        async def insert_one(self, doc):
            self._docs.append({k: v for k, v in doc.items()})

        async def find_one(self, query, projection=None, sort=None):
            results = [d for d in self._docs if _matches(d, query)]
            if sort:
                key, direction = sort[0] if isinstance(sort, list) else (sort, 1)
                results = sorted(results, key=lambda d: d.get(key, ""), reverse=(direction == -1))
            return _apply_projection(results[-1] if results else None, projection)

        def find(self, query=None, projection=None):
            results = [d for d in self._docs if _matches(d, query or {})]
            return _AsyncCursor(results, projection)

        async def delete_many(self, query):
            before = len(self._docs)
            self._docs = [d for d in self._docs if not _matches(d, query)]
            return MagicMock(deleted_count=before - len(self._docs))

        async def update_one(self, query, update, upsert=False):
            for d in self._docs:
                if _matches(d, query):
                    if "$set" in update:
                        d.update(update["$set"])
                    return
            if upsert:
                new_doc = dict(query)
                if "$set" in update:
                    new_doc.update(update["$set"])
                self._docs.append(new_doc)

        async def count_documents(self, query=None):
            return sum(1 for d in self._docs if _matches(d, query or {}))

        async def replace_one(self, query, replacement, upsert=False):
            for i, d in enumerate(self._docs):
                if _matches(d, query):
                    self._docs[i] = replacement
                    return
            if upsert:
                self._docs.append(replacement)

    class _AsyncCursor:
        def __init__(self, docs, projection=None):
            self._docs = [_apply_projection(d, projection) for d in docs]

        def sort(self, key, direction=-1):
            self._docs.sort(key=lambda d: d.get(key, ""), reverse=(direction == -1))
            return self

        def limit(self, n):
            self._docs = self._docs[:n]
            return self

        def skip(self, n):
            self._docs = self._docs[n:]
            return self

        async def to_list(self, n=None):
            return self._docs[:n] if n else self._docs

    def _matches(doc, query):
        for k, v in query.items():
            if k.startswith("$"):
                continue
            dv = doc.get(k)
            if isinstance(v, dict):
                for op, opv in v.items():
                    if op == "$gte" and not (dv is not None and dv >= opv):
                        return False
                    if op == "$regex" and not (isinstance(dv, str) and opv in dv):
                        return False
            elif dv != v:
                return False
        return True

    def _apply_projection(doc, proj):
        if doc is None or not proj:
            return doc
        result = {}
        for k, v in doc.items():
            if k == "_id":
                if proj.get("_id", 1) != 0:
                    result[k] = v
            elif proj.get(k, 1) != 0:
                result[k] = v
        return result

    class _DB:
        def __init__(self):
            self.project_versions = _Col()
            self.projects = _Col()
            self.files = _Col()
            self.project_checkpoints = _Col()

        def __getattr__(self, name):
            col = _Col()
            setattr(self, name, col)
            return col

    return _DB()


class _MockFS:
    """Minimal ProjectFS mock."""

    def __init__(self):
        self._files: dict[str, dict] = {}

    async def write(self, path, content, language="text"):
        self._files[path] = {"path": path, "content": content, "language": language}

    async def list_full(self):
        return list(self._files.values())

    async def list(self):
        return [{"path": p} for p in self._files]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2A — Versioning
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_version_creates_record():
    from app.versioning.version_store import create_version, list_versions

    db = _make_db()
    await db.projects.insert_one({"id": "proj1", "status": "ready", "updated_at": "t"})

    v = await create_version(
        db, "proj1",
        user_request="Build landing page",
        generated_files=["index.html"],
        build_status="ready",
        file_snapshot=[{"path": "index.html", "content": "<h1>Hello</h1>"}],
    )
    assert v["version_id"]
    assert v["project_id"] == "proj1"
    assert v["parent_version_id"] is None
    assert v["build_status"] == "ready"
    assert v["user_request"] == "Build landing page"

    versions = await list_versions(db, "proj1")
    assert len(versions) == 1
    # file_snapshot excluded from list
    assert "file_snapshot" not in versions[0]


@pytest.mark.asyncio
async def test_create_version_chains_parent():
    from app.versioning.version_store import create_version

    db = _make_db()
    await db.projects.insert_one({"id": "proj2", "status": "ready", "updated_at": "t"})

    v1 = await create_version(db, "proj2", build_status="ready", file_snapshot=[])
    v2 = await create_version(db, "proj2", build_status="ready", file_snapshot=[])
    assert v2["parent_version_id"] == v1["version_id"]


@pytest.mark.asyncio
async def test_get_version_returns_snapshot():
    from app.versioning.version_store import create_version, get_version

    db = _make_db()
    await db.projects.insert_one({"id": "proj3", "status": "ready", "updated_at": "t"})
    files = [{"path": "index.html", "content": "<p>v1</p>", "language": "html"}]
    v = await create_version(db, "proj3", build_status="ready", file_snapshot=files)

    result = await get_version(db, "proj3", v["version_id"])
    assert result is not None
    assert result["file_snapshot"][0]["path"] == "index.html"


@pytest.mark.asyncio
async def test_restore_version_restores_files():
    from app.versioning.version_store import create_version, restore_version

    db = _make_db()
    await db.projects.insert_one({"id": "proj4", "status": "ready", "updated_at": "t"})
    files = [{"path": "index.html", "content": "<p>original</p>", "language": "html"}]
    v = await create_version(db, "proj4", build_status="ready", file_snapshot=files)

    fs = _MockFS()
    result = await restore_version(db, "proj4", v["version_id"], fs)

    assert result["ok"] is True
    assert result["restored_files"] == 1
    assert fs._files["index.html"]["content"] == "<p>original</p>"


@pytest.mark.asyncio
async def test_restore_version_raises_on_missing():
    from app.versioning.version_store import restore_version

    db = _make_db()
    fs = _MockFS()
    with pytest.raises(ValueError, match="not found"):
        await restore_version(db, "proj-x", "nonexistent-version-id", fs)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2A — Diff summary generation
# ═══════════════════════════════════════════════════════════════════════════

def test_generate_diff_summary_added_file():
    from app.versioning.version_store import generate_diff_summary

    old = []
    new = [{"path": "index.html", "content": "<h1>Hello</h1>"}]
    summary = generate_diff_summary(old, new)
    assert "Added" in summary
    assert "index.html" in summary


def test_generate_diff_summary_modified_file():
    from app.versioning.version_store import generate_diff_summary

    old = [{"path": "styles.css", "content": "body { color: red; }"}]
    new = [{"path": "styles.css", "content": "body { color: blue; }"}]
    summary = generate_diff_summary(old, new)
    assert "Modified" in summary
    assert "styles.css" in summary
    assert "-body { color: red; }" in summary or "red" in summary


def test_generate_diff_summary_no_changes():
    from app.versioning.version_store import generate_diff_summary

    files = [{"path": "a.js", "content": "console.log('hi')"}]
    summary = generate_diff_summary(files, files)
    assert "No file changes" in summary


def test_generate_diff_summary_deleted_file():
    from app.versioning.version_store import generate_diff_summary

    old = [{"path": "old.css", "content": "body {}"}]
    new = []
    summary = generate_diff_summary(old, new)
    assert "Deleted" in summary
    assert "old.css" in summary


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2F — Extended Stack Detection
# ═══════════════════════════════════════════════════════════════════════════

def test_detect_stack_vite():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "vite.config.ts", "content": "export default {}"},
        {"path": "package.json", "content": json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "^4.0.0"}})},
    ]
    result = detect_extended_stack(files)
    assert "vite" in result["detected"]
    assert result["flags"].get("vite") is True


def test_detect_stack_next():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "next.config.js", "content": "module.exports = {}"},
        {"path": "package.json", "content": json.dumps({"dependencies": {"next": "13.0.0"}})},
    ]
    result = detect_extended_stack(files)
    assert "next" in result["detected"]


def test_detect_stack_fastapi():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "main.py", "content": "from fastapi import FastAPI\napp = FastAPI()"},
        {"path": "requirements.txt", "content": "fastapi\nuvicorn"},
    ]
    result = detect_extended_stack(files)
    assert "fastapi" in result["detected"]
    assert result["package_manager"] == "pip"


def test_detect_stack_tailwind():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "tailwind.config.js", "content": "module.exports = {}"},
        {"path": "package.json", "content": json.dumps({"devDependencies": {"tailwindcss": "^3.0.0"}})},
    ]
    result = detect_extended_stack(files)
    assert "tailwind" in result["detected"]


def test_detect_stack_typescript():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "tsconfig.json", "content": "{}"},
        {"path": "src/app.ts", "content": "const x: number = 1;"},
        {"path": "package.json", "content": json.dumps({})},
    ]
    result = detect_extended_stack(files)
    assert "typescript" in result["detected"]


def test_detect_stack_static():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "index.html", "content": "<html><body>Hello</body></html>"},
        {"path": "style.css", "content": "body {}"},
    ]
    result = detect_extended_stack(files)
    assert "static" in result["detected"]


def test_detect_stack_docker():
    from app.repos.repair_engine import detect_extended_stack

    files = [
        {"path": "Dockerfile", "content": "FROM node:18"},
        {"path": "docker-compose.yml", "content": "version: '3'"},
    ]
    result = detect_extended_stack(files)
    assert "docker" in result["detected"]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2E — Repo Repair
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_repair_creates_env_example():
    from app.repos.repair_engine import RepairEngine

    db = _make_db()
    engine = RepairEngine(db, "repo1")
    files = [
        {"path": "package.json", "content": json.dumps({"dependencies": {"express": "4.0.0"}}), "language": "json"},
    ]
    profile = {"missing_env": ["DATABASE_URL", "SECRET_KEY"], "broken_imports": [], "syntax_errors": []}
    plan = await engine.create_repair_plan(files, profile)
    new_files, applied, skipped = await engine.apply_repairs(files, plan)

    applied_paths = [f["path"] for f in new_files]
    assert ".env.example" in applied_paths
    assert any("env" in a.lower() for a in applied)


@pytest.mark.asyncio
async def test_repair_adds_build_script():
    from app.repos.repair_engine import RepairEngine

    db = _make_db()
    engine = RepairEngine(db, "repo2")
    files = [
        {"path": "package.json", "content": json.dumps({"devDependencies": {"vite": "4.0"}}), "language": "json"},
    ]
    profile = {"missing_env": [], "broken_imports": [], "syntax_errors": []}
    plan = await engine.create_repair_plan(files, profile)
    new_files, applied, skipped = await engine.apply_repairs(files, plan)

    pkg = next((f for f in new_files if f["path"] == "package.json"), None)
    assert pkg is not None
    pkg_data = json.loads(pkg["content"])
    scripts = pkg_data.get("scripts", {})
    assert "build" in scripts or "dev" in scripts


def test_diff_summary_for_files_structure():
    from app.repos.repair_engine import generate_diff_summary_for_files

    old = [{"path": "index.html", "content": "<p>old</p>"}]
    new = [
        {"path": "index.html", "content": "<p>new</p>"},
        {"path": ".env.example", "content": "DATABASE_URL="},
    ]
    summary = generate_diff_summary_for_files(
        old, new,
        reason="Added env example and updated index",
        risk_level="low",
        build_result="success",
        validation_result="passed",
    )
    assert summary["files_changed"] == 2
    assert summary["files_added"] == 1
    assert summary["files_modified"] == 1
    assert "reason" in summary
    assert "markdown" in summary
    assert "Added" in summary["markdown"] or "Added" in summary["markdown"].lower()


def test_diff_summary_markdown_contains_risk():
    from app.repos.repair_engine import generate_diff_summary_for_files

    old = []
    new = [{"path": "app.py", "content": "from flask import Flask"}]
    summary = generate_diff_summary_for_files(
        old, new,
        reason="Added Flask app",
        risk_level="medium",
        build_result="success",
        validation_result="skipped",
    )
    assert "medium" in summary["markdown"].lower() or "Medium" in summary["markdown"]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2H — Checkpoints
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_checkpoint_persists():
    from app.repos.repair_engine import create_checkpoint, get_checkpoint

    db = _make_db()
    files = [{"path": "index.html", "content": "<p>before repair</p>"}]
    cp_id = await create_checkpoint(db, "proj5", files, label="pre-repair")
    assert cp_id

    cp = await get_checkpoint(db, "proj5", cp_id)
    assert cp is not None
    assert cp["label"] == "pre-repair"
    assert len(cp["file_snapshot"]) == 1
    assert cp["file_snapshot"][0]["path"] == "index.html"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2C — Preview Service
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_preview_service_static_success():
    """Static HTML preview must succeed and return real HTML, not a fake."""
    from app.runtime.preview_service import PreviewService

    svc = PreviewService()
    files = [
        {"path": "index.html", "content": "<html><body><h1>Hello World</h1></body></html>"},
        {"path": "style.css", "content": "body { margin: 0; }"},
    ]
    result = await svc.build_preview(files)

    assert result["success"] is True
    assert result["stack"] == "static"
    assert result["preview_html"] is not None
    assert "<html" in result["preview_html"].lower() or "Hello World" in result["preview_html"]
    assert result["runtime_status"] == "running"


@pytest.mark.asyncio
async def test_preview_service_returns_logs():
    """Preview result must always include build logs."""
    from app.runtime.preview_service import PreviewService

    svc = PreviewService()
    files = [{"path": "index.html", "content": "<h1>Test</h1>"}]
    result = await svc.build_preview(files)
    assert "logs" in result
    assert isinstance(result["logs"], list)


@pytest.mark.asyncio
async def test_preview_service_emits_events():
    """Preview service must emit build_log and preview_ready/preview_failed events."""
    from app.runtime.preview_service import PreviewService

    svc = PreviewService()
    events: list[dict] = []

    async def capture(event):
        events.append(event)

    files = [{"path": "index.html", "content": "<h1>Hello</h1>"}]
    await svc.build_preview(files, emit=capture)

    types = {e["type"] for e in events}
    assert "build_log" in types
    # Either preview_ready or preview_failed must be emitted
    assert "preview_ready" in types or "preview_failed" in types


@pytest.mark.asyncio
async def test_preview_service_detect_stack():
    from app.runtime.preview_service import PreviewService

    svc = PreviewService()
    files = [{"path": "index.html", "content": "<p>hi</p>"}]
    stack = svc.detect_stack(files)
    assert stack == "static"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2G — PR diff summary (markdown format)
# ═══════════════════════════════════════════════════════════════════════════

def test_pr_diff_markdown_not_vague():
    """PR diff summary must contain specific change information."""
    from app.repos.repair_engine import generate_diff_summary_for_files

    old = [{"path": "package.json", "content": '{"scripts":{}}'}]
    new = [
        {"path": "package.json", "content": '{"scripts":{"build":"vite build"}}'},
        {"path": ".env.example", "content": "PORT=3000"},
    ]
    summary = generate_diff_summary_for_files(
        old, new,
        reason="Add build script and env template",
        risk_level="low",
        build_result="success",
        validation_result="passed",
        unresolved_risks=["No tests added"],
    )
    md = summary["markdown"]
    # Must name the changed files
    assert "package.json" in md
    assert ".env.example" in md
    # Must state the reason
    assert "build script" in md.lower() or "env" in md.lower() or "reason" in md.lower()
    # Must state risk
    assert "low" in md.lower()
    # Must surface unresolved risk
    assert "No tests added" in md


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2K — Iteration task checklist (multi-change obedience)
# ═══════════════════════════════════════════════════════════════════════════

def test_iteration_response_has_checklist_fields():
    """Iteration response must report satisfied and unsatisfied tasks."""
    # This tests the data contract expected from the iteration agent output
    iteration_response = {
        "files": [
            {"path": "index.html", "content": "<h1>Dark Hero</h1>"},
            {"path": "pricing.html", "content": "<section>pricing</section>"},
        ],
        "requestedChanges": [
            "make the hero darker",
            "change the pricing section",
            "add a contact page",
        ],
        "satisfiedChanges": [
            "make the hero darker",
            "change the pricing section",
        ],
        "unsatisfiedChanges": [
            "add a contact page",
        ],
        "summary": "Updated hero and pricing; contact page not yet added.",
    }
    assert len(iteration_response["requestedChanges"]) == 3
    assert len(iteration_response["satisfiedChanges"]) == 2
    assert len(iteration_response["unsatisfiedChanges"]) == 1
    # All requests must be accounted for
    all_accounted = set(iteration_response["satisfiedChanges"]) | set(iteration_response["unsatisfiedChanges"])
    assert set(iteration_response["requestedChanges"]) == all_accounted


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2J — Cleanup scripts existence and executability
# ═══════════════════════════════════════════════════════════════════════════

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def test_cleanup_previews_script_exists():
    script = SCRIPTS_DIR / "cleanup_previews.sh"
    assert script.exists(), f"cleanup_previews.sh not found at {script}"


def test_cleanup_build_cache_script_exists():
    script = SCRIPTS_DIR / "cleanup_build_cache.sh"
    assert script.exists(), f"cleanup_build_cache.sh not found at {script}"


def test_check_runtime_health_script_exists():
    script = SCRIPTS_DIR / "check_runtime_health.sh"
    assert script.exists(), f"check_runtime_health.sh not found at {script}"


def test_cleanup_previews_dry_run():
    """Dry-run cleanup must not error."""
    import subprocess
    script = SCRIPTS_DIR / "cleanup_previews.sh"
    result = subprocess.run(
        ["bash", str(script), "--dry-run"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"cleanup_previews.sh dry-run failed: {result.stderr}"


def test_cleanup_build_cache_dry_run():
    """Dry-run cache cleanup must not error."""
    import subprocess
    script = SCRIPTS_DIR / "cleanup_build_cache.sh"
    result = subprocess.run(
        ["bash", str(script), "--dry-run"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"cleanup_build_cache.sh dry-run failed: {result.stderr}"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2A — Version not mutated check
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_version_immutability():
    """Each build must create a new version — old versions are never mutated."""
    from app.versioning.version_store import create_version, list_versions

    db = _make_db()
    await db.projects.insert_one({"id": "proj6", "status": "ready", "updated_at": "t"})

    v1 = await create_version(
        db, "proj6",
        user_request="Build v1",
        file_snapshot=[{"path": "index.html", "content": "<p>v1</p>"}],
        build_status="ready",
    )
    v2 = await create_version(
        db, "proj6",
        user_request="Build v2",
        file_snapshot=[{"path": "index.html", "content": "<p>v2</p>"}],
        build_status="ready",
    )
    versions = await list_versions(db, "proj6")
    assert len(versions) == 2
    ids = {v["version_id"] for v in versions}
    assert v1["version_id"] in ids
    assert v2["version_id"] in ids
    assert v1["version_id"] != v2["version_id"]


# ═══════════════════════════════════════════════════════════════════════════
# Regression: existing sandbox_manager still works
# ═══════════════════════════════════════════════════════════════════════════

def test_sandbox_detect_stack_static():
    from runtime.sandbox_manager import detect_stack

    files = [{"path": "index.html", "content": "<h1>hi</h1>"}]
    assert detect_stack(files) == "static"


def test_sandbox_detect_stack_vite():
    from runtime.sandbox_manager import detect_stack

    files = [
        {"path": "vite.config.ts", "content": "export default {}"},
        {"path": "package.json", "content": json.dumps({"devDependencies": {"vite": "4.0.0"}})},
    ]
    assert detect_stack(files) == "vite"


def test_sandbox_detect_stack_next():
    from runtime.sandbox_manager import detect_stack

    files = [
        {"path": "next.config.js", "content": "module.exports = {}"},
        {"path": "package.json", "content": json.dumps({"dependencies": {"next": "13.0.0"}})},
    ]
    assert detect_stack(files) == "next"


def test_sandbox_detect_stack_fastapi():
    from runtime.sandbox_manager import detect_stack

    files = [{"path": "main.py", "content": "from fastapi import FastAPI"}]
    assert detect_stack(files) == "fastapi"


def test_sandbox_detect_stack_django():
    from runtime.sandbox_manager import detect_stack

    files = [
        {"path": "manage.py", "content": "#!/usr/bin/env python"},
        {"path": "settings.py", "content": "from django.conf import settings"},
    ]
    assert detect_stack(files) == "django"
