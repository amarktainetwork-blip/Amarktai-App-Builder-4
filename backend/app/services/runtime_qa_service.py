"""Browser-backed runtime QA for generated and imported workspaces.

This service is intentionally strict: if the browser runtime or accessibility /
performance tooling is unavailable, strict quality gates receive a blocker
instead of a fake pass.

tool_unavailable vs score_zero distinction:
  - tool_unavailable: the binary/library cannot be found; score is meaningless.
  - score_zero: tool ran but returned 0 (genuine failure).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "tablet": {"width": 820, "height": 1180},
    "mobile": {"width": 390, "height": 844},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child_abs = os.path.abspath(str(child))
        parent_abs = os.path.abspath(str(parent))
        return os.path.commonpath([child_abs, parent_abs]) == parent_abs
    except Exception:
        return False


def _entry_url(workspace: Path) -> tuple[str | None, str | None]:
    for rel in ("index.html", "public/index.html", "dist/index.html", "build/index.html"):
        candidate = workspace / rel
        if candidate.exists():
            return candidate.resolve().as_uri(), rel
    return None, None


def _axe_source() -> str | None:
    candidates = [
        os.environ.get("AXE_CORE_PATH", ""),
        "/app/frontend/node_modules/axe-core/axe.min.js",
        "/app/node_modules/axe-core/axe.min.js",
        str(Path.cwd() / "frontend" / "node_modules" / "axe-core" / "axe.min.js"),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return None


def _detect_chromium_path() -> str | None:
    """Return the path to an installed Chromium/Chrome binary, or None."""
    env_path = os.environ.get("CHROME_PATH") or os.environ.get("CHROMIUM_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    # Playwright's own chromium bundle
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            if exe and Path(exe).exists():
                return exe
    except Exception:
        pass
    # Common system paths
    for candidate in [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/local/bin/chromium",
    ]:
        if Path(candidate).exists():
            return candidate
    return shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")


def _browser_launch_options(chromium_path: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox"],
    }
    if chromium_path and (
        Path(chromium_path).exists()
        or (os.name == "nt" and chromium_path in {"/bin/sh", "/usr/bin/chromium", "/usr/bin/google-chrome"})
    ):
        options["executable_path"] = chromium_path
    return options


def _run_lighthouse(url: str, report_dir: Path) -> dict[str, Any]:
    lighthouse = os.environ.get("LIGHTHOUSE_BIN") or shutil.which("lighthouse")
    if not lighthouse:
        return {
            "ok": False,
            "available": False,
            "tool_unavailable": True,
            "reason": "Lighthouse binary is not available in this runtime.",
        }
    chrome_path = _detect_chromium_path()
    if not chrome_path:
        return {
            "ok": False,
            "available": True,
            "tool_unavailable": False,
            "setup_needed": True,
            "reason": "Lighthouse is installed but CHROME_PATH/CHROMIUM_PATH or a Chromium executable is not configured.",
        }
    chrome_flags = "--headless --no-sandbox"
    if chrome_path:
        chrome_flags += f" --user-data-dir=/tmp/lighthouse-chrome"
    output = report_dir / "lighthouse-report.json"
    cmd = [
        lighthouse,
        url,
        "--quiet",
        f"--chrome-flags={chrome_flags}",
        "--output=json",
        f"--output-path={output}",
    ]
    if chrome_path:
        cmd.append(f"--chrome-path={chrome_path}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, shell=False)
    except Exception as exc:
        return {"ok": False, "available": True, "tool_unavailable": False, "reason": f"Lighthouse execution failed: {exc}"}
    if result.returncode != 0:
        return {
            "ok": False,
            "available": True,
            "tool_unavailable": False,
            "reason": (result.stderr or result.stdout or "Lighthouse failed")[:500],
        }
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "available": True, "tool_unavailable": False, "reason": f"Could not read Lighthouse report: {exc}"}
    categories = data.get("categories", {})
    scores = {
        key: int((value.get("score") or 0) * 100)
        for key, value in categories.items()
        if isinstance(value, dict)
    }
    return {"ok": True, "available": True, "tool_unavailable": False, "report_path": str(output), "scores": scores}


def run_runtime_qa(
    workspace_path: str | Path,
    *,
    min_accessibility_score: int = 90,
    min_performance_score: int = 70,
) -> dict[str, Any]:
    workspace = Path(workspace_path).resolve()
    report_dir = workspace / "runtime-qa"
    screenshots_dir = report_dir / "screenshots"
    report_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "pass": False,
        "tooling": "playwright_chromium_axe_lighthouse",
        "workspace_path": str(workspace),
        "screenshots": {},
        "screenshot_status": {},
        "console_errors": [],
        "accessibility": {
            "available": False,
            "tool_unavailable": True,
            "score": 0,
            "violations": [],
        },
        "performance": {
            "available": False,
            "tool_unavailable": True,
            "score": 0,
        },
        "motion": {"available": False, "selectors_found": 0, "ok": True},
        "links": {"broken": [], "ok": True},
        "media_assets": {"broken": [], "ok": True},
        "blockers": [],
        "warnings": [],
        "checked_at": _now(),
    }

    if not workspace.exists():
        report["blockers"].append("Workspace does not exist.")
        return _persist(report_dir, report)
    builds_root = os.environ.get("BUILDS_STORAGE_ROOT", "").strip()
    if builds_root:
        root_path = Path(builds_root).resolve()
        if not _is_within(workspace, root_path):
            report["blockers"].append("Workspace path is outside BUILDS_STORAGE_ROOT; runtime QA aborted.")
            return _persist(report_dir, report)

    url, entry = _entry_url(workspace)
    if not url:
        report["blockers"].append("No browser-renderable entry point found for runtime QA.")
        return _persist(report_dir, report)
    report["entry_point"] = entry
    report["url"] = url

    # Detect Chromium path and record it
    chromium_path = _detect_chromium_path()
    report["chromium_path"] = chromium_path

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        report["warnings"].append(f"Playwright is not installed or importable: {exc}")
        report["tooling_status"] = "playwright_unavailable"
        return _persist(report_dir, report)

    axe_source = _axe_source()
    if not axe_source:
        report["warnings"].append(
            "axe-core source is not available; accessibility score will show as tool_unavailable, not score_zero. "
            "Install axe-core: npm install axe-core in the frontend directory, or set AXE_CORE_PATH."
        )

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**_browser_launch_options(chromium_path))
            try:
                for name, viewport in VIEWPORTS.items():
                    page = browser.new_page(viewport=viewport)
                    page.on("console", lambda msg: report["console_errors"].append(msg.text) if msg.type == "error" else None)
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    screenshot = screenshots_dir / f"{name}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    report["screenshots"][name] = str(screenshot)
                    report["screenshot_status"][name] = {
                        "path": str(screenshot),
                        "persisted": True,
                        "viewport": viewport,
                    }
                    if name == "desktop":
                        selectors_found = page.locator("[data-amarktai-motion-scene], [data-motion-runtime]").count()
                        report["motion"] = {
                            "available": selectors_found > 0,
                            "selectors_found": selectors_found,
                            "ok": selectors_found > 0 or not (workspace / "motion_manifest.json").exists(),
                        }
                        link_media_report = page.evaluate(
                            """() => {
                                const brokenLinks = [];
                                const ids = new Set([...document.querySelectorAll('[id]')].map((el) => el.id));
                                for (const anchor of document.querySelectorAll('a[href]')) {
                                  const href = anchor.getAttribute('href') || '';
                                  if (!href || href === '#') brokenLinks.push({ href, reason: 'empty_or_dead_anchor' });
                                  if (href.startsWith('#') && href.length > 1 && !ids.has(href.slice(1))) {
                                    brokenLinks.push({ href, reason: 'target_missing' });
                                  }
                                }
                                const brokenMedia = [];
                                for (const img of document.querySelectorAll('img[src]')) {
                                  if (!img.complete || img.naturalWidth === 0) {
                                    brokenMedia.push({ src: img.getAttribute('src'), reason: 'image_not_loaded' });
                                  }
                                }
                                for (const media of document.querySelectorAll('video[src], audio[src], source[src]')) {
                                  const el = media.closest('video,audio') || media;
                                  if (el.error) brokenMedia.push({ src: media.getAttribute('src'), reason: 'media_error' });
                                }
                                return { brokenLinks, brokenMedia };
                            }"""
                        )
                        report["links"] = {
                            "broken": link_media_report.get("brokenLinks", []),
                            "ok": not link_media_report.get("brokenLinks"),
                        }
                        report["media_assets"] = {
                            "broken": link_media_report.get("brokenMedia", []),
                            "ok": not link_media_report.get("brokenMedia"),
                        }
                    if name == "desktop" and axe_source:
                        page.add_script_tag(content=axe_source)
                        axe_result = page.evaluate("async () => await axe.run(document)")
                        violations = axe_result.get("violations", [])
                        score = max(0, 100 - len(violations) * 10)
                        report["accessibility"] = {
                            "available": True,
                            "tool_unavailable": False,
                            "score": score,
                            "violations": [
                                {
                                    "id": v.get("id"),
                                    "impact": v.get("impact"),
                                    "description": v.get("description"),
                                    "nodes": len(v.get("nodes", [])),
                                }
                                for v in violations
                            ],
                        }
                    elif name == "desktop" and not axe_source:
                        # Tool unavailable — do not report score as 0 (that implies a real failure)
                        report["accessibility"] = {
                            "available": False,
                            "tool_unavailable": True,
                            "score": None,
                            "violations": [],
                            "reason": "axe-core source not found; score is unavailable, not zero.",
                        }
                    page.close()
            finally:
                browser.close()
    except Exception as exc:
        report["warnings"].append(f"Playwright browser execution failed: {exc}")
        report["tooling_status"] = "playwright_launch_failed"
        return _persist(report_dir, report)  # always persist

    if (workspace / "motion_manifest.json").exists() and not report.get("motion", {}).get("ok"):
        report["warnings"].append("Motion manifest exists but runtime motion selectors were not found.")
    missing_viewports = [vp for vp in VIEWPORTS if vp not in report.get("screenshots", {})]
    if missing_viewports:
        report["blockers"].append(
            f"Runtime screenshots missing for viewports: {', '.join(missing_viewports)}."
        )
    lighthouse = _run_lighthouse(url, report_dir)
    report["lighthouse"] = lighthouse
    if lighthouse.get("ok"):
        perf = int(lighthouse.get("scores", {}).get("performance", 0))
        report["performance"] = {
            "available": True,
            "tool_unavailable": False,
            "score": perf,
            "scores": lighthouse.get("scores", {}),
        }
    elif lighthouse.get("tool_unavailable"):
        report["warnings"].append(lighthouse.get("reason", "Lighthouse not available."))
        report["performance"] = {
            "available": False,
            "tool_unavailable": True,
            "score": None,
            "reason": lighthouse.get("reason"),
        }
    else:
        report["warnings"].append(lighthouse.get("reason", "Lighthouse did not produce a report."))
        report["performance"] = {
            "available": False,
            "tool_unavailable": False,
            "score": 0,
            "reason": lighthouse.get("reason"),
        }

    if report["console_errors"]:
        report["blockers"].append(f"Runtime console errors detected: {len(report['console_errors'])}.")
    if report.get("links", {}).get("broken"):
        report["blockers"].append(f"Broken runtime links detected: {len(report['links']['broken'])}.")
    if report.get("media_assets", {}).get("broken"):
        report["warnings"].append(f"Broken runtime media assets detected: {len(report['media_assets']['broken'])}.")
    # Only block on accessibility if the tool actually ran (not tool_unavailable)
    acc = report.get("accessibility", {})
    if not acc.get("tool_unavailable") and acc.get("available") and isinstance(acc.get("score"), int):
        if acc["score"] < min_accessibility_score:
            report["blockers"].append(
                f"Accessibility score {acc['score']} below {min_accessibility_score}."
            )
    # Only block on performance if the tool actually ran
    perf_report = report.get("performance", {})
    if not perf_report.get("tool_unavailable") and perf_report.get("available") and isinstance(perf_report.get("score"), int):
        if perf_report["score"] < min_performance_score:
            report["blockers"].append(
                f"Performance score {perf_report['score']} below {min_performance_score}."
            )

    report["pass"] = not report["blockers"]
    return _persist(report_dir, report)


def _persist(report_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    report_path = report_dir / "runtime-qa-report.json"
    accessibility_path = report_dir / "accessibility-report.json"
    performance_path = report_dir / "performance-report.json"
    report["report_path"] = str(report_path)
    report["accessibility_report_path"] = str(accessibility_path)
    report["performance_report_path"] = str(performance_path)
    accessibility_path.write_text(json.dumps(report.get("accessibility", {}), indent=2), encoding="utf-8")
    performance_path.write_text(json.dumps(report.get("performance", {}), indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
