"""
Preview Executor — Phase 2 + Phase 3 of the Amarktai App Builder go-live spec.

Generates a structured preview fallback object for imported repos based on the
detected repo profile.  For simple static repos it re-uses render_preview() to
produce an inlined HTML preview.  For everything else it produces an honest
fallback object so the frontend can show stack info, install/build/run commands,
env var requirements, and blockers instead of a blank panel.

The executor intentionally does NOT run npm install / vite build / docker-compose
on the server.  Running arbitrary install/build commands from user-supplied repos
is a significant security and resource risk.  Instead we return all the information
needed for the user to run the app locally or in CI, or for the system to prompt
the user about missing env vars.
"""
from __future__ import annotations

from typing import Any

from .preview import render_preview

# Valid JavaScript/Node package managers for command generation
_JS_PACKAGE_MANAGERS = frozenset({"npm", "yarn", "pnpm"})

# Max characters to truncate the prompt when generating PR titles
PR_PROMPT_TRUNCATE = 400


# ── Fallback object schema ────────────────────────────────────────────────────

def _fallback(
    reason: str,
    profile: dict,
    logs: list[str] | None = None,
) -> dict:
    """Build the canonical preview-fallback contract object."""
    return {
        "canPreview": False,
        "type": "repo-preview-fallback",
        "reason": reason,
        "detectedStack": list(profile.get("frameworks", [])),
        "languages": list(profile.get("languages", [])),
        "fileTree": list(profile.get("fileTree", [])),
        "routeMap": list(profile.get("routeMap", [])),
        "readmeExcerpt": profile.get("readmeExcerpt", ""),
        "installCommands": list(profile.get("installCommands", [])),
        "buildCommands": list(profile.get("buildCommands", [])),
        "devCommands": list(profile.get("devCommands", [])),
        "testCommands": list(profile.get("testCommands", [])),
        "missingEnv": list(profile.get("envRequired", [])),
        "logs": list(logs or []),
        "previewBlockers": list(profile.get("previewBlockers", [])),
        "nextActions": _next_actions(profile),
        "riskNotes": list(profile.get("riskNotes", [])),
        "recommendedPlan": profile.get("recommendedPlan", ""),
        "detectedType": profile.get("detectedType", "unknown"),
        "packageManager": profile.get("packageManager", ""),
        "frontendPath": profile.get("frontendPath", ""),
        "backendPath": profile.get("backendPath", ""),
    }


def _next_actions(profile: dict) -> list[str]:
    actions: list[str] = []
    detected = profile.get("detectedType", "unknown")
    pkg = profile.get("packageManager", "")
    env = profile.get("envRequired", [])

    if detected in ("vite_react", "next", "vue", "svelte"):
        install_cmd = f"{pkg} install" if pkg in _JS_PACKAGE_MANAGERS else "npm install"
        build_cmd = {
            "vite_react": f"{pkg} run build" if pkg in _JS_PACKAGE_MANAGERS else "npm run build",
            "next": f"{pkg} run build" if pkg in _JS_PACKAGE_MANAGERS else "npm run build",
            "vue": f"{pkg} run build" if pkg in _JS_PACKAGE_MANAGERS else "npm run build",
            "svelte": f"{pkg} run build" if pkg in _JS_PACKAGE_MANAGERS else "npm run build",
        }.get(detected, "npm run build")
        dev_cmd = f"{pkg} run dev" if pkg in _JS_PACKAGE_MANAGERS else "npm run dev"
        actions += [
            f"Run `{install_cmd}` to install dependencies",
            f"Run `{build_cmd}` to build the app",
            f"Run `{dev_cmd}` to start the development server",
        ]
    elif detected == "static":
        actions.append("Open index.html in a browser or serve with a static server")
    elif detected == "fullstack":
        actions += [
            "Start the backend server (see devCommands)",
            "Start the frontend dev server",
            "Configure .env with required variables",
        ]
    elif detected == "api_service":
        actions += [
            "Install dependencies and start the API server",
            "Test the health endpoint (e.g. GET /health)",
        ]
    else:
        actions.append("Review README for run instructions")

    if env:
        actions.append(f"Create a .env file with: {', '.join(env[:6])}")

    if profile.get("hasDocker"):
        actions.append("Run `docker compose up` to start all services")

    return actions


# ── Main executor ─────────────────────────────────────────────────────────────

def execute_preview(
    files: list[dict],
    profile: dict,
) -> dict:
    """Return a preview result dict.

    Returns:
        {
            "canPreview": bool,
            "type": "static" | "repo-preview-fallback",
            # For static: "html" key with inlined HTML
            # For fallback: full fallback contract
        }
    """
    detected = profile.get("detectedType", "unknown")
    blockers = profile.get("previewBlockers", [])

    # ── Static site: we can produce a live inline preview ─────────────────────
    if detected == "static" and not blockers:
        html = render_preview(files)
        if html and "<body>" in html:
            return {
                "canPreview": True,
                "type": "static",
                "html": html,
                "detectedType": detected,
                "previewStrategy": "static",
            }

    # ── All other strategies: produce informative fallback ────────────────────
    reason_map = {
        "vite_react": "Vite/React app requires npm install + build before preview. Run the commands below locally or in CI.",
        "next": "Next.js app requires npm install + next build before preview. Run the commands below.",
        "vue": "Vue app requires npm install + build before preview. Run the commands below.",
        "svelte": "Svelte app requires npm install + build before preview. Run the commands below.",
        "fullstack": "Full-stack app requires both frontend and backend to be running. See commands below.",
        "api_service": "API-only service — no browser preview available. Test the routes listed below.",
        "unknown": "Could not determine how to preview this repository. See file tree and README below.",
    }
    reason = reason_map.get(detected, "Preview requires build steps or environment configuration.")
    if blockers:
        reason = blockers[0]

    fb = _fallback(reason, profile)
    fb["previewStrategy"] = profile.get("previewStrategy", detected)
    return fb
