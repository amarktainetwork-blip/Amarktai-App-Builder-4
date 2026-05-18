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

from app.services.content_quality_service import check_content_quality
from app.services.build_contract_service import is_static_preview_ready_workspace
from app.services.runtime_qa_service import run_runtime_qa
from app.services.media_runtime_service import expected_media_sections, summarize_media_section_alignment

logger = logging.getLogger("amarktai.quality_gate")

# ── Patterns ──────────────────────────────────────────────────────────────────

_PLACEHOLDER_PATTERNS = [
    r"Lorem ipsum",
    r"placeholder text",
    r"Your Product",
    r"TODO:",
    r"FIXME:",
    r"Coming soon",
    r"Under construction",
    r"\bFeature One\b",
    r"broken\.jpg",
    r"placeholder\.[a-z0-9]{2,5}",
]

_AUTOMOTIVE_ONLY_FILES = {"finance.html", "inventory.html", "vehicle-detail.html"}
_AUTOMOTIVE_HINTS = re.compile(
    r"\b(auto|automotive|car|cars|vehicle|vehicles|dealership|dealer|inventory|finance|test drive)\b",
    re.IGNORECASE,
)
_STRICT_WARNING_BLOCKERS = {
    "placeholders",
    "dead_ctas",
    "responsive",
    "image_alt",
    "preview_manifest",
    "broken_assets",
    "template_contamination",
}

_OPTIONAL_RUNTIME_TOOLING = re.compile(
    r"axe-core|lighthouse|chrome_path|chromium|chrome executable|playwright browser execution failed|playwright traces",
    re.IGNORECASE,
)


def _runtime_blocker_can_warn_for_static(message: str, runtime_report: dict[str, Any]) -> bool:
    if _OPTIONAL_RUNTIME_TOOLING.search(message):
        return True
    if re.search(r"accessibility score \d+ below", message, re.IGNORECASE):
        return not bool(runtime_report.get("accessibility", {}).get("available"))
    if re.search(r"performance score \d+ below", message, re.IGNORECASE):
        return not bool(runtime_report.get("performance", {}).get("available"))
    if re.search(r"broken runtime (?:links|media assets) detected", message, re.IGNORECASE):
        return True
    return False


def _runtime_qa_can_warn_for_static(ws: Path, mode: str, prompt: str, runtime_report: dict[str, Any]) -> bool:
    """Static preview builds can be ready with QA warnings when only optional browser tooling is missing."""
    if not is_static_preview_ready_workspace(ws, mode, prompt=prompt):
        return False
    blockers = [str(b) for b in runtime_report.get("blockers", [])]
    if not blockers:
        return False
    return all(_runtime_blocker_can_warn_for_static(message, runtime_report) for message in blockers)


def _media_fallback_can_warn_for_static(ws: Path, mode: str, prompt: str) -> bool:
    if not is_static_preview_ready_workspace(ws, mode, prompt=prompt):
        return False
    manifest_path = ws / "media_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return manifest.get("status") == "fallback" and manifest.get("reason") == "no_relevant_media_found"

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


def _workspace_js(ws: Path) -> str:
    snippets: list[str] = []
    for path in _iter_source_files(ws, {".js", ".jsx", ".ts", ".tsx"}):
        try:
            snippets.append(path.read_text(errors="replace")[:100_000])
        except Exception:
            continue
    return "\n".join(snippets)


def _html_ids(content: str) -> set[str]:
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', content, re.IGNORECASE))


def _extract_attr(attrs: str, name: str) -> str:
    match = re.search(rf'\b{name}=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
    return match.group(1) if match else ""


def _has_form_wrapper(prefix: str) -> bool:
    return prefix.lower().rfind("<form") > prefix.lower().rfind("</form>")


def _button_has_runtime_handler(attrs: str, js: str) -> bool:
    if re.search(r"\bon(?:click|pointerdown|mousedown|submit)\s*=", attrs, re.IGNORECASE):
        return True
    label = " ".join([
        _extract_attr(attrs, "id"),
        _extract_attr(attrs, "class"),
        _extract_attr(attrs, "data-action"),
        _extract_attr(attrs, "data-target"),
        _extract_attr(attrs, "aria-label"),
    ]).strip()
    if not label:
        return False
    tokens = [token for token in re.split(r"[^a-zA-Z0-9_-]+", label) if len(token) >= 3]
    handler_terms = (
        "addEventListener" in js
        or "onclick" in js.lower()
        or "querySelector" in js
        or "getElementById" in js
    )
    if not handler_terms:
        return False
    return any(token in js for token in tokens)


def _button_is_control(attrs: str, js: str) -> bool:
    text = " ".join([
        _extract_attr(attrs, "id"),
        _extract_attr(attrs, "class"),
        _extract_attr(attrs, "aria-label"),
        _extract_attr(attrs, "data-role"),
    ]).lower()
    if re.search(r"\b(nav-toggle|menu-toggle|hamburger|carousel|testimonial|slider|dot|tab|accordion)\b", text):
        return _button_has_runtime_handler(attrs, js)
    return False


def _cta_target(ids: set[str], text: str, attrs: str) -> str:
    haystack = f"{text} {attrs}".lower()
    preferred: list[str]
    if re.search(r"gallery|look|view", haystack):
        preferred = ["gallery", "contact", "hero"]
    elif re.search(r"event|catering|private", haystack):
        preferred = ["events", "catering", "contact", "hero"]
    elif re.search(r"menu|product|pastr|sourdough|signature|order", haystack):
        preferred = ["signature", "menu", "pastries", "sourdough", "contact", "hero"]
    else:
        preferred = ["contact", "lead-capture", "hero"]
    for item in preferred:
        if item in ids:
            return f"#{item}"
    return "#hero"


def repair_static_dead_ctas(ws: Path, *, mode: str = "", prompt: str = "") -> dict[str, Any]:
    """Repair inert static CTAs before the strict quality gate evaluates them."""
    if not is_static_preview_ready_workspace(ws, mode, prompt=prompt):
        return {"changed": False, "files": [], "repairs": []}
    js = _workspace_js(ws)
    changed_files: list[str] = []
    repairs: list[dict[str, str]] = []
    for path in _iter_source_files(ws, {".html"}):
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        ids = _html_ids(original)
        html = original

        def anchor_repl(match: re.Match) -> str:
            attrs = match.group(1)
            body = match.group(2)
            href = _extract_attr(attrs, "href").strip().lower()
            if href not in {"", "#", "javascript:void(0)", "javascript:void(0);"}:
                return match.group(0)
            target = _cta_target(ids, re.sub(r"<[^>]+>", " ", body), attrs)
            new_attrs = re.sub(r'\bhref=["\'][^"\']*["\']', f'href="{target}"', attrs, flags=re.IGNORECASE)
            if "href=" not in new_attrs.lower():
                new_attrs = f' href="{target}"{new_attrs}'
            repairs.append({"file": str(path.relative_to(ws)), "kind": "anchor", "target": target})
            return f"<a{new_attrs}>{body}</a>"

        html = re.sub(r"<a\b([^>]*)>([\s\S]*?)</a>", anchor_repl, html, flags=re.IGNORECASE)

        def button_repl(match: re.Match) -> str:
            attrs = match.group(1)
            body = match.group(2)
            prefix = html[:match.start()]
            btn_type = _extract_attr(attrs, "type").lower()
            if btn_type == "submit" and _has_form_wrapper(prefix):
                return match.group(0)
            if _button_is_control(attrs, js) or _button_has_runtime_handler(attrs, js):
                return match.group(0)
            target = _cta_target(ids, re.sub(r"<[^>]+>", " ", body), attrs)
            cls = _extract_attr(attrs, "class")
            class_attr = f' class="{cls}"' if cls else ' class="button"'
            aria = _extract_attr(attrs, "aria-label")
            aria_attr = f' aria-label="{aria}"' if aria else ""
            repairs.append({"file": str(path.relative_to(ws)), "kind": "button", "target": target})
            return f"<a{class_attr}{aria_attr} href=\"{target}\">{body}</a>"

        html = re.sub(r"<button\b([^>]*)>([\s\S]*?)</button>", button_repl, html, flags=re.IGNORECASE)
        if html != original:
            path.write_text(html, encoding="utf-8")
            changed_files.append(str(path.relative_to(ws)))
    return {"changed": bool(changed_files), "files": changed_files, "repairs": repairs}


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
    js = _workspace_js(ws)
    hits: list[str] = []
    for f in ui_files[:50]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        if re.search(r'href=["\'](?:#|javascript:void\(0\);?)?["\']', content, re.IGNORECASE):
            hits.append(str(f.relative_to(ws)))
            continue
        for match in re.finditer(r"<button\b([^>]*)>", content, re.IGNORECASE):
            attrs = match.group(1)
            prefix = content[:match.start()]
            btn_type = _extract_attr(attrs, "type").lower()
            if btn_type == "submit" and _has_form_wrapper(prefix):
                continue
            if _button_is_control(attrs, js) or _button_has_runtime_handler(attrs, js):
                continue
            if "onClick" not in attrs:
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
    for name in candidates:
        path = ws / name
        if not path.exists():
            continue
        if name == "preview-manifest.json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entry = data.get("entry") or (data.get("entry_candidates") or [""])[0]
                if entry and not (ws / str(entry)).exists():
                    return {
                        "ok": False,
                        "blocker": False,
                        "warning": True,
                        "message": f"Preview manifest entry does not exist: {entry}",
                    }
            except Exception:
                pass
        return {"ok": True}
    project_manifest = ws / "amarktai.project.json"
    if project_manifest.exists():
        try:
            data = json.loads(project_manifest.read_text(encoding="utf-8"))
            preview = data.get("preview") if isinstance(data.get("preview"), dict) else {}
            entry = preview.get("entry") or data.get("preview_entry")
            if entry == "index.html" or (entry and (ws / str(entry)).exists()):
                return {"ok": True, "source": "amarktai.project.json"}
        except Exception:
            pass
    return {
        "ok": False,
        "blocker": False,
        "warning": True,
        "message": "No preview manifest found.",
        "suggestion": "Save preview-manifest.json or status.json with preview status and URL.",
    }


# ── Main gate ─────────────────────────────────────────────────────────────────

def check_broken_assets(ws: Path) -> dict[str, Any]:
    """Detect local image/video references that do not resolve in the workspace."""
    ui_files = _iter_source_files(ws, {".html", ".jsx", ".tsx", ".vue", ".svelte"})
    missing: list[str] = []
    for f in ui_files[:50]:
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        refs = re.findall(r"\b(?:src|poster)=['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
        for ref in refs:
            if not ref or ref.startswith(("http://", "https://", "data:", "#", "{", "/api/")):
                continue
            clean_ref = ref.split("#", 1)[0].split("?", 1)[0]
            if clean_ref.startswith("/"):
                clean_ref = clean_ref.lstrip("/")
            if not (ws / clean_ref).exists():
                missing.append(f"{f.relative_to(ws)} -> {ref}")
    if missing:
        return {
            "ok": False,
            "blocker": True,
            "message": f"Broken local media references found in {len(missing)} location(s).",
            "files": missing[:10],
            "suggestion": "Persist referenced media assets or update src/poster paths to existing files.",
        }
    return {"ok": True}


def check_template_contamination(ws: Path, *, prompt: str = "", mode: str = "") -> dict[str, Any]:
    """Prevent unrelated starter pages from leaking into non-automotive builds."""
    requested_automotive = bool(_AUTOMOTIVE_HINTS.search(f"{prompt} {mode}"))
    present = sorted(name for name in _AUTOMOTIVE_ONLY_FILES if (ws / name).exists())
    if present and not requested_automotive:
        return {
            "ok": False,
            "blocker": True,
            "message": "Automotive starter pages appeared in a non-automotive build.",
            "files": present,
            "suggestion": "Remove finance/inventory/vehicle-detail starter files unless the prompt requests automotive workflows.",
        }
    return {"ok": True, "files": present, "automotive_prompt": requested_automotive}


def check_media_manifest(ws: Path) -> dict[str, Any]:
    """Require persisted real media assets when media is mandatory."""
    for rel in ("media_manifest.json", "media-manifest.json", "media/manifest.json"):
        path = ws / rel
        if not path.exists():
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"ok": False, "blocker": True, "message": f"Media manifest {rel} is invalid JSON."}
        assets = manifest.get("assets") or manifest.get("items") or manifest.get("media") or []
        existing = []
        for item in assets:
            raw = item.get("path") or item.get("file") or item.get("url") if isinstance(item, dict) else str(item)
            if not raw or str(raw).startswith(("http://", "https://", "data:")):
                continue
            rel = str(raw).lstrip("/")
            if Path(rel).suffix.lower() == ".svg":
                continue
            if (ws / rel).exists():
                existing.append(raw)
        if len(existing) >= 3:
            return {"ok": True, "manifest": rel, "asset_count": len(existing)}
        return {"ok": False, "blocker": True, "message": f"Media manifest {rel} contains {len(existing)} existing local asset file(s); premium media builds require at least 3."}
    return {"ok": False, "blocker": True, "message": "Premium/media build requires persisted media_manifest.json with real asset files."}


def check_motion_manifest(ws: Path) -> dict[str, Any]:
    """Require motion manifest and source-level animation evidence."""
    manifest = next((rel for rel in ("motion_manifest.json", "motion-manifest.json") if (ws / rel).exists()), None)
    if not manifest:
        return {"ok": False, "blocker": True, "message": "Premium/motion build requires motion_manifest.json."}
    source_files = _iter_source_files(ws, {".html", ".css", ".js", ".jsx", ".ts", ".tsx"})
    combined = "\n".join(p.read_text(errors="replace")[:50000] for p in source_files[:50])
    if not re.search(r"gsap|three|@react-three/fiber|framer-motion|requestAnimationFrame|@keyframes|animation\s*:", combined, re.IGNORECASE):
        return {"ok": False, "blocker": True, "message": "Motion manifest exists but no motion implementation was found in source files."}
    return {"ok": True, "manifest": manifest}


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _combined_source_text(ws: Path) -> str:
    snippets = []
    for path in _iter_source_files(ws, {".html", ".css", ".js", ".jsx", ".tsx"}):
        try:
            snippets.append(path.read_text(encoding="utf-8", errors="replace")[:100_000])
        except Exception:
            continue
    return "\n".join(snippets)


def _is_premium_prompt(prompt: str, *, strict: bool, require_media: bool) -> bool:
    return bool(strict or require_media or re.search(r"\b(premium|cinematic|gallery|media|video|motion)\b", prompt or "", re.IGNORECASE))


def compute_premium_quality_score(
    ws: Path,
    *,
    prompt: str = "",
    runtime_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _read_json_file(ws / "media_manifest.json")
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    attempts = manifest.get("attempts") if isinstance(manifest.get("attempts"), list) else []
    source_text = _combined_source_text(ws)
    html_sections = re.findall(r"<section[^>]*(?:id|class)=['\"]([^'\"]+)['\"]", source_text, re.IGNORECASE)
    expected_sections = expected_media_sections(prompt, html_sections)
    alignment = manifest.get("section_alignment") or summarize_media_section_alignment(ws, assets, sections=expected_sections)
    runtime_report = runtime_report or _read_json_file(ws / "runtime-qa" / "runtime-qa-report.json")

    provider_failures = [a for a in attempts if a.get("ok") is False and a.get("provider") in {"genx", "qwen", "pixabay", "pixabay_video"}]
    fallback_assets = [a for a in assets if a.get("source") in {"local_runtime_fallback", "css_svg_fallback"}]
    ai_assets = [a for a in assets if a.get("source") in {"genx", "qwen"}]
    visible_sections = set(alignment.get("aligned_sections") or [])
    missing_sections = sorted(set(expected_sections) - visible_sections)
    hero_background = "data-amarktai-hero-background" in source_text or "amarktai-hero-media-layer" in source_text
    gallery_media = "gallery" in visible_sections or "gallery" not in expected_sections
    responsive = bool(check_responsive(ws).get("ok"))
    generic_fallback = bool(re.search(r"Amarktai Builder runtime media|Amarktai media fallback|Local fallback asset", source_text, re.IGNORECASE))
    runtime_blockers = [str(item) for item in (runtime_report or {}).get("blockers", [])]
    runtime_warnings = [str(item) for item in (runtime_report or {}).get("warnings", [])]
    broken_media = bool((runtime_report or {}).get("media_assets", {}).get("broken")) or any("broken runtime media" in b.lower() for b in runtime_blockers)
    lighthouse_setup = any("lighthouse" in item.lower() for item in runtime_blockers + runtime_warnings) and not (runtime_report or {}).get("performance", {}).get("available")
    axe_setup = any("axe-core" in item.lower() for item in runtime_blockers + runtime_warnings) and not (runtime_report or {}).get("accessibility", {}).get("available")
    motion_depth = bool(re.search(r"<video\b|data-motion-runtime|data-amarktai-motion-scene|requestAnimationFrame|@keyframes|animation\s*:", source_text, re.IGNORECASE))

    sub_scores = {
        "provider_execution": 100 if not provider_failures else 30,
        "media_persistence": min(100, len(assets) * 34),
        "media_section_alignment": 100 if not missing_sections and not alignment.get("hero_only") else max(0, 100 - 25 * len(missing_sections) - (35 if alignment.get("hero_only") else 0)),
        "hero_media_depth": 100 if hero_background else 35,
        "gallery_media": 100 if gallery_media else 0,
        "runtime_qa": 100 if (runtime_report or {}).get("pass") else (40 if (axe_setup or lighthouse_setup) and not broken_media else 0),
        "responsive_css": 100 if responsive else 0,
        "brand_specificity": 20 if generic_fallback else 100,
        "motion_video_treatment": 100 if motion_depth else 45,
        "final_preview_integrity": 0 if broken_media else 100,
    }
    score = int(sum(sub_scores.values()) / len(sub_scores))
    blockers: list[str] = []
    if provider_failures and fallback_assets and manifest.get("status") in {"ready", "ai_generated", "stock", "fallback"}:
        blockers.append("Provider media execution failed and fallback assets were used; premium media cannot be reported as complete.")
    if missing_sections:
        blockers.append(f"Expected media sections missing: {', '.join(missing_sections)}.")
    if alignment.get("hero_only") and len(expected_sections) > 1:
        blockers.append("All media is assigned to hero while premium sections require visual coverage.")
    if "gallery" in expected_sections and not gallery_media:
        blockers.append("Gallery was requested but has no visible media.")
    if broken_media:
        blockers.append("Broken runtime media assets detected.")
    if generic_fallback:
        blockers.append("Generic fallback media wording is visible in the generated project.")
    if not hero_background:
        blockers.append("Hero media is not injected as a background/visual layer.")
    if not responsive:
        blockers.append("Responsive CSS or viewport support is missing.")
    if score < int(os.environ.get("PREMIUM_QUALITY_MIN_SCORE", "75")):
        blockers.append(f"premium_quality_score {score} is below threshold.")
    warnings = []
    if axe_setup:
        warnings.append("axe-core is setup-needed; accessibility runtime score is unavailable.")
    if lighthouse_setup:
        warnings.append("Lighthouse/Chrome is setup-needed or misconfigured; performance runtime score is unavailable.")
    return {
        "ok": not blockers,
        "score": score,
        "sub_scores": sub_scores,
        "blocker": bool(blockers),
        "message": "; ".join(blockers) if blockers else "Premium quality evidence passed.",
        "blockers": blockers,
        "warnings": warnings,
        "expected_sections": expected_sections,
        "section_alignment": alignment,
        "provider_failures": provider_failures,
        "fallback_asset_count": len(fallback_assets),
        "ai_asset_count": len(ai_assets),
    }


def run_quality_gate(
    workspace_path: str | Path,
    *,
    strict: bool = False,
    require_runtime: bool = False,
    require_media: bool = False,
    require_motion: bool = False,
    prompt: str = "",
    mode: str = "",
) -> dict[str, Any]:
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

    cta_repair = repair_static_dead_ctas(ws, mode=mode, prompt=prompt)
    static_preview_ready = is_static_preview_ready_workspace(ws, mode, prompt=prompt)

    checks = {
        "entry_point":  check_entry_point(ws),
        "placeholders": check_placeholders(ws),
        "secrets":      check_secrets(ws),
        "env_example":  check_env_example(ws),
        "readme":       check_readme(ws),
        "responsive":   check_responsive(ws),
        "image_alt":    check_image_alt(ws),
        "dead_ctas":    check_dead_ctas(ws),
        "broken_assets": check_broken_assets(ws),
        "template_contamination": check_template_contamination(ws, prompt=prompt, mode=mode),
        "content_quality": check_content_quality(ws, prompt=prompt, strict=strict),
        "preview_manifest": check_preview_manifest(ws),
    }
    if strict or require_media:
        checks["media_manifest"] = check_media_manifest(ws)
        if (
            not checks["media_manifest"].get("ok")
            and _media_fallback_can_warn_for_static(ws, mode, prompt)
        ):
            checks["media_manifest"] = {
                **checks["media_manifest"],
                "ok": False,
                "blocker": False,
                "warning": True,
                "message": "No relevant stock media was found; static preview uses the CSS/SVG visual system and finalize remains locked.",
                "finalize_locked": True,
            }
    if strict or require_motion:
        checks["motion_manifest"] = check_motion_manifest(ws)
    runtime_report: dict[str, Any] | None = None
    if strict or require_runtime:
        import asyncio
        import concurrent.futures

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                runtime_report = executor.submit(run_runtime_qa, ws).result()
        except RuntimeError:
            runtime_report = run_runtime_qa(ws)

        runtime_warn_only = _runtime_qa_can_warn_for_static(ws, mode, prompt, runtime_report)
        checks["runtime_qa"] = {
            "ok": bool(runtime_report.get("pass")),
            "blocker": not runtime_warn_only,
            "warning": runtime_warn_only,
            "message": (
                "Runtime QA tooling warning: "
                if runtime_warn_only else ""
            ) + ("; ".join(runtime_report.get("blockers", [])) or "Runtime QA failed."),
            "report_path": runtime_report.get("report_path"),
            "finalize_locked": runtime_warn_only,
        }
        if runtime_warn_only:
            runtime_report["policy"] = "static_preview_ready_with_runtime_warnings"
            runtime_report["finalize_locked"] = True

    if _is_premium_prompt(prompt, strict=strict, require_media=require_media):
        premium_quality = compute_premium_quality_score(ws, prompt=prompt, runtime_report=runtime_report)
        checks["premium_quality"] = {
            "ok": premium_quality["ok"],
            "blocker": bool(premium_quality.get("blockers")),
            "warning": bool(premium_quality.get("warnings")) and not premium_quality["ok"],
            "message": premium_quality.get("message", ""),
            "score": premium_quality["score"],
            "report": premium_quality,
        }

    blockers = []
    warnings = []
    suggestions = []

    for check_name, result in checks.items():
        if (
            static_preview_ready
            and check_name == "broken_assets"
            and not result.get("ok")
            and result.get("blocker")
        ):
            result = {
                **result,
                "blocker": False,
                "warning": True,
                "finalize_locked": True,
                "message": (
                    str(result.get("message") or "Broken local media references found.")
                    + " Static preview remains available; finalize remains locked until media references are repaired."
                ),
            }
            checks[check_name] = result
        if not result.get("ok"):
            if result.get("blocker"):
                blockers.append({
                    "check": check_name,
                    "message": result.get("message", ""),
                    "files": result.get("files", []),
                })
            elif result.get("warning"):
                payload = {
                    "check": check_name,
                    "message": result.get("message", ""),
                    "files": result.get("files", []),
                }
                if strict and check_name in _STRICT_WARNING_BLOCKERS:
                    if static_preview_ready and check_name == "broken_assets":
                        warnings.append(payload)
                    else:
                        blockers.append(payload)
                else:
                    warnings.append(payload)
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
        "strict": strict,
        "runtime_qa": runtime_report,
        "premium_quality_score": checks.get("premium_quality", {}).get("score"),
        "premium_quality_report": checks.get("premium_quality", {}).get("report"),
        "content_quality_report": checks.get("content_quality", {}).get("report"),
        "repair_suggestions": suggestions,
        "workspace_path": str(ws),
        "checked_at": _now(),
    }
    if cta_repair.get("changed"):
        report["fixes_applied"].append({
            "type": "dead_cta_repair",
            "files": cta_repair.get("files", []),
            "repairs": cta_repair.get("repairs", []),
        })
    try:
        (ws / "quality-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report
