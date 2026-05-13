"""
Amarktai App Builder — Frontend Detection Service.

Detects the frontend framework, build tools, package manager, dev/build commands,
and output directories for an imported repository workspace.

Supports: Vite, React (CRA), Next.js, Vue, Nuxt, Svelte, SvelteKit, Angular,
          Astro, static HTML, and unknown fallback.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.frontend_detection")

# ── Root candidates to search ─────────────────────────────────────────────────

FRONTEND_ROOT_CANDIDATES = [
    ".",
    "frontend",
    "client",
    "app",
    "web",
    "apps/web",
    "packages/web",
    "src",
    "ui",
    "www",
]

# ── Framework detection ───────────────────────────────────────────────────────

FRAMEWORK_SIGNATURES: list[tuple[str, list[str], str]] = [
    # (framework_name, dep_keys_or_files, dev_command)
    ("nextjs",     ["next"],                           "next dev"),
    ("nuxt",       ["nuxt", "nuxt3"],                  "nuxt dev"),
    ("sveltekit",  ["@sveltejs/kit"],                  "vite dev"),
    ("svelte",     ["svelte"],                         "vite dev"),
    ("astro",      ["astro"],                          "astro dev"),
    ("angular",    ["@angular/core"],                  "ng serve"),
    ("vite",       ["vite"],                           "vite"),
    ("cra",        ["react-scripts"],                  "react-scripts start"),
    ("vue",        ["vue"],                            "vite"),
    ("react",      ["react"],                          "vite"),
]

OUTPUT_DIR_CANDIDATES = [".next", "dist", "build", "out", "public", ".svelte-kit"]


# ── Package manager detection ─────────────────────────────────────────────────

def detect_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists():
        return "npm"
    if (root / "package.json").exists():
        return "npm"  # default
    return "none"


# ── Main detection ────────────────────────────────────────────────────────────

def detect_frontend(workspace_path: str | Path) -> dict[str, Any]:
    """
    Detect the frontend setup in the given workspace.

    Returns a dict with:
      - detected: bool
      - framework: str
      - frontend_root: str (relative path)
      - package_manager: str
      - dev_command: str
      - build_command: str
      - preview_command: str
      - install_command: str
      - output_dir: str
      - port_hint: int | None
      - static_html: bool
      - has_package_json: bool
      - detection_notes: list[str]
    """
    ws = Path(workspace_path).resolve()
    notes: list[str] = []

    if not ws.exists():
        return {
            "detected": False,
            "error": f"Workspace path does not exist: {ws}",
            "detection_notes": [],
        }

    # Search for frontend root
    for candidate in FRONTEND_ROOT_CANDIDATES:
        candidate_path = (ws / candidate).resolve()
        if not candidate_path.exists():
            continue
        # Ensure it's inside the workspace
        try:
            candidate_path.relative_to(ws)
        except ValueError:
            continue

        pkg_json = candidate_path / "package.json"
        if pkg_json.exists():
            result = _analyse_package_json(candidate_path, candidate, notes)
            if result["detected"]:
                return result

    # Check for static HTML at root or common locations
    for html_candidate in [".", "public", "static", "html"]:
        html_path = (ws / html_candidate).resolve()
        if not html_path.exists():
            continue
        try:
            html_path.relative_to(ws)
        except ValueError:
            continue
        if (html_path / "index.html").exists():
            notes.append(f"Found static index.html at {html_candidate}/")
            return {
                "detected": True,
                "framework": "static",
                "frontend_root": html_candidate,
                "package_manager": "none",
                "dev_command": None,
                "build_command": None,
                "preview_command": None,
                "install_command": None,
                "output_dir": html_candidate,
                "port_hint": None,
                "static_html": True,
                "has_package_json": False,
                "detection_notes": notes,
            }

    notes.append("No frontend detected in common root candidates.")
    return {
        "detected": False,
        "framework": "unknown",
        "frontend_root": ".",
        "package_manager": "none",
        "dev_command": None,
        "build_command": None,
        "preview_command": None,
        "install_command": None,
        "output_dir": "dist",
        "port_hint": None,
        "static_html": False,
        "has_package_json": False,
        "detection_notes": notes,
    }


def _analyse_package_json(
    root: Path, relative_root: str, notes: list[str]
) -> dict[str, Any]:
    """Analyse a package.json to determine framework and commands."""
    pkg_json_path = root / "package.json"
    try:
        pkg = json.loads(pkg_json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        notes.append(f"Could not parse package.json: {exc}")
        return {"detected": False, "detection_notes": notes}

    deps: dict[str, str] = {}
    deps.update(pkg.get("dependencies", {}))
    deps.update(pkg.get("devDependencies", {}))

    scripts: dict[str, str] = pkg.get("scripts", {})

    framework = "unknown"
    dev_command: str | None = None
    build_command: str | None = None
    preview_command: str | None = None

    for fw_name, dep_keys, default_dev in FRAMEWORK_SIGNATURES:
        if any(k in deps for k in dep_keys):
            framework = fw_name
            # Prefer scripts from package.json
            dev_command = _pick_script(scripts, ["dev", "start", "serve", "develop"], default_dev)
            build_command = _pick_script(scripts, ["build"], "npm run build")
            preview_command = _pick_script(scripts, ["preview", "serve"], None)
            notes.append(f"Detected framework: {fw_name} in {relative_root}/")
            break

    if framework == "unknown":
        # Fallback: if package.json exists with scripts, assume generic JS
        if scripts:
            framework = "generic_js"
            dev_command = _pick_script(scripts, ["dev", "start", "serve"], None)
            build_command = _pick_script(scripts, ["build"], None)
            notes.append(f"Unknown framework but scripts found in {relative_root}/")
        else:
            return {"detected": False, "detection_notes": notes}

    pm = detect_package_manager(root)
    install_command = f"{pm} install" if pm != "none" else "npm install"

    # Output dir
    output_dir = _detect_output_dir(root, framework)

    # Port hint
    port_hint = _detect_port_hint(root, framework, scripts)

    return {
        "detected": True,
        "framework": framework,
        "frontend_root": relative_root,
        "package_manager": pm,
        "dev_command": dev_command,
        "build_command": build_command,
        "preview_command": preview_command,
        "install_command": install_command,
        "output_dir": output_dir,
        "port_hint": port_hint,
        "static_html": False,
        "has_package_json": True,
        "scripts": scripts,
        "dependencies_count": len(deps),
        "detection_notes": notes,
    }


def _pick_script(scripts: dict[str, str], candidates: list[str], default: str | None) -> str | None:
    for c in candidates:
        if c in scripts:
            return f"npm run {c}"
    return default


def _detect_output_dir(root: Path, framework: str) -> str:
    for d in OUTPUT_DIR_CANDIDATES:
        if (root / d).exists():
            return d
    # Framework-specific defaults
    defaults = {
        "nextjs": ".next",
        "cra": "build",
        "nuxt": ".nuxt",
        "sveltekit": ".svelte-kit",
    }
    return defaults.get(framework, "dist")


def _detect_port_hint(root: Path, framework: str, scripts: dict[str, str]) -> int | None:
    """Attempt to detect the dev server port from config files."""
    framework_defaults = {
        "nextjs": 3000,
        "cra": 3000,
        "vite": 5173,
        "vue": 5173,
        "react": 5173,
        "svelte": 5173,
        "sveltekit": 5173,
        "nuxt": 3000,
        "astro": 4321,
        "angular": 4200,
    }

    # Check vite.config.{js,ts}
    for vite_conf in ["vite.config.js", "vite.config.ts", "vite.config.mjs"]:
        vite_path = root / vite_conf
        if vite_path.exists():
            try:
                content = vite_path.read_text(errors="replace")
                m = re.search(r"port\s*:\s*(\d+)", content)
                if m:
                    return int(m.group(1))
            except Exception:
                pass

    # Check next.config.{js,ts,mjs}
    for next_conf in ["next.config.js", "next.config.ts", "next.config.mjs"]:
        next_path = root / next_conf
        if next_path.exists():
            return 3000

    return framework_defaults.get(framework)


def list_project_files(workspace_path: str | Path, max_files: int = 200) -> list[str]:
    """Return a sorted list of relative file paths in the workspace."""
    ws = Path(workspace_path).resolve()
    if not ws.exists():
        return []

    files = []
    for p in sorted(ws.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(ws))
            # Skip .git and node_modules
            parts = Path(rel).parts
            if ".git" in parts or "node_modules" in parts or "__pycache__" in parts:
                continue
            files.append(rel)
            if len(files) >= max_files:
                break
    return files
