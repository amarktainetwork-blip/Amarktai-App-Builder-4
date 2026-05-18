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
from app.services.tier_service import is_premium, normalize_quality_tier


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


def get_build_contract(mode: str | None, *, prompt: str = "", quality_tier: str = "standard") -> BuildContract:
    normalized = normalize_contract_mode(mode)
    quality_tier = normalize_quality_tier(quality_tier)
    project_type = infer_project_type(normalized)
    build_mode = infer_build_mode(normalized)
    required = tuple(get_required_files(project_type, build_mode, prompt, {}))
    forbidden: tuple[str, ...] = ()
    manifests: list[str] = ["amarktai.project.json", "preview-manifest.json"]
    runtime_artifacts: list[str] = []
    if project_type == "static-site":
        forbidden = tuple(sorted(STATIC_FORBIDDEN_FILES))
    if is_premium(quality_tier):
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


def is_static_preview_ready_workspace(workspace: str | Path, mode: str | None, *, prompt: str = "") -> bool:
    ws = Path(workspace).resolve()
    contract = get_build_contract(mode, prompt=prompt, quality_tier="standard")
    if contract.project_type != "static-site":
        return False
    if not all((ws / rel).exists() for rel in ("index.html", "styles.css")):
        return False
    preview_manifest = ws / "preview-manifest.json"
    if preview_manifest.exists():
        try:
            data = json.loads(preview_manifest.read_text(encoding="utf-8"))
            entry = data.get("entry") or (data.get("entry_candidates") or [""])[0]
            status = str(data.get("status") or "").lower()
            if (entry == "index.html" or (ws / str(entry)).exists()) and status in {"ready", "built", "ok", "preview_ready"}:
                return True
        except Exception:
            return True
    project_manifest = ws / "amarktai.project.json"
    if project_manifest.exists():
        try:
            data = json.loads(project_manifest.read_text(encoding="utf-8"))
            preview = data.get("preview") if isinstance(data.get("preview"), dict) else {}
            entry = preview.get("entry") or data.get("preview_entry")
            if entry == "index.html" or (entry and (ws / str(entry)).exists()):
                return True
        except Exception:
            pass
    return False


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
    allow_static_runtime_warnings: bool = False,
    allow_static_media_fallback_warnings: bool = False,
) -> list[str]:
    """Return final filesystem-level blockers shared by API, dashboard, and finalize paths."""
    ws = Path(workspace).resolve()
    quality_tier = normalize_quality_tier(quality_tier)
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
        media_warning_only = False
        if allow_static_media_fallback_warnings and is_static_preview_ready_workspace(ws, mode, prompt=prompt):
            manifest_path = ws / "media_manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    media_warning_only = (
                        manifest.get("status") == "fallback"
                        and manifest.get("reason") == "no_relevant_media_found"
                    )
                except Exception:
                    media_warning_only = False
        if not (ws / "media_manifest.json").exists():
            blockers.append("Missing media_manifest.json.")
        media_dir = ws / "media"
        asset_count = 0
        if media_dir.exists():
            asset_count = len([
                p for p in media_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
            ])
        if asset_count < 3 and not media_warning_only:
            blockers.append(f"Expected at least 3 persisted media assets; found {asset_count}.")
    if motion_required and not (ws / "motion_manifest.json").exists():
        blockers.append("Missing motion_manifest.json.")
    runtime_warning_only = (
        runtime_required
        and allow_static_runtime_warnings
        and is_static_preview_ready_workspace(ws, mode, prompt=prompt)
    )
    if runtime_required and not runtime_warning_only:
        for rel in contract.required_runtime_artifacts:
            if not (ws / rel).exists():
                blockers.append(f"Missing runtime QA artifact: {rel}")
    if is_premium(quality_tier):
        content_report_path = ws / "content_quality_report.json"
        if content_report_path.exists():
            try:
                report = json.loads(content_report_path.read_text(encoding="utf-8"))
                if not report.get("pass"):
                    blockers.append("Content quality report did not pass.")
            except Exception:
                blockers.append("content_quality_report.json is invalid.")
    return blockers

