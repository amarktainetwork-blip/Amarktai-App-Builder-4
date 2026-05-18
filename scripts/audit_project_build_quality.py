from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_workspace(root: Path, project_id: str) -> Path | None:
    candidates = [
        root / "generated" / project_id,
        root / "incomplete" / project_id,
        root / "releases" / project_id,
        root / "archive" / project_id,
        root / "archived" / project_id,
        root / project_id,
    ]
    for candidate in candidates:
        if candidate.exists():
            if candidate.is_dir() and (candidate / "index.html").exists():
                return candidate
            nested = [p for p in candidate.rglob("index.html") if p.is_file()]
            if nested:
                return nested[0].parent
    matches = [p.parent for p in root.rglob("index.html") if project_id in str(p)]
    return matches[0] if matches else None


def _files(ws: Path) -> list[str]:
    return sorted(str(p.relative_to(ws)).replace("\\", "/") for p in ws.rglob("*") if p.is_file())


def _html(ws: Path) -> str:
    for rel in ("index.html", "public/index.html"):
        path = ws / rel
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _sections(html: str) -> list[str]:
    out = []
    for match in re.finditer(r"<section(?P<attrs>[^>]*)>", html, re.IGNORECASE):
        attrs = match.group("attrs") or ""
        id_match = re.search(r"\bid=['\"]([^'\"]+)['\"]", attrs, re.IGNORECASE)
        class_match = re.search(r"\bclass=['\"]([^'\"]+)['\"]", attrs, re.IGNORECASE)
        value = id_match.group(1) if id_match else (class_match.group(1).split()[0] if class_match else "section")
        out.append(value)
    return out


def _assets_by_source(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    out = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        out.append({
            "source": asset.get("source") or asset.get("provider"),
            "provider": asset.get("provider") or asset.get("source"),
            "type": asset.get("media_type") or asset.get("type"),
            "section": asset.get("section") or "unassigned",
            "path": asset.get("path") or asset.get("url"),
            "status": asset.get("status"),
        })
    return out


def _anchor_validity(html: str) -> dict[str, Any]:
    ids = set(re.findall(r"\bid=['\"]([^'\"]+)['\"]", html, re.IGNORECASE))
    broken = []
    for href in re.findall(r"<a\b[^>]*href=['\"]([^'\"]*)['\"]", html, re.IGNORECASE):
        if href in {"", "#", "javascript:void(0)", "javascript:void(0);"}:
            broken.append({"href": href, "reason": "dead_anchor"})
        elif href.startswith("#") and href[1:] not in ids:
            broken.append({"href": href, "reason": "target_missing"})
    return {"ok": not broken, "broken": broken}


def audit_project(project_id: str, workspace_root: Path) -> dict[str, Any]:
    ws = _find_workspace(workspace_root, project_id)
    if not ws:
        return {
            "project_id": project_id,
            "workspace_path": None,
            "files": [],
            "final_verdict": "failed",
            "exact_blockers": [f"Workspace for project_id {project_id} was not found under {workspace_root}."],
        }

    html = _html(ws)
    manifest = _read_json(ws / "media_manifest.json")
    runtime_qa = _read_json(ws / "runtime-qa" / "runtime-qa-report.json")
    quality = _read_json(ws / "quality-report.json")
    content_quality = _read_json(ws / "content_quality_report.json")
    sections = _sections(html)
    expected_sections = [s for s in ["hero", "menu", "story", "gallery", "contact"] if s in " ".join(sections).lower() or s in html.lower()]
    alignment = manifest.get("section_alignment") or {}
    attempts = manifest.get("attempts") if isinstance(manifest.get("attempts"), list) else []
    provider_failures = [
        {
            "provider": item.get("provider"),
            "status": item.get("status"),
            "reason": item.get("reason") or item.get("error"),
        }
        for item in attempts
        if isinstance(item, dict) and item.get("ok") is False
    ]
    screenshots = runtime_qa.get("screenshots") or {}
    broken_media = (
        runtime_qa.get("media_assets", {}).get("broken")
        or [b for b in runtime_qa.get("blockers", []) if "broken runtime media" in str(b).lower()]
    )
    blockers = []
    if provider_failures:
        blockers.append("Provider execution failures were recorded.")
    if alignment.get("hero_only"):
        blockers.append("Media is aligned only to hero.")
    if quality.get("score") == 100 and (runtime_qa.get("pass") is False or broken_media or provider_failures):
        blockers.append("quality-report.json score is 100 despite runtime/provider failures.")
    if broken_media:
        blockers.append("Runtime QA detected broken media.")
    if "gallery" in expected_sections and "gallery" not in alignment.get("aligned_sections", []):
        blockers.append("Gallery was expected but has no aligned media.")

    return {
        "project_id": project_id,
        "workspace_path": str(ws),
        "files": _files(ws),
        "media_manifest_summary": {
            "status": manifest.get("status"),
            "asset_count": manifest.get("asset_count"),
            "premium_media_complete": manifest.get("premium_media_complete"),
            "fallback_used": manifest.get("fallback_used"),
            "runtime_call_failed": manifest.get("runtime_call_failed"),
            "rate_limited": manifest.get("rate_limited"),
            "section_alignment": alignment,
        },
        "media_assets_by_source_provider_type_section": _assets_by_source(manifest),
        "provider_attempt_failures": provider_failures,
        "section_list_from_index_html": sections,
        "missing_expected_sections": [s for s in expected_sections if s not in " ".join(sections).lower()],
        "media_injected_into_html": "data-amarktai-media-asset" in html,
        "hero_contains_media": bool(re.search(r"<section[^>]*(?:id|class)=['\"][^'\"]*hero[^'\"]*['\"][\s\S]*data-amarktai-media-asset", html, re.IGNORECASE)),
        "gallery_contains_media": bool(re.search(r"<section[^>]*(?:id|class)=['\"][^'\"]*gallery[^'\"]*['\"][\s\S]*data-amarktai-media-asset", html, re.IGNORECASE)),
        "video_background_layer": "data-amarktai-hero-background" in html and "<video" in html.lower(),
        "anchor_validity": _anchor_validity(html),
        "responsive_css": bool(re.search(r"<meta[^>]+name=['\"]viewport['\"]|@media\s*\(", html + "\n".join((ws / f).read_text(errors="replace") for f in ("styles.css",) if (ws / f).exists()), re.IGNORECASE)),
        "runtime_qa_status": {"pass": runtime_qa.get("pass"), "blockers": runtime_qa.get("blockers"), "warnings": runtime_qa.get("warnings")},
        "screenshot_presence": {name: bool(path) for name, path in screenshots.items()},
        "lighthouse_status": runtime_qa.get("performance") or runtime_qa.get("lighthouse"),
        "axe_core_status": runtime_qa.get("accessibility"),
        "broken_media": broken_media or [],
        "content_quality_score": content_quality.get("score") or quality.get("content_quality_report", {}).get("score"),
        "quality_report_score": quality.get("score"),
        "final_verdict": "pass" if quality.get("pass") and not blockers else "needs_attention",
        "exact_blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit generated project build quality evidence.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workspace-root", required=True)
    args = parser.parse_args()
    print(json.dumps(audit_project(args.project_id, Path(args.workspace_root)), indent=2))


if __name__ == "__main__":
    main()
