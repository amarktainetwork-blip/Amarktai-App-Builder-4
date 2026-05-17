"""Truthful gates for Repo Workbench PR creation."""
from __future__ import annotations

from typing import Any


PASSING = {"passed", "pass", "success", "succeeded", "ok", True, None}


def diff_has_changes(diff_summary: dict[str, Any] | None) -> bool:
    if not isinstance(diff_summary, dict):
        return False
    if int(diff_summary.get("files_changed") or 0) > 0:
        return True
    return any(
        item.get("action") in {"added", "modified", "deleted"}
        for item in diff_summary.get("file_diffs", [])
        if isinstance(item, dict)
    )


def repo_pr_blockers(
    project: dict[str, Any],
    *,
    allow_failing_pr: bool = False,
) -> list[str]:
    """Return blockers that must prevent normal Repo Workbench PR creation."""
    blockers: list[str] = []
    if not project.get("github"):
        blockers.append("Project is not linked to a GitHub repository.")
    diff_summary = project.get("diff_summary") or {}
    if not diff_has_changes(diff_summary):
        blockers.append("No changed files are available; empty pull requests are blocked.")
    validation = project.get("validation_state") or {}
    validation_status = validation.get("status") or validation.get("overall")
    if validation_status and validation_status not in PASSING and not allow_failing_pr:
        blockers.append(f"Validation status is {validation_status}; pass validation or explicitly create a draft/failing PR.")
    coverage = project.get("coverage_score") or {}
    if coverage and coverage.get("qualityOk") is False and not allow_failing_pr:
        blockers.append("Quality coverage failed; normal PR creation is blocked.")
    return blockers
