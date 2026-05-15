"""Central build contract service used by runtime build paths.

The lower-level implementation lives in `agents.build_contract` for backward
compatibility with older imports. This service is the application-facing source
of truth for build modes, forbidden files, deterministic repair, validation,
and final gate blockers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.build_contract import (
    STATIC_FORBIDDEN_FILES,
    enforce_static_contract_files,
    get_required_files,
    infer_build_mode,
    infer_project_type,
    validate_project_files,
)


MODE_ALIASES = {
    "static_landing_page": "landing_page",
    "static_multi_page_website": "website",
    "react_web_app": "web_app",
    "full_stack_app": "full_stack",
    "repo_workflow": "repo_fix",
}


@dataclass(frozen=True)
class BuildContract:
    mode: str
    project_type: str
    build_mode: str
    required_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    required_manifests: tuple[str, ...]
    required_runtime_artifacts: tuple[str, ...]


def normalize_contract_mode(mode: str | None) -> str:
    raw = (mode or "web_app").strip().lower().replace("-", "_")
    return MODE_ALIASES.get(raw, raw)


def get_build_contract(mode: str | None, *, prompt: str = "", quality_tier: str = "balanced") -> BuildContract:
    normalized = normalize_contract_mode(mode)
    project_type = infer_project_type(normalized)
    build_mode = infer_build_mode(normalized)
    required = tuple(get_required_files(project_type, build_mode, prompt, {}))
    forbidden: tuple[str, ...] = ()
    manifests: list[str] = ["amarktai.project.json", "preview-manifest.json"]
    runtime_artifacts: list[str] = []
    if project_type == "static-site":
        forbidden = tuple(sorted(STATIC_FORBIDDEN_FILES))
    if quality_tier == "premium":
        manifests.extend(["media_manifest.json", "motion_manifest.json"])
        runtime_artifacts.extend([
            "runtime-qa/runtime-qa-report.json",
            "runtime-qa/accessibility-report.json",
            "runtime-qa/performance-report.json",
            "runtime-qa/screenshots/desktop.png",
            "runtime-qa/screenshots/tablet.png",
            "runtime-qa/screenshots/mobile.png",
        ])
    return BuildContract(
        mode=normalized,
        project_type=project_type,
        build_mode=build_mode,
        required_files=required,
        forbidden_files=forbidden,
        required_manifests=tuple(dict.fromkeys(manifests)),
        required_runtime_artifacts=tuple(runtime_artifacts),
    )


def enforce_contract_files(project: dict[str, Any], prompt: str, plan: dict | None, files: list[dict]) -> tuple[list[dict], list[str]]:
    return enforce_static_contract_files(project, prompt, plan, files)


def validate_contract_files(project: dict[str, Any], files: list[dict], prompt: str = "", plan: dict | None = None) -> dict:
    return validate_project_files(project, files, prompt=prompt, plan=plan)


def final_gate_blockers(
    workspace: str | Path,
    *,
    mode: str | None,
    quality_tier: str,
    prompt: str = "",
    media_required: bool = False,
    motion_required: bool = False,
    runtime_required: bool = False,
) -> list[str]:
    """Return final filesystem-level blockers shared by API, dashboard, and finalize paths."""
    ws = Path(workspace).resolve()
    contract = get_build_contract(mode, prompt=prompt, quality_tier=quality_tier)
    blockers: list[str] = []
    if contract.project_type == "static-site":
        for rel in contract.forbidden_files:
            if (ws / rel).exists():
                blockers.append(f"Static contract forbids generated file: {rel}")
    for rel in contract.required_files:
        if not (ws / rel).exists():
            blockers.append(f"Missing required file: {rel}")
    if media_required:
        if not (ws / "media_manifest.json").exists():
            blockers.append("Missing media_manifest.json.")
        media_dir = ws / "media"
        asset_count = 0
        if media_dir.exists():
            asset_count = len([
                p for p in media_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
            ])
        if asset_count < 3:
            blockers.append(f"Expected at least 3 persisted media assets; found {asset_count}.")
    if motion_required and not (ws / "motion_manifest.json").exists():
        blockers.append("Missing motion_manifest.json.")
    if runtime_required:
        for rel in contract.required_runtime_artifacts:
            if not (ws / rel).exists():
                blockers.append(f"Missing runtime QA artifact: {rel}")
    if quality_tier == "premium":
        content_report_path = ws / "content_quality_report.json"
        if not content_report_path.exists():
            blockers.append("Missing content_quality_report.json.")
        else:
            try:
                report = json.loads(content_report_path.read_text(encoding="utf-8"))
                if not report.get("pass"):
                    blockers.append("Content quality report did not pass.")
            except Exception:
                blockers.append("content_quality_report.json is invalid.")
    return blockers

