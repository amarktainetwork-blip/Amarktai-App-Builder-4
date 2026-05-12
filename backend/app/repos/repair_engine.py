"""Imported repo repair pipeline for Amarktai App Builder — Phase 2E.

Rules:
- No blind rewrites — only targeted fixes.
- Every repair produces a diff summary.
- Every repair is reversible via checkpoints.
- Never mark a repo as fixed unless the repair actually succeeded.
"""
from __future__ import annotations

import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Diff helpers ──────────────────────────────────────────────────────────────

def generate_diff_summary_for_files(
    old_files: list[dict],
    new_files: list[dict],
    *,
    reason: str = "",
    risk_level: str = "low",
    tests_run: list[str] | None = None,
    build_result: str = "unknown",
    validation_result: str = "unknown",
    unresolved_risks: list[str] | None = None,
) -> dict:
    """Generate a structured diff summary for PR creation (Phase 2G).

    Args:
        old_files: Previous files as ``[{path, content}]``.
        new_files: New files as ``[{path, content}]``.
        reason: Human-readable description of why changes were made.
        risk_level: "low" | "medium" | "high".
        tests_run: List of test commands that were run.
        build_result: "success" | "failed" | "skipped".
        validation_result: "passed" | "failed" | "skipped".
        unresolved_risks: List of remaining risks.

    Returns:
        A ``DiffSummary`` dict suitable for PR bodies and version records.
    """
    old_map = {f["path"]: f.get("content", "") for f in old_files}
    new_map = {f["path"]: f.get("content", "") for f in new_files}

    old_paths = set(old_map)
    new_paths = set(new_map)

    added = sorted(new_paths - old_paths)
    deleted = sorted(old_paths - new_paths)
    modified = sorted(p for p in old_paths & new_paths if old_map[p] != new_map[p])

    # Build patch text for changed files
    file_diffs: list[dict] = []
    for path in modified:
        diff_lines = list(difflib.unified_diff(
            old_map[path].splitlines(),
            new_map[path].splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=3,
        ))
        file_diffs.append({
            "path": path,
            "action": "modified",
            "lines_added": sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++")),
            "lines_removed": sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---")),
            "diff": "\n".join(diff_lines[:80]),  # cap at 80 lines
        })
    for path in added:
        file_diffs.append({
            "path": path,
            "action": "added",
            "lines_added": len(new_map[path].splitlines()),
            "lines_removed": 0,
            "diff": "",
        })
    for path in deleted:
        file_diffs.append({
            "path": path,
            "action": "deleted",
            "lines_added": 0,
            "lines_removed": len(old_map[path].splitlines()),
            "diff": "",
        })

    total_added = sum(d["lines_added"] for d in file_diffs)
    total_removed = sum(d["lines_removed"] for d in file_diffs)

    markdown = _build_markdown_summary(
        added=added,
        deleted=deleted,
        modified=modified,
        file_diffs=file_diffs,
        reason=reason,
        risk_level=risk_level,
        tests_run=tests_run or [],
        build_result=build_result,
        validation_result=validation_result,
        unresolved_risks=unresolved_risks or [],
        total_added=total_added,
        total_removed=total_removed,
    )

    return {
        "files_changed": len(added) + len(deleted) + len(modified),
        "files_added": len(added),
        "files_deleted": len(deleted),
        "files_modified": len(modified),
        "lines_added": total_added,
        "lines_removed": total_removed,
        "reason": reason,
        "risk_level": risk_level,
        "tests_run": tests_run or [],
        "build_result": build_result,
        "validation_result": validation_result,
        "unresolved_risks": unresolved_risks or [],
        "file_diffs": file_diffs,
        "markdown": markdown,
    }


def _build_markdown_summary(
    *,
    added: list[str],
    deleted: list[str],
    modified: list[str],
    file_diffs: list[dict],
    reason: str,
    risk_level: str,
    tests_run: list[str],
    build_result: str,
    validation_result: str,
    unresolved_risks: list[str],
    total_added: int,
    total_removed: int,
) -> str:
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚪")
    build_emoji = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(build_result, "❓")
    val_emoji = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(validation_result, "❓")

    lines = [
        "## Amarktai App Builder — Change Summary\n",
        f"**Reason:** {reason or 'Automated repair/iteration'}\n",
        f"**Risk level:** {risk_emoji} {risk_level.capitalize()}\n",
        f"**Build:** {build_emoji} {build_result.capitalize()}  |  "
        f"**Validation:** {val_emoji} {validation_result.capitalize()}\n",
        f"\n**Files changed:** {len(added) + len(deleted) + len(modified)}  "
        f"(+{total_added} / -{total_removed} lines)\n",
    ]

    if added:
        lines += ["\n### Added files", *[f"- `{p}`" for p in added]]
    if deleted:
        lines += ["\n### Deleted files", *[f"- `{p}`" for p in deleted]]
    if modified:
        lines += ["\n### Modified files", *[f"- `{p}`" for p in modified]]

    if tests_run:
        lines += ["\n### Tests run", *[f"- `{t}`" for t in tests_run]]
    else:
        lines.append("\n_No tests were run for this change._")

    if unresolved_risks:
        lines += ["\n### ⚠️ Unresolved risks", *[f"- {r}" for r in unresolved_risks]]

    return "\n".join(lines)


# ── Checkpoint helpers ─────────────────────────────────────────────────────────

async def create_checkpoint(
    db,
    project_id: str,
    files: list[dict],
    memory: dict | None = None,
    validation: dict | None = None,
    preview_state: dict | None = None,
    label: str = "pre-repair",
) -> str:
    """Persist a checkpoint snapshot before a repair or iteration.

    Returns the checkpoint_id.
    """
    checkpoint_id = str(uuid.uuid4())
    await db.project_checkpoints.insert_one({
        "_id": checkpoint_id,
        "checkpoint_id": checkpoint_id,
        "project_id": project_id,
        "label": label,
        "file_snapshot": files,
        "memory_snapshot": memory or {},
        "validation_snapshot": validation or {},
        "preview_state": preview_state or {},
        "created_at": _now(),
    })
    return checkpoint_id


async def get_checkpoint(db, project_id: str, checkpoint_id: str) -> dict | None:
    return await db.project_checkpoints.find_one(
        {"checkpoint_id": checkpoint_id, "project_id": project_id},
        {"_id": 0},
    )


async def list_checkpoints(db, project_id: str) -> list[dict]:
    docs = await db.project_checkpoints.find(
        {"project_id": project_id},
        {"_id": 0, "file_snapshot": 0},
    ).sort("created_at", -1).to_list(50)
    return list(docs)


# ── Stack detection ────────────────────────────────────────────────────────────

_STACK_INDICATORS = {
    "vite": ["vite.config.js", "vite.config.ts", "vite.config.mjs"],
    "next": ["next.config.js", "next.config.ts", "next.config.mjs"],
    "cra": ["react-scripts"],
    "express": ["express"],
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django", "manage.py"],
    "tailwind": ["tailwind.config.js", "tailwind.config.ts"],
    "typescript": [".ts", ".tsx"],
    "prisma": ["prisma/schema.prisma", "prisma\\schema.prisma"],
    "docker": ["docker-compose.yml", "docker-compose.yaml", "Dockerfile"],
    "postgres": ["pg", "postgres", "postgresql"],
    "mongodb": ["mongoose", "mongodb"],
    "mariadb": ["mariadb", "mysql2", "mysql"],
    "pwa": ["manifest.json", "service-worker"],
}


def detect_extended_stack(files: list[dict]) -> dict:
    """Detect the full technology stack from a file set.

    Returns a ``stack_detection.json``-compatible dict.
    """
    by_path = {f["path"]: f.get("content", "") for f in files}
    paths = set(by_path.keys())

    detected: list[str] = []
    flags: dict[str, bool] = {}

    # Read package.json dependencies
    pkg_data: dict[str, Any] = {}
    for p in paths:
        if p.endswith("package.json") and "node_modules" not in p:
            try:
                pkg_data = json.loads(by_path[p])
            except Exception:
                pass
            break

    all_deps: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        all_deps.update(pkg_data.get(section, {}).keys())

    scripts: dict[str, str] = pkg_data.get("scripts", {})
    all_scripts_str = " ".join(scripts.values())

    # Vite
    has_vite = (
        any(re.search(r"vite\.config\.(js|ts|mjs)$", p) for p in paths)
        or "vite" in all_deps
        or "vite" in all_scripts_str
    )
    if has_vite:
        detected.append("vite")
        flags["vite"] = True

    # Next.js
    has_next = (
        any(re.search(r"next\.config\.(js|ts|mjs)$", p) for p in paths)
        or "next" in all_deps
        or "next" in all_scripts_str
    )
    if has_next:
        detected.append("next")
        flags["next"] = True

    # CRA
    has_cra = "react-scripts" in all_deps
    if has_cra:
        detected.append("cra")
        flags["cra"] = True

    # Express
    if "express" in all_deps:
        detected.append("express")
        flags["express"] = True

    # React (generic)
    if "react" in all_deps and "react-dom" in all_deps:
        if not (has_vite or has_next or has_cra):
            detected.append("react")
        flags["react"] = True

    # Tailwind
    has_tw = (
        any(re.search(r"tailwind\.config\.(js|ts)$", p) for p in paths)
        or "tailwindcss" in all_deps
    )
    if has_tw:
        detected.append("tailwind")
        flags["tailwind"] = True

    # TypeScript
    has_ts = (
        any(p.endswith((".ts", ".tsx")) for p in paths)
        or "typescript" in all_deps
        or any(p.endswith("tsconfig.json") for p in paths)
    )
    if has_ts:
        detected.append("typescript")
        flags["typescript"] = True

    # Prisma
    if any("prisma" in p for p in paths) or "prisma" in all_deps:
        detected.append("prisma")
        flags["prisma"] = True

    # Python frameworks
    py_content = " ".join(by_path[p] for p in paths if p.endswith(".py"))
    if "from fastapi import" in py_content or "import fastapi" in py_content.lower():
        detected.append("fastapi")
        flags["fastapi"] = True
    if "manage.py" in paths or "from django" in py_content or "django.conf" in py_content:
        detected.append("django")
        flags["django"] = True
    if "from flask import" in py_content or "import flask" in py_content.lower():
        detected.append("flask")
        flags["flask"] = True

    # Databases
    if any(k in all_deps for k in ("mongoose", "mongodb")):
        detected.append("mongodb")
        flags["mongodb"] = True
    if any(k in all_deps for k in ("mariadb", "mysql2", "mysql")):
        detected.append("mariadb")
        flags["mariadb"] = True
    if any(k in all_deps for k in ("pg", "postgres", "postgresql")):
        detected.append("postgres")
        flags["postgres"] = True

    # Docker
    has_docker = any(
        p in paths for p in ("docker-compose.yml", "docker-compose.yaml", "Dockerfile")
    )
    if has_docker:
        detected.append("docker")
        flags["docker"] = True

    # Static HTML
    has_static = any(p.endswith(".html") for p in paths)
    if has_static and not any(k in detected for k in ("vite", "next", "cra", "react")):
        detected.append("static")
        flags["static"] = True

    # PWA
    has_sw = any(re.search(r"service.?worker\.(js|ts)$", p, re.I) for p in paths)
    has_mf = any(p.endswith("manifest.json") for p in paths)
    if has_sw and has_mf:
        detected.append("pwa")
        flags["pwa"] = True

    # Derive commands from detected stack
    install_cmd, build_cmd, preview_cmd, test_cmd = _derive_commands(detected, scripts, flags)

    return {
        "detected": detected,
        "flags": flags,
        "install_command": install_cmd,
        "build_command": build_cmd,
        "preview_command": preview_cmd,
        "test_command": test_cmd,
        "repair_strategy": _repair_strategy(detected),
        "total_files": len(files),
        "has_package_json": bool(pkg_data),
        "package_manager": _detect_package_manager(paths),
    }


def _detect_package_manager(paths: set[str]) -> str:
    if "yarn.lock" in paths:
        return "yarn"
    if "pnpm-lock.yaml" in paths:
        return "pnpm"
    if "package-lock.json" in paths:
        return "npm"
    if any(p.endswith("package.json") for p in paths):
        return "npm"
    if any(p.endswith("requirements.txt") for p in paths):
        return "pip"
    return "unknown"


def _derive_commands(
    detected: list[str],
    scripts: dict[str, str],
    flags: dict[str, bool],
) -> tuple[str, str, str, str]:
    """Derive install/build/preview/test commands from the detected stack."""
    install = "npm install"
    build = scripts.get("build", "npm run build") if scripts else "npm run build"
    preview = scripts.get("dev", scripts.get("start", "npm run dev")) if scripts else "npm run dev"
    test = scripts.get("test", "npm test") if scripts else "npm test"

    if flags.get("fastapi") or flags.get("flask") or flags.get("django"):
        install = "pip install -r requirements.txt"
        build = "echo 'No build step for Python apps'"
        if flags.get("fastapi"):
            preview = "uvicorn main:app --reload"
        elif flags.get("django"):
            preview = "python manage.py runserver"
        else:
            preview = "flask run"
        test = "pytest"

    return install, build, preview, test


def _repair_strategy(detected: list[str]) -> str:
    if "next" in detected:
        return "next-repair"
    if "vite" in detected:
        return "vite-repair"
    if "cra" in detected:
        return "cra-repair"
    if any(f in detected for f in ("fastapi", "flask", "django")):
        return "python-repair"
    if "static" in detected:
        return "static-repair"
    return "generic-repair"


# ── Repair Engine ─────────────────────────────────────────────────────────────

class RepairEngine:
    """Targeted repair pipeline for imported repos.

    Rules:
    - No blind rewrites.
    - Every repair is atomic and produces a diff summary.
    - Failed repairs do not overwrite working code.
    """

    def __init__(self, db, project_id: str):
        self.db = db
        self.project_id = project_id

    async def create_repair_plan(
        self,
        files: list[dict],
        profile: dict,
    ) -> dict:
        """Analyse a repo profile and produce a repair plan.

        Args:
            files:   Current project files.
            profile: Repo profile from ``analyze_repo_profile``.

        Returns:
            A repair plan with ``tasks``, ``risk_level``, and ``strategy``.
        """
        stack_info = detect_extended_stack(files)
        tasks: list[dict] = []
        risk_level = "low"

        # Missing package.json scripts
        pkg_data: dict[str, Any] = {}
        for f in files:
            if f.get("path", "").endswith("package.json") and "node_modules" not in f.get("path", ""):
                try:
                    pkg_data = json.loads(f.get("content", "{}"))
                except Exception:
                    pass
                break
        existing_scripts: dict[str, str] = pkg_data.get("scripts", {})
        if stack_info["has_package_json"] and not existing_scripts.get("build"):
            tasks.append({
                "id": str(uuid.uuid4()),
                "type": "add_build_script",
                "description": "Add missing build script to package.json",
                "risk": "low",
                "reversible": True,
            })

        # Broken imports (detect from profile)
        broken = profile.get("broken_imports", [])
        for imp in broken[:10]:  # cap
            tasks.append({
                "id": str(uuid.uuid4()),
                "type": "fix_import",
                "description": f"Fix broken import: {imp}",
                "risk": "low",
                "reversible": True,
            })

        # Missing env vars
        missing_env = profile.get("missing_env", [])
        if missing_env:
            tasks.append({
                "id": str(uuid.uuid4()),
                "type": "create_env_example",
                "description": "Create .env.example with required environment variables",
                "risk": "low",
                "reversible": True,
            })
            risk_level = "medium"

        # Syntax errors
        syntax_errors = profile.get("syntax_errors", [])
        if syntax_errors:
            for err in syntax_errors[:5]:
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "fix_syntax",
                    "description": f"Fix syntax error: {err}",
                    "risk": "medium",
                    "reversible": True,
                })
            risk_level = "medium"

        return {
            "project_id": self.project_id,
            "tasks": tasks,
            "task_count": len(tasks),
            "risk_level": risk_level,
            "strategy": stack_info["repair_strategy"],
            "stack": stack_info["detected"],
            "created_at": _now(),
        }

    async def apply_repairs(
        self,
        files: list[dict],
        plan: dict,
    ) -> tuple[list[dict], list[str], list[str]]:
        """Apply targeted repairs from a repair plan.

        Returns:
            - ``new_files``: the patched file set
            - ``applied``:   list of applied task descriptions
            - ``skipped``:   list of skipped task descriptions
        """
        new_files = [dict(f) for f in files]
        applied: list[str] = []
        skipped: list[str] = []

        for task in plan.get("tasks", []):
            task_type = task.get("type", "")
            desc = task.get("description", "")

            if task_type == "create_env_example":
                existing = {f["path"] for f in new_files}
                if ".env.example" not in existing:
                    new_files.append({
                        "path": ".env.example",
                        "content": "# Required environment variables\n# Copy to .env and fill in values\n\n",
                        "language": "text",
                    })
                    applied.append(desc)
                else:
                    skipped.append(f"{desc} (already exists)")

            elif task_type == "add_build_script":
                for i, f in enumerate(new_files):
                    if f["path"] == "package.json":
                        try:
                            pkg = json.loads(f["content"])
                            scripts = pkg.setdefault("scripts", {})
                            changed = False
                            if "build" not in scripts:
                                scripts["build"] = "vite build"
                                changed = True
                            if "dev" not in scripts and "start" not in scripts:
                                scripts["dev"] = "vite"
                                changed = True
                            if changed:
                                new_files[i] = {**f, "content": json.dumps(pkg, indent=2)}
                                applied.append(desc)
                            else:
                                skipped.append(f"{desc} (scripts already present)")
                        except json.JSONDecodeError:
                            skipped.append(f"{desc} (could not parse package.json)")
                        break
                else:
                    skipped.append(f"{desc} (package.json not found)")

            else:
                # Generic tasks: record as applied but make no file changes
                # (actual repair requires AI — this is the deterministic pass)
                skipped.append(f"{desc} (requires AI repair pass)")

        return new_files, applied, skipped
