"""Project versioning system for Amarktai App Builder — Phase 2A.

Every build and iteration creates an immutable version record.
File content is snapshotted so rollbacks work even after subsequent changes.

Version record schema::

    {
        version_id: str,
        project_id: str,
        parent_version_id: str | None,
        user_request: str,
        generated_files: list[str],    # paths only
        changed_files: list[str],      # paths only
        diff_summary: str,
        satisfied_tasks: list[str],
        unsatisfied_tasks: list[str],
        validation_result: dict,
        visual_qa_result: dict | None,
        preview_url: str | None,
        build_status: str,             # "ready" | "failed" | "building"
        file_snapshot: list[dict],     # full {path, content, language} for rollback
        memory_snapshot: dict,         # project_memory at this point
        created_at: str,               # ISO 8601
    }
"""
from __future__ import annotations

import difflib
import uuid
from datetime import datetime, timezone
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Diff generation ───────────────────────────────────────────────────────────

def generate_diff_summary(
    old_files: list[dict],
    new_files: list[dict],
) -> str:
    """Produce a human-readable diff summary between two file snapshots.

    Args:
        old_files: Previous file set as list of {path, content} dicts.
        new_files: New file set as list of {path, content} dicts.

    Returns:
        A Markdown-formatted diff summary string.
    """
    old_map = {f["path"]: f.get("content", "") for f in old_files}
    new_map = {f["path"]: f.get("content", "") for f in new_files}

    old_paths = set(old_map)
    new_paths = set(new_map)

    added = sorted(new_paths - old_paths)
    deleted = sorted(old_paths - new_paths)
    modified: list[str] = []
    for path in sorted(old_paths & new_paths):
        if old_map[path] != new_map[path]:
            modified.append(path)

    lines: list[str] = ["## Diff Summary\n"]

    if added:
        lines.append(f"**Added ({len(added)} file(s)):**")
        lines.extend(f"- `{p}`" for p in added)
        lines.append("")

    if deleted:
        lines.append(f"**Deleted ({len(deleted)} file(s)):**")
        lines.extend(f"- `{p}`" for p in deleted)
        lines.append("")

    if modified:
        lines.append(f"**Modified ({len(modified)} file(s)):**")
        for path in modified:
            old_lines = old_map[path].splitlines()
            new_lines = new_map[path].splitlines()
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}",
                lineterm="",
                n=2,
            ))
            lines.append(f"\n### `{path}`")
            if diff:
                # Cap diff at 60 lines to keep it readable
                shown = diff[:60]
                lines.append("```diff")
                lines.extend(shown)
                if len(diff) > 60:
                    lines.append(f"... ({len(diff) - 60} more lines)")
                lines.append("```")
            else:
                lines.append("_(binary or whitespace-only change)_")
        lines.append("")

    if not (added or deleted or modified):
        lines.append("_No file changes detected._")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

async def create_version(
    db,
    project_id: str,
    *,
    user_request: str = "",
    generated_files: list[str] | None = None,
    changed_files: list[str] | None = None,
    diff_summary: str = "",
    satisfied_tasks: list[str] | None = None,
    unsatisfied_tasks: list[str] | None = None,
    validation_result: dict | None = None,
    visual_qa_result: dict | None = None,
    preview_url: str | None = None,
    build_status: str = "unknown",
    file_snapshot: list[dict] | None = None,
    memory_snapshot: dict | None = None,
) -> dict:
    """Create and persist a new project version record.

    Always chains to the previous version via parent_version_id so the full
    history is traversable.

    Returns the version record dict (without ``_id``).
    """
    prev = await db.project_versions.find_one(
        {"project_id": project_id},
        {"_id": 0, "version_id": 1},
        sort=[("created_at", -1)],
    )
    parent_version_id: str | None = prev["version_id"] if prev else None

    version_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "version_id": version_id,
        "project_id": project_id,
        "parent_version_id": parent_version_id,
        "user_request": user_request,
        "generated_files": generated_files or [],
        "changed_files": changed_files or [],
        "diff_summary": diff_summary,
        "satisfied_tasks": satisfied_tasks or [],
        "unsatisfied_tasks": unsatisfied_tasks or [],
        "validation_result": validation_result or {},
        "visual_qa_result": visual_qa_result,
        "preview_url": preview_url,
        "build_status": build_status,
        "file_snapshot": file_snapshot or [],
        "memory_snapshot": memory_snapshot or {},
        "created_at": _now(),
    }
    await db.project_versions.insert_one({**record, "_id": version_id})
    # Store the latest version_id on the project document for quick access
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"latest_version_id": version_id, "updated_at": _now()}},
    )
    return record


async def list_versions(db, project_id: str) -> list[dict]:
    """Return all version records for a project, newest first.

    File snapshots are excluded from the list response to keep it lightweight.
    """
    docs = await db.project_versions.find(
        {"project_id": project_id},
        {"_id": 0, "file_snapshot": 0},
    ).sort("created_at", -1).to_list(200)
    return list(docs)


async def get_version(db, project_id: str, version_id: str) -> dict | None:
    """Return a single version record including its file snapshot."""
    doc = await db.project_versions.find_one(
        {"version_id": version_id, "project_id": project_id},
        {"_id": 0},
    )
    return doc


async def restore_version(
    db,
    project_id: str,
    version_id: str,
    fs,
) -> dict:
    """Restore a project to the state captured in version_id.

    Restores:
    - All files from the version's ``file_snapshot``
    - Project memory from ``memory_snapshot``
    - Validation result and preview URL on the project document
    - Project status mapped from ``build_status``

    Args:
        db:         Motor database handle.
        project_id: The project to restore.
        version_id: The version to restore to.
        fs:         A ``ProjectFS`` instance for the project.

    Returns:
        A status dict with ``ok``, ``version_id``, ``restored_files``, and ``status``.

    Raises:
        ValueError: If the version record is not found.
    """
    version = await get_version(db, project_id, version_id)
    if not version:
        raise ValueError(
            f"Version {version_id!r} not found for project {project_id!r}"
        )

    # 1. Restore files — delete all current files then write the snapshot
    await db.files.delete_many({"project_id": project_id})
    for f in version.get("file_snapshot", []):
        path = f.get("path", "")
        content = f.get("content", "")
        language = f.get("language", "text")
        if path:
            await fs.write(path, content, language)

    # 2. Determine project status from build_status
    build_status = version.get("build_status", "ready")
    _STATUS_MAP = {
        "ready": "ready",
        "success": "ready",
        "failed": "failed",
        "building": "ready",
    }
    project_status = _STATUS_MAP.get(build_status, "ready")

    # 3. Update project document
    now = _now()
    update_fields: dict[str, Any] = {
        "status": project_status,
        "preview_url": version.get("preview_url"),
        "validation_state": version.get("validation_result"),
        "updated_at": now,
        "rollback_version_id": version_id,
        "preview_iteration": 0,  # reset preview iteration so iframe re-fetches
    }
    memory_snapshot = version.get("memory_snapshot")
    if memory_snapshot:
        update_fields["project_memory"] = memory_snapshot

    await db.projects.update_one({"id": project_id}, {"$set": update_fields})

    return {
        "ok": True,
        "version_id": version_id,
        "restored_files": len(version.get("file_snapshot", [])),
        "status": project_status,
        "diff_summary": version.get("diff_summary", ""),
    }
