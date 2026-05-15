"""Content Director quality checks for generated builds.

This deterministic layer audits whether generated copy matches the prompt,
names the right product, covers requested capabilities, and avoids generic
filler. It writes `content_quality_report.json` and returns a gate result that
the runtime quality gate can block on.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any


GENERIC_COPY_PATTERNS = [
    r"\bLorem ipsum\b",
    r"\bYour Product\b",
    r"\bFeature One\b",
    r"\bFeature Two\b",
    r"\bComing Soon\b",
    r"\bUnder Construction\b",
    r"\bplaceholder\b",
    r"\bgeneric SaaS\b",
]

CAPABILITY_KEYWORDS = {
    "github": ("github", "repo", "pull request", "pr automation"),
    "media": ("media", "image", "video", "visual", "asset"),
    "voice_avatar": ("voice", "avatar", "audio"),
    "runtime_qa": ("runtime qa", "quality gate", "accessibility", "performance"),
    "agents": ("agent", "orchestration", "pipeline"),
    "deployment": ("deploy", "deployment", "production"),
    "preview": ("preview", "live preview"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text_files(workspace: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for ext in (".html", ".jsx", ".tsx", ".js", ".md"):
        for path in workspace.rglob(f"*{ext}"):
            if any(part in {"node_modules", ".git", "runtime-qa", "media"} for part in path.parts):
                continue
            try:
                files.append((str(path.relative_to(workspace)).replace("\\", "/"), path.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    return files[:80]


def _visible_text(raw: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[{}();<>=\"'`]+", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _infer_brand(prompt: str) -> str:
    quoted = re.findall(r"[\"“](.{3,80}?)[\"”]", prompt or "")
    if quoted:
        return quoted[0].strip()
    match = re.search(r"\bfor\s+([A-Z][A-Za-z0-9 ]{2,60})", prompt or "")
    return match.group(1).strip() if match else ""


def _requested_capabilities(prompt: str) -> list[str]:
    lower = (prompt or "").lower()
    requested: list[str] = []
    for capability, keywords in CAPABILITY_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            requested.append(capability)
    return requested


def _anchors_have_targets(raw_files: list[tuple[str, str]]) -> list[str]:
    combined = "\n".join(content for _, content in raw_files)
    ids = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", combined))
    broken: list[str] = []
    for path, content in raw_files:
        for href in re.findall(r"\bhref=[\"']#([^\"']+)[\"']", content):
            if href and href not in ids:
                broken.append(f"{path} -> #{href}")
    return broken


def _run_content_quality(
    raw_files: list[tuple[str, str]],
    *,
    prompt: str = "",
    context: dict[str, Any] | None = None,
    strict: bool = False,
    workspace: Path | None = None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    combined_visible = " ".join(_visible_text(content) for _, content in raw_files)
    combined_lower = combined_visible.lower()
    brand = (context or {}).get("brand_name") or _infer_brand(prompt)
    requested = _requested_capabilities(prompt)

    if not raw_files:
        blockers.append({"check": "content_files", "message": "No generated content files were available for Content Director audit."})

    generic_hits = [
        pattern for pattern in GENERIC_COPY_PATTERNS
        if re.search(pattern, combined_visible, re.IGNORECASE)
    ]
    if generic_hits:
        blockers.append({
            "check": "generic_copy",
            "message": "Generated copy contains placeholder or generic filler.",
            "patterns": generic_hits,
        })

    if brand and brand.lower() not in combined_lower:
        blockers.append({
            "check": "brand_alignment",
            "message": f"Generated page does not clearly describe the requested product: {brand}.",
        })

    missing_requested = [
        capability for capability in requested
        if not any(keyword in combined_lower for keyword in CAPABILITY_KEYWORDS[capability])
    ]
    if missing_requested:
        blockers.append({
            "check": "requested_capabilities",
            "message": "Generated copy is missing requested capability coverage.",
            "missing": missing_requested,
        })

    section_count = len(re.findall(r"<section\b|<h2\b|class=[\"'][^\"']*(?:section|panel|feature|workflow)", "\n".join(c for _, c in raw_files), re.IGNORECASE))
    if strict and section_count < 5:
        blockers.append({
            "check": "section_depth",
            "message": f"Premium content needs at least 5 meaningful sections; found {section_count}.",
        })
    elif section_count < 3:
        warnings.append({
            "check": "section_depth",
            "message": f"Generated content appears shallow; found {section_count} section signals.",
        })

    cta_count = len(re.findall(r"\b(?:Get started|Start|Build|Launch|Book|Request|Create|Deploy|Try)\b", combined_visible, re.IGNORECASE))
    if cta_count == 0:
        blockers.append({"check": "cta_quality", "message": "No clear CTA copy was found."})

    broken_anchors = _anchors_have_targets(raw_files)
    if broken_anchors:
        blockers.append({
            "check": "cta_navigation",
            "message": "Internal CTA/navigation anchors point to missing sections.",
            "files": broken_anchors[:10],
        })

    word_count = len(combined_visible.split())
    if strict and word_count < 180:
        blockers.append({"check": "content_depth", "message": f"Premium copy is too thin: {word_count} words."})

    score = max(0, 100 - len(blockers) * 25 - len(warnings) * 5)
    report = {
        "pass": not blockers,
        "score": score,
        "brand_name": brand,
        "audience": (context or {}).get("audience") or "",
        "requested_capabilities": requested,
        "section_count": section_count,
        "cta_count": cta_count,
        "word_count": word_count,
        "blockers": blockers,
        "warnings": warnings,
        "files_checked": [path for path, _ in raw_files],
        "checked_at": _now(),
    }
    if workspace is not None:
        try:
            (workspace / "content_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:
            pass
    return report


def run_content_quality_check_for_files(
    files: list[dict[str, Any]],
    *,
    prompt: str = "",
    context: dict[str, Any] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    raw_files = [
        (str(item.get("path", "")), str(item.get("content", "")))
        for item in files
        if Path(str(item.get("path", ""))).suffix.lower() in {".html", ".jsx", ".tsx", ".js", ".md"}
    ]
    return _run_content_quality(raw_files, prompt=prompt, context=context, strict=strict)


def run_content_quality_check(
    workspace_path: str | Path,
    *,
    prompt: str = "",
    context: dict[str, Any] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    workspace = Path(workspace_path).resolve()
    if not workspace.exists():
        return {
            "pass": False,
            "score": 0,
            "blockers": [{"check": "workspace", "message": "Workspace does not exist."}],
            "warnings": [],
            "checked_at": _now(),
        }
    raw_files = _read_text_files(workspace)
    report = _run_content_quality(raw_files, prompt=prompt, context=context, strict=strict, workspace=workspace)
    try:
        (workspace / "content_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


def check_content_quality(workspace_path: str | Path, *, prompt: str = "", context: dict[str, Any] | None = None, strict: bool = False) -> dict[str, Any]:
    report = run_content_quality_check(workspace_path, prompt=prompt, context=context, strict=strict)
    return {
        "ok": bool(report.get("pass")),
        "blocker": strict,
        "warning": not strict and not report.get("pass"),
        "message": "; ".join(item.get("message", "") for item in report.get("blockers", [])[:3]) or "Content quality check passed.",
        "report_path": "content_quality_report.json",
        "report": report,
    }
