"""
Amarktai App Builder — VPS GitHub Build Storage Service.

Provides a safe, structured local workspace for:
  - Imported GitHub repos
  - Generated apps
  - Incomplete/half-built apps
  - Release-ready builds

Storage root: /var/www/amarktai/builds (or BUILDS_STORAGE_ROOT env var)

Layout:
  {root}/repos/{owner}/{repo}/{branch-or-build-id}/   ← imported repos
  {root}/generated/{project_id}/                      ← AI-generated apps
  {root}/incomplete/{project_id}/                     ← half-built saves
  {root}/releases/{project_id}/{version}/             ← release-ready builds

Each workspace directory contains:
  build.json        ← project/build metadata
  repo.json         ← source repo info (when imported)
  status.json       ← last known build/audit/deploy status
  env.example       ← detected env vars
  audit_report.json ← last audit
  repair_plan.json  ← last repair plan
  deploy_report.json← last deploy report
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.build_storage")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BUILDS_ROOT = "/var/www/amarktai/builds"
BUILD_TYPES = frozenset({"repos", "generated", "incomplete", "releases"})
BUILD_STATUS_VALUES = frozenset({
    "pending", "cloning", "cloned", "building", "built",
    "incomplete", "failed", "audited", "repaired",
    "release_ready", "deployed", "archived",
})
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

METADATA_FILES = [
    "build.json",
    "repo.json",
    "status.json",
    "env.example",
    "audit_report.json",
    "repair_plan.json",
    "deploy_report.json",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_storage_root() -> Path:
    """Return the configured build storage root, creating it if needed."""
    raw = os.environ.get("BUILDS_STORAGE_ROOT", DEFAULT_BUILDS_ROOT)
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Create sub-directories
    for sub in BUILD_TYPES:
        (root / sub).mkdir(exist_ok=True)
    return root


def _safe_segment(value: str) -> str:
    """Sanitise a path segment — reject anything that isn't alphanum/dash/dot/underscore."""
    if not value or not _SAFE_PATH_RE.match(value):
        raise ValueError(f"Unsafe path segment: {value!r}")
    # Extra guard: no path traversal
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"Path traversal attempt: {value!r}")
    return value


def _assert_inside_root(path: Path, root: Path) -> None:
    """Raise ValueError if path is not inside root (prevents traversal after resolution)."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path {path} is outside the builds storage root {root}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Workspace paths ───────────────────────────────────────────────────────────

def repo_workspace_path(owner: str, repo: str, branch_or_id: str) -> Path:
    root = get_storage_root()
    path = root / "repos" / _safe_segment(owner) / _safe_segment(repo) / _safe_segment(branch_or_id)
    _assert_inside_root(path, root)
    return path


def generated_workspace_path(project_id: str) -> Path:
    root = get_storage_root()
    path = root / "generated" / _safe_segment(project_id)
    _assert_inside_root(path, root)
    return path


def incomplete_workspace_path(project_id: str) -> Path:
    root = get_storage_root()
    path = root / "incomplete" / _safe_segment(project_id)
    _assert_inside_root(path, root)
    return path


def release_workspace_path(project_id: str, version: str) -> Path:
    root = get_storage_root()
    path = root / "releases" / _safe_segment(project_id) / _safe_segment(version)
    _assert_inside_root(path, root)
    return path


# ── Metadata schema ───────────────────────────────────────────────────────────

def _build_metadata(
    *,
    project_id: str,
    workspace_type: str,
    local_path: Path,
    source_repo_url: str = "",
    github_owner: str = "",
    github_repo: str = "",
    branch: str = "",
    commit_sha: str = "",
    build_status: str = "pending",
    detected_stack: dict | None = None,
    frontend_path: str = "",
    backend_path: str = "",
    deploy_target: str = "",
    github_pr_url: str = "",
    provider_capabilities_used: list[str] | None = None,
    missing_env_vars: list[str] | None = None,
) -> dict:
    now = _now()
    return {
        "project_id": project_id,
        "workspace_type": workspace_type,
        "source_repo_url": source_repo_url,
        "github_owner": github_owner,
        "github_repo": github_repo,
        "branch": branch,
        "commit_sha": commit_sha,
        "local_path": str(local_path),
        "build_status": build_status,
        "last_audit_status": None,
        "last_test_status": None,
        "last_deploy_status": None,
        "created_at": now,
        "updated_at": now,
        "last_opened_at": now,
        "provider_capabilities_used": provider_capabilities_used or [],
        "missing_env_vars": missing_env_vars or [],
        "detected_stack": detected_stack or {},
        "frontend_path": frontend_path,
        "backend_path": backend_path,
        "deploy_target": deploy_target,
        "github_pr_url": github_pr_url,
    }


# ── Core workspace operations ─────────────────────────────────────────────────

def create_repo_workspace(
    owner: str,
    repo: str,
    branch: str,
    commit_sha: str = "",
    repo_url: str = "",
) -> dict:
    """Create (or return existing) a workspace directory for an imported repo.

    Returns the build metadata dict.
    """
    branch_id = branch.replace("/", "_") or "main"
    ws = repo_workspace_path(owner, repo, branch_id)
    ws.mkdir(parents=True, exist_ok=True)

    meta_path = ws / "build.json"
    existing = _read_json(meta_path)
    if existing:
        # Update access time
        existing["last_opened_at"] = _now()
        existing["commit_sha"] = commit_sha or existing.get("commit_sha", "")
        _write_json(meta_path, existing)
        return existing

    meta = _build_metadata(
        project_id=f"{owner}-{repo}-{branch_id}",
        workspace_type="repo",
        local_path=ws,
        source_repo_url=repo_url or f"https://github.com/{owner}/{repo}",
        github_owner=owner,
        github_repo=repo,
        branch=branch,
        commit_sha=commit_sha,
        build_status="cloned",
    )
    _write_json(meta_path, meta)
    _write_json(ws / "repo.json", {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "commit_sha": commit_sha,
        "html_url": f"https://github.com/{owner}/{repo}",
        "imported_at": _now(),
    })
    _write_json(ws / "status.json", {"build_status": "cloned", "updated_at": _now()})
    logger.info("Created repo workspace: %s", ws)
    return meta


def create_generated_workspace(project_id: str) -> dict:
    """Create (or return existing) workspace for an AI-generated app."""
    ws = generated_workspace_path(project_id)
    ws.mkdir(parents=True, exist_ok=True)

    meta_path = ws / "build.json"
    existing = _read_json(meta_path)
    if existing:
        existing["last_opened_at"] = _now()
        _write_json(meta_path, existing)
        return existing

    meta = _build_metadata(
        project_id=project_id,
        workspace_type="generated",
        local_path=ws,
        build_status="building",
    )
    _write_json(meta_path, meta)
    _write_json(ws / "status.json", {"build_status": "building", "updated_at": _now()})
    logger.info("Created generated workspace: %s", ws)
    return meta


def create_incomplete_workspace(project_id: str) -> dict:
    """Save a half-built app to the incomplete store for later continuation."""
    ws = incomplete_workspace_path(project_id)
    ws.mkdir(parents=True, exist_ok=True)

    meta_path = ws / "build.json"
    existing = _read_json(meta_path)
    if existing:
        existing["last_opened_at"] = _now()
        existing["build_status"] = "incomplete"
        _write_json(meta_path, existing)
        return existing

    meta = _build_metadata(
        project_id=project_id,
        workspace_type="incomplete",
        local_path=ws,
        build_status="incomplete",
    )
    _write_json(meta_path, meta)
    _write_json(ws / "status.json", {"build_status": "incomplete", "updated_at": _now()})
    logger.info("Created incomplete workspace: %s", ws)
    return meta


def create_release_workspace(project_id: str, version: str) -> dict:
    """Create a release-ready build snapshot."""
    ws = release_workspace_path(project_id, version)
    ws.mkdir(parents=True, exist_ok=True)

    meta_path = ws / "build.json"
    existing = _read_json(meta_path)
    if existing:
        return existing

    meta = _build_metadata(
        project_id=project_id,
        workspace_type="release",
        local_path=ws,
        build_status="release_ready",
    )
    _write_json(meta_path, meta)
    _write_json(ws / "status.json", {"build_status": "release_ready", "updated_at": _now()})
    logger.info("Created release workspace: %s", ws)
    return meta


# ── Metadata updates ──────────────────────────────────────────────────────────

def update_workspace_metadata(workspace_path: Path, updates: dict) -> dict:
    """Merge updates into build.json for a workspace."""
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    meta_path = resolved / "build.json"
    meta = _read_json(meta_path)
    meta.update(updates)
    meta["updated_at"] = _now()
    _write_json(meta_path, meta)
    # Also update status.json if build_status changed
    if "build_status" in updates:
        _write_json(resolved / "status.json", {
            "build_status": updates["build_status"],
            "updated_at": _now(),
        })
    return meta


def save_audit_report(workspace_path: Path, report: dict) -> None:
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    _write_json(resolved / "audit_report.json", {**report, "saved_at": _now()})
    update_workspace_metadata(resolved, {"last_audit_status": report.get("status", "audited")})


def save_repair_plan(workspace_path: Path, plan: dict) -> None:
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    _write_json(resolved / "repair_plan.json", {**plan, "saved_at": _now()})


def save_deploy_report(workspace_path: Path, report: dict) -> None:
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    _write_json(resolved / "deploy_report.json", {**report, "saved_at": _now()})
    update_workspace_metadata(resolved, {"last_deploy_status": report.get("status", "deployed")})


def save_env_example(workspace_path: Path, env_vars: list[str]) -> None:
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    content = "# Auto-detected environment variables\n# Fill in values before deploying.\n\n"
    content += "\n".join(f"{v}=" for v in sorted(env_vars))
    (resolved / "env.example").write_text(content, encoding="utf-8")


# ── Listing / discovery ───────────────────────────────────────────────────────

def _load_workspace_meta(ws_dir: Path) -> dict | None:
    meta = _read_json(ws_dir / "build.json")
    if not meta:
        return None
    meta["local_path"] = str(ws_dir)
    return meta


def list_workspaces(workspace_type: str | None = None) -> list[dict]:
    """Return all workspace metadata dicts, optionally filtered by type."""
    root = get_storage_root()
    results: list[dict] = []

    # Validate workspace_type against the whitelist before using as path component
    if workspace_type is not None and workspace_type not in BUILD_TYPES:
        raise ValueError(f"Invalid workspace_type: {workspace_type!r}. Must be one of: {sorted(BUILD_TYPES)}")

    types_to_scan = BUILD_TYPES if not workspace_type else {workspace_type}

    for btype in types_to_scan:
        base = root / btype
        if not base.exists():
            continue
        if btype == "repos":
            for owner_dir in sorted(base.iterdir()):
                if not owner_dir.is_dir():
                    continue
                for repo_dir in sorted(owner_dir.iterdir()):
                    if not repo_dir.is_dir():
                        continue
                    for branch_dir in sorted(repo_dir.iterdir()):
                        if not branch_dir.is_dir():
                            continue
                        m = _load_workspace_meta(branch_dir)
                        if m:
                            results.append(m)
        elif btype == "releases":
            for proj_dir in sorted(base.iterdir()):
                if not proj_dir.is_dir():
                    continue
                for ver_dir in sorted(proj_dir.iterdir()):
                    if not ver_dir.is_dir():
                        continue
                    m = _load_workspace_meta(ver_dir)
                    if m:
                        results.append(m)
        else:
            for proj_dir in sorted(base.iterdir()):
                if not proj_dir.is_dir():
                    continue
                m = _load_workspace_meta(proj_dir)
                if m:
                    results.append(m)

    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results


def get_workspace(workspace_path: Path) -> dict:
    """Load metadata for a specific workspace directory."""
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    meta = _load_workspace_meta(resolved)
    if not meta:
        raise FileNotFoundError(f"No build.json found at {resolved}")
    return meta


def storage_usage() -> dict:
    """Return total and per-type storage usage."""
    root = get_storage_root()
    total_bytes = 0
    per_type: dict[str, int] = {}
    for btype in BUILD_TYPES:
        base = root / btype
        if not base.exists():
            per_type[btype] = 0
            continue
        size = sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
        per_type[btype] = size
        total_bytes += size
    return {
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1_048_576, 2),
        "per_type": {k: {"bytes": v, "mb": round(v / 1_048_576, 2)} for k, v in per_type.items()},
        "root": str(root),
    }


# ── Safe delete / archive ─────────────────────────────────────────────────────

def archive_workspace(workspace_path: Path, confirmed: bool = False) -> dict:
    """Move workspace to {root}/archived/{name}."""
    if not confirmed:
        return {"ok": False, "error": "Archive requires confirmed=True."}
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    if not resolved.exists():
        return {"ok": False, "error": "Workspace not found."}
    archive_root = root / "archived"
    archive_root.mkdir(exist_ok=True)
    dest = archive_root / resolved.name
    # Avoid name collisions
    if dest.exists():
        dest = archive_root / f"{resolved.name}_{_now().replace(':', '-').replace('.', '-')}"
    shutil.move(str(resolved), str(dest))
    logger.info("Archived workspace %s → %s", resolved, dest)
    return {"ok": True, "archived_to": str(dest)}


def delete_workspace(workspace_path: Path, confirmed: bool = False) -> dict:
    """Permanently delete a workspace. Requires confirmed=True and must be inside root."""
    if not confirmed:
        return {"ok": False, "error": "Delete requires confirmed=True."}
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)
    if not resolved.exists():
        return {"ok": False, "error": "Workspace not found."}
    shutil.rmtree(str(resolved))
    logger.info("Deleted workspace: %s", workspace_path)
    return {"ok": True, "deleted": str(workspace_path)}


# ── Stack detection integration ───────────────────────────────────────────────

def detect_and_save_stack(workspace_path: Path, files: list[dict[str, Any]]) -> dict:
    """Run stack detection on workspace files and persist the result."""
    from agents.stack_engine import decide_stack
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)

    try:
        stack = decide_stack("", "auto")
        # Try to infer from filenames
        paths = [f.get("path", "") for f in files]
        stack_info: dict[str, Any] = {
            "has_package_json": any("package.json" in p for p in paths),
            "has_requirements_txt": any("requirements.txt" in p for p in paths),
            "has_dockerfile": any(p.lower() == "dockerfile" for p in paths),
            "has_docker_compose": any("docker-compose" in p.lower() for p in paths),
            "has_react": any(".jsx" in p or ".tsx" in p for p in paths),
            "has_next": any("next.config" in p for p in paths),
            "has_vite": any("vite.config" in p for p in paths),
            "has_fastapi": any("main.py" in p or "server.py" in p for p in paths),
            "total_files": len(files),
        }
        # Derive frontend/backend paths
        frontend_path = ""
        backend_path = ""
        if any("frontend/" in p for p in paths):
            frontend_path = "frontend"
        elif stack_info["has_react"] and any("src/" in p for p in paths):
            frontend_path = "src"
        if any("backend/" in p for p in paths):
            backend_path = "backend"

        update_workspace_metadata(resolved, {
            "detected_stack": stack_info,
            "frontend_path": frontend_path,
            "backend_path": backend_path,
        })
        return stack_info
    except Exception as exc:
        logger.warning("Stack detection failed for %s: %s", resolved, exc)
        return {}


def detect_missing_env_vars(workspace_path: Path, files: list[dict[str, Any]]) -> list[str]:
    """Scan files for env var references and compare to env.example."""
    root = get_storage_root()
    resolved = workspace_path.resolve()
    _assert_inside_root(resolved, root)

    env_re = re.compile(r'(?:process\.env\.|os\.environ\.get\(|os\.getenv\()["\']?([A-Z_][A-Z0-9_]{2,})')
    found: set[str] = set()
    for f in files:
        content = f.get("content", "")
        found.update(env_re.findall(content))

    env_example_path = resolved / "env.example"
    declared: set[str] = set()
    if env_example_path.exists():
        for line in env_example_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                declared.add(line.split("=")[0].strip())

    missing = sorted(found - declared)
    if missing:
        update_workspace_metadata(resolved, {"missing_env_vars": missing})
    return missing
