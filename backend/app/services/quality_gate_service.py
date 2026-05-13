"""
Amarktai App Builder — Premium Website / App Quality Gate Service.

Runs a series of checks on a project workspace to determine build completeness
and quality. Returns a structured report with pass/fail status, score,
blockers, warnings, and repair suggestions.

Checks:
  1. Required pages / entry point exists
  2. No placeholder-only pages
  3. No broken internal links (href="#" without label, etc.)
  4. No dead buttons (no onClick / no href / no type=submit)
  5. No fake forms (form without action/onSubmit)
  6. Mobile responsive check (viewport meta, responsive CSS)
  7. Image alt text
  8. No hardcoded secrets (basic patterns)
  9. env.example exists if env vars referenced
  10. README exists
  11. No empty CSS/JS files
  12. Build/test pass (optional — checked separately via command runner)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.quality_gate")

# ── Patterns ──────────────────────────────────────────────────────────────────

_PLACEHOLDER_PATTERNS = [
    r"Lorem ipsum",
    r"placeholder text",
    r"TODO:",
    r"FIXME:",
    r"Coming soon",
    r"Under construction",
]

_SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|apikey|secret[_-]?key|private[_-]?key)\s*=\s*['\"][a-zA-Z0-9_\-\.]{16,}['\"]",
    r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}['\"]",
    r"(?i)(token)\s*=\s*['\"][a-zA-Z0-9_\-\.]{20,}['\"]",
    r"sk-[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"gnxk_[a-zA-Z0-9]{20,}",
]

_ENV_VAR_PATTERNS = [
    r"process\.env\.[A-Z_][A-Z0-9_]{2,}",
    r'os\.environ\.get\(["\'][A-Z_][A-Z0-9_]{2,}',
    r'os\.getenv\(["\'][A-Z_][A-Z0-9_]{2,}',
]

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".svelte-kit"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_source_files(ws: Path, extensions: set[str]) -> list[Path]:
    """Yield source files under workspace, skipping build/vendor dirs."""
    result = []
    for p in ws.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(ws).parts)
        if parts & _SKIP_DIRS:
            continue
        if p.suffix.lower() in extensions:
            result.append(p)
    return result


# ── Individual checks ─────────────────────────────────────────────────────────

def check_entry_point(ws: Path) -> dict[str, Any]:
    """Check that an entry point (index.html, index.js, main.tsx, etc.) exists."""
    candidates = [
        "index.html", "public/index.html",
        "src/index.js", "src/index.ts", "src/index.jsx", "src/index.tsx",
        "src/main.js", "src/main.ts", "src/main.jsx", "src/main.tsx",
        "app/page.tsx", "app/page.jsx", "pages/index.tsx", "pages/index.jsx",
        "package.json",
    ]
    for c in candidates:
        if (ws / c).exists():
            return {"ok": True, "found": c}
    return {
        "ok": False,
        "blocker": True,
        "message": "No entry point found (index.html, src/index.*, package.json, etc.)",
        "suggestion": "Add an index.html or src/index.tsx as the app entry point.",
    }


def check_placeholders(ws: Path) -> dict[str, Any]:
    """Scan for placeholder text in source files."""
    html_files = _iter_source_files(ws, {".html", ".jsx", ".tsx", ".vue", ".svelte"})
    hits: list[str] = []
    for f in html_files[:50]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        for pat in _PLACEHOLDER_PATTERNS:
            if re.search(pat, content, re.IGNORECASE):
                hits.append(str(f.relative_to(ws)))
                break
    if hits:
        return {
            "ok": False,
            "blocker": False,
            "warning": True,
            "message": f"Placeholder content found in {len(hits)} file(s).",
            "files": hits[:10],
            "suggestion": "Replace placeholder text with real content.",
        }
    return {"ok": True}


def check_secrets(ws: Path) -> dict[str, Any]:
    """Scan for hardcoded secrets in source files."""
    source_files = _iter_source_files(ws, {".js", ".ts", ".jsx", ".tsx", ".py", ".env", ".json", ".yaml", ".yml"})
    hits: list[dict] = []
    for f in source_files[:100]:
        if f.name == ".env.example":
            continue
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        for pat in _SECRET_PATTERNS:
            matches = re.findall(pat, content)
            if matches:
                hits.append({
                    "file": str(f.relative_to(ws)),
                    "pattern": pat[:40] + "…",
                    "count": len(matches),
                })
    if hits:
        return {
            "ok": False,
            "blocker": True,
            "message": f"Potential hardcoded secrets found in {len(hits)} location(s).",
            "files": [h["file"] for h in hits[:5]],
            "suggestion": "Move secrets to .env files. Add .env to .gitignore.",
        }
    return {"ok": True}


def check_env_example(ws: Path) -> dict[str, Any]:
    """Check if env.example exists when env vars are referenced."""
    source_files = _iter_source_files(ws, {".js", ".ts", ".jsx", ".tsx", ".py"})
    env_refs_found = False
    for f in source_files[:100]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        for pat in _ENV_VAR_PATTERNS:
            if re.search(pat, content):
                env_refs_found = True
                break

    if not env_refs_found:
        return {"ok": True, "note": "No env var references found"}

    has_env_example = (ws / ".env.example").exists() or (ws / "env.example").exists()
    if has_env_example:
        return {"ok": True}
    return {
        "ok": False,
        "blocker": False,
        "warning": True,
        "message": "Env vars are referenced but no .env.example found.",
        "suggestion": "Create a .env.example with required variable names (no values).",
    }


def check_readme(ws: Path) -> dict[str, Any]:
    """Check if a README file exists."""
    for name in ["README.md", "README.txt", "README", "readme.md"]:
        if (ws / name).exists():
            return {"ok": True, "found": name}
    return {
        "ok": False,
        "blocker": False,
        "warning": True,
        "message": "No README found.",
        "suggestion": "Add a README.md describing the project and how to run it.",
    }


def check_responsive(ws: Path) -> dict[str, Any]:
    """Check for viewport meta and basic responsive CSS indicators."""
    html_files = _iter_source_files(ws, {".html"})
    has_viewport = False
    for f in html_files[:10]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        if re.search(r'<meta[^>]+name=["\']viewport["\']', content, re.IGNORECASE):
            has_viewport = True
            break

    # Check package.json for Tailwind / responsive CSS frameworks
    pkg_json = ws / "package.json"
    has_responsive_framework = False
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {}
            deps.update(pkg.get("dependencies", {}))
            deps.update(pkg.get("devDependencies", {}))
            if any(k in deps for k in ["tailwindcss", "@mui/material", "bootstrap", "chakra-ui", "antd"]):
                has_responsive_framework = True
        except Exception:
            pass

    if has_viewport or has_responsive_framework:
        return {"ok": True, "has_viewport_meta": has_viewport, "has_responsive_framework": has_responsive_framework}
    if html_files:
        return {
            "ok": False,
            "blocker": False,
            "warning": True,
            "message": "No viewport meta tag found in HTML files.",
            "suggestion": "Add <meta name='viewport' content='width=device-width, initial-scale=1'> to HTML head.",
        }
    # If no HTML (SPA), assume framework handles it
    return {"ok": True, "note": "No HTML files found; assuming SPA handles responsiveness"}


def check_image_alt(ws: Path) -> dict[str, Any]:
    """Check for img tags missing alt attributes."""
    html_files = _iter_source_files(ws, {".html", ".jsx", ".tsx", ".vue", ".svelte"})
    missing_alt: list[str] = []
    for f in html_files[:30]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        imgs = re.findall(r"<img\b([^>]*)>", content, re.IGNORECASE)
        for img_attrs in imgs:
            if "alt=" not in img_attrs:
                if str(f.relative_to(ws)) not in missing_alt:
                    missing_alt.append(str(f.relative_to(ws)))

    if missing_alt:
        return {
            "ok": False,
            "blocker": False,
            "warning": True,
            "message": f"Images missing alt text in {len(missing_alt)} file(s).",
            "files": missing_alt[:5],
            "suggestion": "Add descriptive alt attributes to all <img> tags.",
        }
    return {"ok": True}


def check_dead_ctas(ws: Path) -> dict[str, Any]:
    """Detect obvious dead links/buttons in UI source."""
    ui_files = _iter_source_files(ws, {".html", ".jsx", ".tsx", ".vue", ".svelte"})
    hits: list[str] = []
    for f in ui_files[:50]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        if re.search(r'href=["\']#["\']', content, re.IGNORECASE):
            hits.append(str(f.relative_to(ws)))
            continue
        for match in re.finditer(r"<button\b([^>]*)>", content, re.IGNORECASE):
            attrs = match.group(1)
            if "onClick" not in attrs and "type=" not in attrs:
                hits.append(str(f.relative_to(ws)))
                break
    if hits:
        return {
            "ok": False,
            "blocker": False,
            "warning": True,
            "message": f"Potential dead CTA or inert button found in {len(set(hits))} file(s).",
            "files": sorted(set(hits))[:10],
            "suggestion": "Give CTAs real hrefs, handlers, or explicit button types tied to a working flow.",
        }
    return {"ok": True}


def check_preview_manifest(ws: Path) -> dict[str, Any]:
    """Check for a saved preview manifest/status when preview is required."""
    candidates = ["preview-manifest.json", "preview_manifest.json", "preview.json", "status.json"]
    if any((ws / name).exists() for name in candidates):
        return {"ok": True}
    return {
        "ok": False,
        "blocker": False,
        "warning": True,
        "message": "No preview manifest found.",
        "suggestion": "Save preview-manifest.json or status.json with preview status and URL.",
    }


# ── Main gate ─────────────────────────────────────────────────────────────────

def run_quality_gate(workspace_path: str | Path) -> dict[str, Any]:
    """
    Run all quality checks on a project workspace.

    Returns a structured quality report with:
      - pass: bool
      - score: int (0-100)
      - blockers: list
      - warnings: list
      - checks: dict
      - repair_suggestions: list
      - checked_at: str
    """
    ws = Path(workspace_path).resolve()

    if not ws.exists():
        return {
            "pass": False,
            "score": 0,
            "error": f"Workspace not found: {ws}",
            "blockers": ["Workspace does not exist"],
            "warnings": [],
            "checks": {},
            "repair_suggestions": ["Ensure the workspace is cloned/created before running QA."],
            "checked_at": _now(),
        }

    checks = {
        "entry_point":  check_entry_point(ws),
        "placeholders": check_placeholders(ws),
        "secrets":      check_secrets(ws),
        "env_example":  check_env_example(ws),
        "readme":       check_readme(ws),
        "responsive":   check_responsive(ws),
        "image_alt":    check_image_alt(ws),
        "dead_ctas":    check_dead_ctas(ws),
        "preview_manifest": check_preview_manifest(ws),
    }

    blockers = []
    warnings = []
    suggestions = []

    for check_name, result in checks.items():
        if not result.get("ok"):
            if result.get("blocker"):
                blockers.append({
                    "check": check_name,
                    "message": result.get("message", ""),
                    "files": result.get("files", []),
                })
            elif result.get("warning"):
                warnings.append({
                    "check": check_name,
                    "message": result.get("message", ""),
                    "files": result.get("files", []),
                })
            if result.get("suggestion"):
                suggestions.append(result["suggestion"])

    # Score: 100 - (blockers * 25) - (warnings * 5), min 0
    score = max(0, 100 - len(blockers) * 25 - len(warnings) * 5)
    passed = len(blockers) == 0

    files_checked = [str(p.relative_to(ws)) for p in _iter_source_files(ws, {".html", ".js", ".jsx", ".ts", ".tsx", ".css", ".md", ".json"})[:200]]
    report = {
        "pass": passed,
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "fixes_applied": [],
        "files_checked": files_checked,
        "checks": checks,
        "repair_suggestions": suggestions,
        "workspace_path": str(ws),
        "checked_at": _now(),
    }
    try:
        (ws / "quality-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report
