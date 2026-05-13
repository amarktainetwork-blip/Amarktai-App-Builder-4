"""
Amarktai App Builder — Continue Build / Repair Pipeline Service.

Wires together:
  1. Load local workspace
  2. Detect stack
  3. Detect missing pieces (pages/routes/env/tests/assets)
  4. Read previous status/audit/repair files
  5. Produce a completion plan
  6. Apply safe file edits (with diff)
  7. Optionally run build/test
  8. Save version and repair history
  9. Allow commit/PR

All destructive edits require either auto_apply=True or explicit diff approval.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.continue_build")

DEFAULT_BUILDS_ROOT = "/var/www/amarktai/builds"

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _builds_root() -> Path:
    raw = os.environ.get("BUILDS_STORAGE_ROOT", DEFAULT_BUILDS_ROOT)
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


# ── Workspace loading ─────────────────────────────────────────────────────────

def load_workspace(workspace_path: str | Path) -> dict[str, Any]:
    """Load a workspace and all its metadata files."""
    ws = Path(workspace_path).resolve()
    if not ws.exists():
        return {"ok": False, "error": f"Workspace not found: {ws}"}

    build_meta = _load_json_file(ws / "build.json")
    repo_meta = _load_json_file(ws / "repo.json")
    status = _load_json_file(ws / "status.json")
    audit = _load_json_file(ws / "audit_report.json")
    repair = _load_json_file(ws / "repair_plan.json")

    # List source files
    files: list[str] = []
    for p in sorted(ws.rglob("*")):
        if p.is_file():
            rel = p.relative_to(ws)
            parts = rel.parts
            if any(d in _SKIP_DIRS for d in parts):
                continue
            files.append(str(rel))
            if len(files) >= 500:
                break

    return {
        "ok": True,
        "workspace_path": str(ws),
        "build_meta": build_meta,
        "repo_meta": repo_meta,
        "status": status,
        "last_audit": audit,
        "last_repair": repair,
        "files": files,
        "file_count": len(files),
        "loaded_at": _now(),
    }


# ── Stack detection ───────────────────────────────────────────────────────────

def detect_workspace_stack(workspace_path: str | Path) -> dict[str, Any]:
    """Detect the technology stack of the workspace."""
    ws = Path(workspace_path).resolve()
    if not ws.exists():
        return {"ok": False, "stack": "unknown"}

    indicators: dict[str, bool] = {}

    # Frontend
    pkg_json = ws / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {}
            deps.update(pkg.get("dependencies", {}))
            deps.update(pkg.get("devDependencies", {}))
            indicators["react"] = "react" in deps
            indicators["nextjs"] = "next" in deps
            indicators["vue"] = "vue" in deps
            indicators["svelte"] = "svelte" in deps
            indicators["vite"] = "vite" in deps
            indicators["typescript"] = "typescript" in deps
            indicators["tailwind"] = "tailwindcss" in deps
        except Exception:
            pass

    # Backend
    indicators["python"] = any((ws / f).exists() for f in ["requirements.txt", "pyproject.toml", "setup.py"])
    indicators["fastapi"] = _check_content(ws / "requirements.txt", "fastapi")
    indicators["django"] = _check_content(ws / "requirements.txt", "django")
    indicators["docker"] = (ws / "Dockerfile").exists() or (ws / "docker-compose.yml").exists()

    # Detect primary stack
    if indicators.get("nextjs"):
        primary = "nextjs"
    elif indicators.get("react"):
        primary = "react"
    elif indicators.get("vue"):
        primary = "vue"
    elif indicators.get("svelte"):
        primary = "svelte"
    elif indicators.get("python"):
        primary = "python"
    else:
        primary = "static"

    return {
        "ok": True,
        "primary": primary,
        "indicators": indicators,
        "detected_at": _now(),
    }


def _check_content(path: Path, keyword: str) -> bool:
    if not path.exists():
        return False
    try:
        return keyword.lower() in path.read_text().lower()
    except Exception:
        return False


# ── Missing piece detection ───────────────────────────────────────────────────

def detect_missing_pieces(workspace_path: str | Path, stack: str) -> dict[str, Any]:
    """Detect what's missing from the workspace based on the detected stack."""
    ws = Path(workspace_path).resolve()
    missing: list[dict] = []
    present: list[str] = []

    def _check(rel_path: str, label: str, severity: str = "warning") -> None:
        if (ws / rel_path).exists():
            present.append(label)
        else:
            missing.append({"path": rel_path, "label": label, "severity": severity})

    # Universal
    _check("README.md", "README", "warning")
    _check(".env.example", "env.example", "warning")

    # Frontend-specific
    if stack in ("react", "nextjs", "vue", "svelte", "vite"):
        _check("package.json", "package.json", "blocker")

        if stack == "nextjs":
            _check("app/page.tsx", "Next.js app entry OR pages/index.tsx", "blocker")
            if not (ws / "app" / "page.tsx").exists():
                _check("pages/index.tsx", "pages/index.tsx", "warning")
        elif stack in ("react", "vite"):
            for entry in ["src/index.tsx", "src/index.jsx", "src/main.tsx", "src/main.jsx"]:
                if (ws / entry).exists():
                    present.append(f"Entry: {entry}")
                    break
            else:
                missing.append({"path": "src/index.tsx", "label": "React entry point", "severity": "blocker"})

    # Python-specific
    if stack == "python":
        _check("requirements.txt", "requirements.txt", "warning")
        for main in ["main.py", "app.py", "server.py", "run.py"]:
            if (ws / main).exists():
                present.append(f"Python main: {main}")
                break
        else:
            missing.append({"path": "main.py", "label": "Python main entry", "severity": "warning"})

    return {
        "ok": True,
        "missing": missing,
        "present": present,
        "missing_count": len(missing),
        "blocker_count": sum(1 for m in missing if m.get("severity") == "blocker"),
        "detected_at": _now(),
    }


# ── Completion plan ───────────────────────────────────────────────────────────

def generate_completion_plan(
    workspace_info: dict[str, Any],
    stack_info: dict[str, Any],
    missing_info: dict[str, Any],
    project_description: str = "",
) -> dict[str, Any]:
    """
    Generate a structured completion plan for the workspace.

    This produces a list of actionable tasks that the repair/build agents
    should execute in order.
    """
    tasks: list[dict] = []
    task_id = 1

    stack = stack_info.get("primary", "unknown")

    # Install dependencies first
    if (Path(workspace_info["workspace_path"]) / "package.json").exists():
        tasks.append({
            "id": task_id,
            "type": "command",
            "action": "install_dependencies",
            "description": "Install project dependencies",
            "command": ["npm", "install"],
            "priority": "high",
        })
        task_id += 1

    # Create missing files
    for item in missing_info.get("missing", []):
        if item.get("severity") == "blocker":
            tasks.append({
                "id": task_id,
                "type": "create_file",
                "action": "create_missing_file",
                "description": f"Create missing {item['label']}",
                "path": item["path"],
                "priority": "high",
            })
            task_id += 1

    # Run build
    if stack in ("react", "nextjs", "vue", "svelte", "vite"):
        tasks.append({
            "id": task_id,
            "type": "command",
            "action": "build",
            "description": "Run project build",
            "command": ["npm", "run", "build"],
            "priority": "medium",
        })
        task_id += 1

    # Run tests
    tasks.append({
        "id": task_id,
        "type": "command",
        "action": "test",
        "description": "Run tests",
        "command": ["npm", "test"] if stack in ("react", "nextjs", "vue") else ["python", "-m", "pytest"],
        "priority": "medium",
    })
    task_id += 1

    # QA gate
    tasks.append({
        "id": task_id,
        "type": "qa_gate",
        "action": "quality_check",
        "description": "Run premium quality gate",
        "priority": "high",
    })

    return {
        "ok": True,
        "plan_version": "1.0",
        "stack": stack,
        "task_count": len(tasks),
        "tasks": tasks,
        "description": project_description,
        "generated_at": _now(),
    }


# ── Diff generation ───────────────────────────────────────────────────────────

def generate_repair_diff(
    workspace_path: str | Path,
    proposed_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate a human-readable diff for proposed file changes before applying.

    Each change in proposed_changes should have:
      - path: str  (relative to workspace)
      - content: str  (new content)
      - action: "create" | "modify" | "delete"
    """
    import difflib

    ws = Path(workspace_path).resolve()
    diffs: list[dict] = []

    for change in proposed_changes:
        rel_path = change.get("path", "")
        action = change.get("action", "modify")
        new_content = change.get("content", "")

        # Path safety
        safe_path = (ws / rel_path).resolve()
        try:
            safe_path.relative_to(ws)
        except ValueError:
            diffs.append({
                "path": rel_path,
                "action": "rejected",
                "reason": "Path traversal denied",
            })
            continue

        old_content = ""
        if safe_path.exists() and action != "create":
            try:
                old_content = safe_path.read_text(errors="replace")
            except Exception:
                pass

        if action == "delete":
            diff_text = f"--- {rel_path}\n+++ /dev/null\n@@ removed @@\n"
        else:
            diff_lines = list(difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                n=3,
            ))
            diff_text = "".join(diff_lines[:200])  # cap diff size

        diffs.append({
            "path": rel_path,
            "action": action,
            "diff": diff_text,
            "lines_added": diff_text.count("\n+") if diff_text else 0,
            "lines_removed": diff_text.count("\n-") if diff_text else 0,
        })

    return {
        "ok": True,
        "changes": len(diffs),
        "diffs": diffs,
        "generated_at": _now(),
    }


# ── Apply repair ──────────────────────────────────────────────────────────────

def apply_repair(
    workspace_path: str | Path,
    changes: list[dict[str, Any]],
    auto_apply: bool = False,
) -> dict[str, Any]:
    """
    Apply a list of file changes to the workspace.

    If auto_apply=False (default), returns the diff without applying.
    If auto_apply=True, applies the changes.
    """
    ws = Path(workspace_path).resolve()

    if not ws.exists():
        return {"ok": False, "error": "Workspace not found"}

    diff_result = generate_repair_diff(ws, changes)

    if not auto_apply:
        return {
            "ok": True,
            "applied": False,
            "reason": "auto_apply=False; review the diff and re-submit with auto_apply=True",
            "diff": diff_result,
        }

    applied: list[str] = []
    errors: list[str] = []

    for change in changes:
        rel_path = change.get("path", "")
        action = change.get("action", "modify")
        content = change.get("content", "")

        safe_path = (ws / rel_path).resolve()
        try:
            safe_path.relative_to(ws)
        except ValueError:
            errors.append(f"Path traversal denied: {rel_path}")
            continue

        try:
            if action == "delete":
                if safe_path.exists():
                    safe_path.unlink()
                    applied.append(f"deleted: {rel_path}")
            else:
                safe_path.parent.mkdir(parents=True, exist_ok=True)
                safe_path.write_text(content)
                applied.append(f"{'created' if action == 'create' else 'modified'}: {rel_path}")
        except Exception as exc:
            errors.append(f"Error applying {rel_path}: {exc}")

    # Update status
    status_path = ws / "status.json"
    status = _load_json_file(status_path)
    status["last_repair_applied_at"] = _now()
    status["repair_applied_count"] = status.get("repair_applied_count", 0) + 1
    try:
        status_path.write_text(json.dumps(status, indent=2))
    except Exception:
        pass

    return {
        "ok": len(errors) == 0,
        "applied": True,
        "files_modified": len(applied),
        "changes": applied,
        "errors": errors,
        "applied_at": _now(),
    }


# ── Save repair plan ──────────────────────────────────────────────────────────

def save_repair_plan_to_workspace(
    workspace_path: str | Path,
    plan: dict[str, Any],
) -> None:
    ws = Path(workspace_path).resolve()
    try:
        (ws / "repair_plan.json").write_text(json.dumps(plan, indent=2))
    except Exception as exc:
        logger.warning("Could not save repair plan: %s", exc)


# ── Version snapshot ──────────────────────────────────────────────────────────

def create_workspace_version(
    workspace_path: str | Path,
    label: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Create a lightweight snapshot (metadata only) of the current workspace state."""
    ws = Path(workspace_path).resolve()
    if not ws.exists():
        return {"ok": False, "error": "Workspace not found"}

    versions_dir = ws / ".versions"
    versions_dir.mkdir(exist_ok=True)

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version_id = ts

    status = _load_json_file(ws / "status.json")
    files = []
    for p in sorted(ws.rglob("*")):
        if p.is_file():
            rel = p.relative_to(ws)
            parts = rel.parts
            if any(d in _SKIP_DIRS | {".versions"} for d in parts):
                continue
            files.append(str(rel))

    snapshot = {
        "version_id": version_id,
        "label": label or f"Snapshot {ts}",
        "notes": notes,
        "file_count": len(files),
        "files": files,
        "status": status,
        "created_at": _now(),
    }

    try:
        (versions_dir / f"{version_id}.json").write_text(json.dumps(snapshot, indent=2))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "version_id": version_id, "snapshot": snapshot}
