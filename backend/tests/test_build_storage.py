"""
Build Storage Service tests — Amarktai App Builder.

Covers:
  - Path safety (traversal prevention)
  - Workspace creation and metadata
  - Storage listing
  - Archive / delete safety
  - Stack detection
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pytest

# Point the storage root at a temp directory for tests
_TMP_ROOT = tempfile.mkdtemp(prefix="amarktai_builds_test_")
os.environ["BUILDS_STORAGE_ROOT"] = _TMP_ROOT


from app.services.build_storage_service import (
    _safe_segment,
    _assert_inside_root,
    create_repo_workspace,
    create_generated_workspace,
    create_incomplete_workspace,
    create_release_workspace,
    update_workspace_metadata,
    list_workspaces,
    archive_workspace,
    delete_workspace,
    storage_usage,
    get_storage_root,
    detect_missing_env_vars,
)
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Path safety
# ─────────────────────────────────────────────────────────────────────────────

class TestPathSafety:
    def test_safe_segment_rejects_traversal(self):
        with pytest.raises(ValueError):
            _safe_segment("../etc")

    def test_safe_segment_rejects_slash(self):
        with pytest.raises(ValueError):
            _safe_segment("owner/repo")

    def test_safe_segment_rejects_backslash(self):
        with pytest.raises(ValueError):
            _safe_segment("owner\\repo")

    def test_safe_segment_allows_valid(self):
        assert _safe_segment("my-owner") == "my-owner"
        assert _safe_segment("my.repo") == "my.repo"
        assert _safe_segment("owner123") == "owner123"

    def test_assert_inside_root_blocks_outside(self):
        root = Path(_TMP_ROOT)
        outside = Path("/etc")
        with pytest.raises(ValueError):
            _assert_inside_root(outside, root)

    def test_assert_inside_root_allows_inside(self):
        root = Path(_TMP_ROOT)
        inside = root / "repos" / "testowner" / "testrepo"
        inside.mkdir(parents=True, exist_ok=True)
        _assert_inside_root(inside, root)  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# Workspace creation
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspaceCreation:
    def test_create_repo_workspace(self):
        meta = create_repo_workspace("myowner", "myrepo", "main", "abc123", "https://github.com/myowner/myrepo")
        assert meta["github_owner"] == "myowner"
        assert meta["github_repo"] == "myrepo"
        assert meta["branch"] == "main"
        assert meta["commit_sha"] == "abc123"
        assert meta["build_status"] == "cloned"
        assert "local_path" in meta
        ws_path = Path(meta["local_path"])
        assert ws_path.exists()
        assert (ws_path / "build.json").exists()
        assert (ws_path / "repo.json").exists()
        assert (ws_path / "status.json").exists()

    def test_create_repo_workspace_idempotent(self):
        meta1 = create_repo_workspace("owner2", "repo2", "develop", "sha1")
        meta2 = create_repo_workspace("owner2", "repo2", "develop", "sha2")
        # Second call should update sha but keep existing
        assert meta2["github_owner"] == "owner2"
        assert meta2["commit_sha"] == "sha2"

    def test_create_generated_workspace(self):
        meta = create_generated_workspace("proj-test-001")
        assert meta["project_id"] == "proj-test-001"
        assert meta["build_status"] == "building"
        ws_path = Path(meta["local_path"])
        assert ws_path.exists()

    def test_create_incomplete_workspace(self):
        meta = create_incomplete_workspace("proj-incomplete-001")
        assert meta["build_status"] == "incomplete"
        ws_path = Path(meta["local_path"])
        assert ws_path.exists()

    def test_create_release_workspace(self):
        meta = create_release_workspace("proj-release-001", "v1.0.0")
        assert meta["build_status"] == "release_ready"
        ws_path = Path(meta["local_path"])
        assert ws_path.exists()

    def test_workspace_metadata_fields(self):
        meta = create_repo_workspace("fieldowner", "fieldrepo", "main")
        required = [
            "project_id", "workspace_type", "source_repo_url", "github_owner",
            "github_repo", "branch", "commit_sha", "local_path", "build_status",
            "last_audit_status", "last_test_status", "last_deploy_status",
            "created_at", "updated_at", "last_opened_at",
            "provider_capabilities_used", "missing_env_vars",
            "detected_stack", "frontend_path", "backend_path",
            "deploy_target", "github_pr_url",
        ]
        for field in required:
            assert field in meta, f"Missing field: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# Metadata update
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadataUpdate:
    def test_update_metadata(self):
        meta = create_repo_workspace("upowner", "uprepo", "main")
        ws_path = Path(meta["local_path"])
        updated = update_workspace_metadata(ws_path, {"build_status": "audited", "github_pr_url": "https://github.com/pr/1"})
        assert updated["build_status"] == "audited"
        assert updated["github_pr_url"] == "https://github.com/pr/1"
        # Verify status.json also updated
        status = json.loads((ws_path / "status.json").read_text())
        assert status["build_status"] == "audited"

    def test_update_metadata_outside_root_blocked(self):
        with pytest.raises(ValueError):
            update_workspace_metadata(Path("/etc/malicious"), {"x": 1})


# ─────────────────────────────────────────────────────────────────────────────
# Listing
# ─────────────────────────────────────────────────────────────────────────────

class TestListing:
    def test_list_workspaces_returns_list(self):
        result = list_workspaces()
        assert isinstance(result, list)

    def test_list_workspaces_filter_by_type(self):
        create_repo_workspace("listowner", "listrepo", "main")
        create_generated_workspace("list-generated-001")
        repos = list_workspaces("repos")
        generated = list_workspaces("generated")
        for ws in repos:
            assert ws.get("workspace_type") in ("repo", "repos")
        for ws in generated:
            assert ws.get("workspace_type") in ("generated",)

    def test_storage_usage_returns_dict(self):
        usage = storage_usage()
        assert "total_bytes" in usage
        assert "total_mb" in usage
        assert "per_type" in usage
        assert "root" in usage


# ─────────────────────────────────────────────────────────────────────────────
# Archive / delete safety
# ─────────────────────────────────────────────────────────────────────────────

class TestArchiveDelete:
    def test_archive_requires_confirmed(self):
        meta = create_repo_workspace("archowner", "archrepo", "main")
        ws_path = Path(meta["local_path"])
        result = archive_workspace(ws_path, confirmed=False)
        assert result["ok"] is False
        assert "confirmed" in result["error"]

    def test_archive_works_when_confirmed(self):
        meta = create_repo_workspace("archowner2", "archrepo2", "main")
        ws_path = Path(meta["local_path"])
        result = archive_workspace(ws_path, confirmed=True)
        assert result["ok"] is True
        assert not ws_path.exists()

    def test_delete_requires_confirmed(self):
        meta = create_repo_workspace("delowner", "delrepo", "main")
        ws_path = Path(meta["local_path"])
        result = delete_workspace(ws_path, confirmed=False)
        assert result["ok"] is False

    def test_delete_outside_root_blocked(self):
        with pytest.raises(ValueError):
            delete_workspace(Path("/tmp/evil"), confirmed=True)

    def test_delete_works_when_confirmed(self):
        meta = create_incomplete_workspace("del-proj-001")
        ws_path = Path(meta["local_path"])
        result = delete_workspace(ws_path, confirmed=True)
        assert result["ok"] is True
        assert not ws_path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Env var detection
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvVarDetection:
    def test_detects_env_vars(self):
        meta = create_generated_workspace("envtest-001")
        ws_path = Path(meta["local_path"])
        files = [
            {"path": "app.js", "content": "const key = process.env.MY_API_KEY;"},
            {"path": "server.py", "content": "val = os.environ.get('MY_DB_URL')"},
        ]
        missing = detect_missing_env_vars(ws_path, files)
        assert "MY_API_KEY" in missing or "MY_DB_URL" in missing
