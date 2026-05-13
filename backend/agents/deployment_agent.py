"""
Deployment Agent — Phase 2B Full Activation.

Responsibilities:
- Validate Docker/docker-compose configuration
- Validate .env.example template completeness
- Validate build scripts (package.json, Makefile, etc.)
- Verify preview readiness (correct entry point, valid HTML)
- Generate deployment instructions
- Report build log errors honestly
- Never mark a broken runtime as successful
- Coordinate rollback guidance when issues detected

Input:
    files: list[{"path": str, "content": str, "language": str}]
    mode: str  (build mode)
    stack_decision: dict

Output:
    {
        "passed": bool,
        "deploy_checklist": [...],
        "warnings": [...],
        "errors": [...],
        "preview_readiness": {...},
        "docker_validation": {...},
        "env_validation": {...},
        "build_script_validation": {...},
        "deployment_instructions": str,
        "rollback_guidance": str,
        "health_check_url": str | None,
    }
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("amarktai.deployment_agent")

# ── Pattern library ────────────────────────────────────────────────────────────

_DOCKER_FROM = re.compile(r"^FROM\s+\S+", re.MULTILINE | re.IGNORECASE)
_DOCKER_EXPOSE = re.compile(r"^EXPOSE\s+(\d+)", re.MULTILINE | re.IGNORECASE)
_DOCKER_CMD = re.compile(r"^(?:CMD|ENTRYPOINT)\s+", re.MULTILINE | re.IGNORECASE)
_DOCKER_HEALTHCHECK = re.compile(r"^HEALTHCHECK\s+", re.MULTILINE | re.IGNORECASE)
_DOCKER_NONROOT = re.compile(r"^USER\s+(?!root)\S+", re.MULTILINE | re.IGNORECASE)

_COMPOSE_SERVICES = re.compile(r"^services:", re.MULTILINE)
_COMPOSE_HEALTHCHECK = re.compile(r"healthcheck:", re.IGNORECASE)
_COMPOSE_RESTART = re.compile(r"restart:\s*(?:always|unless-stopped|on-failure)", re.IGNORECASE)
_COMPOSE_ENV_FILE = re.compile(r"env_file:", re.IGNORECASE)

_ENV_PLACEHOLDER = re.compile(
    r"^([A-Z_][A-Z0-9_]*)\s*=\s*(?:your_|change_me|replace_|example_|<[^>]+>|\"\"$|''$)",
    re.MULTILINE | re.IGNORECASE,
)
_ENV_REAL_SECRET = re.compile(
    r"^(?:JWT_SECRET|SECRET_KEY|API_KEY|DATABASE_URL|POSTGRES_PASSWORD|REDIS_PASSWORD"
    r"|STRIPE_SECRET|SENDGRID_API|OPENAI_API|ANTHROPIC_API)\s*=\s*"
    r"(?!(?:your_|change_me|replace_|example_|<[^>]+>|\"\"$|''$))[^\s$]",
    re.MULTILINE | re.IGNORECASE,
)

_PKG_BUILD_SCRIPT = re.compile(r'"build"\s*:\s*"[^"]*vite|react-scripts|next|tsc|webpack', re.IGNORECASE)
_PKG_START_SCRIPT = re.compile(r'"start"\s*:\s*"[^"]+"', re.IGNORECASE)
_PKG_PREVIEW_SCRIPT = re.compile(r'"preview"\s*:\s*"[^"]+"', re.IGNORECASE)

_HTML_ENTRY = re.compile(r"<!DOCTYPE html>", re.IGNORECASE)
_PLACEHOLDER_TEXT = re.compile(
    r"\b(?:lorem ipsum|coming soon|under construction|placeholder|todo|fixme)\b",
    re.IGNORECASE,
)
_BROKEN_SCRIPT_SRC = re.compile(r'<script\b[^>]*src=["\'](?!https?://|/)[^"\']+\.(js|ts)["\']', re.IGNORECASE)


# ── Docker validation ──────────────────────────────────────────────────────────

def validate_docker_config(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate Dockerfile and docker-compose.yml configurations."""
    result: dict[str, Any] = {
        "has_dockerfile": False,
        "has_compose": False,
        "passed": True,
        "warnings": [],
        "errors": [],
        "checklist": [],
    }

    dockerfile_content = ""
    compose_content = ""

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if path in ("Dockerfile", "backend/Dockerfile", "frontend/Dockerfile"):
            dockerfile_content = content
            result["has_dockerfile"] = True
        elif path in ("docker-compose.yml", "docker-compose.yaml", "docker-compose.prod.yml"):
            compose_content = content
            result["has_compose"] = True

    # Dockerfile checks
    if dockerfile_content:
        if _DOCKER_FROM.search(dockerfile_content):
            result["checklist"].append("✓ Dockerfile has FROM instruction")
        else:
            result["errors"].append("Dockerfile missing FROM instruction.")
            result["passed"] = False

        if _DOCKER_CMD.search(dockerfile_content):
            result["checklist"].append("✓ Dockerfile has CMD/ENTRYPOINT")
        else:
            result["warnings"].append("Dockerfile missing CMD/ENTRYPOINT instruction.")

        if _DOCKER_HEALTHCHECK.search(dockerfile_content):
            result["checklist"].append("✓ Dockerfile has HEALTHCHECK")
        else:
            result["warnings"].append("Dockerfile missing HEALTHCHECK. Add health monitoring.")

        if _DOCKER_NONROOT.search(dockerfile_content):
            result["checklist"].append("✓ Dockerfile uses non-root user")
        else:
            result["warnings"].append("Dockerfile runs as root. Add USER instruction for security.")

        expose_matches = _DOCKER_EXPOSE.findall(dockerfile_content)
        if expose_matches:
            result["checklist"].append(f"✓ Dockerfile exposes port(s): {', '.join(expose_matches)}")
            result["exposed_ports"] = expose_matches
        else:
            result["warnings"].append("Dockerfile missing EXPOSE instruction.")

    # docker-compose checks
    if compose_content:
        if _COMPOSE_SERVICES.search(compose_content):
            result["checklist"].append("✓ docker-compose.yml has services section")
        else:
            result["errors"].append("docker-compose.yml missing services section.")
            result["passed"] = False

        if _COMPOSE_HEALTHCHECK.search(compose_content):
            result["checklist"].append("✓ docker-compose.yml has healthcheck")
        else:
            result["warnings"].append("docker-compose.yml missing healthcheck configuration.")

        if _COMPOSE_RESTART.search(compose_content):
            result["checklist"].append("✓ docker-compose.yml has restart policy")
        else:
            result["warnings"].append("docker-compose.yml missing restart policy.")

        if _COMPOSE_ENV_FILE.search(compose_content):
            result["checklist"].append("✓ docker-compose.yml references env_file")

    return result


# ── Env template validation ────────────────────────────────────────────────────

def validate_env_template(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate .env.example for completeness and no real secrets."""
    result: dict[str, Any] = {
        "has_env_example": False,
        "passed": True,
        "warnings": [],
        "errors": [],
        "checklist": [],
        "variables": [],
    }

    env_content = ""
    for f in files:
        path = f.get("path", "")
        if path in (".env.example", ".env.sample", ".env.template"):
            env_content = f.get("content", "")
            result["has_env_example"] = True
            break

    if not env_content:
        result["warnings"].append("No .env.example found. Full-stack projects need env documentation.")
        return result

    # Check all vars are placeholders (not real values)
    if _ENV_REAL_SECRET.search(env_content):
        result["errors"].append(
            ".env.example appears to contain real secrets. "
            "Replace with placeholder values like YOUR_JWT_SECRET_HERE."
        )
        result["passed"] = False
    else:
        result["checklist"].append("✓ .env.example uses placeholder values only")

    # Count placeholder variables
    placeholders = _ENV_PLACEHOLDER.findall(env_content)
    if placeholders:
        result["checklist"].append(f"✓ .env.example has {len(placeholders)} documented variable(s)")
        result["variables"] = placeholders
    elif env_content.strip():
        result["warnings"].append(
            ".env.example seems present but no standard placeholder patterns detected. "
            "Ensure variables are documented with example values."
        )

    return result


# ── Build script validation ────────────────────────────────────────────────────

def validate_build_scripts(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate build scripts in package.json."""
    result: dict[str, Any] = {
        "has_package_json": False,
        "passed": True,
        "warnings": [],
        "checklist": [],
    }

    for f in files:
        path = f.get("path", "")
        if path in ("package.json", "frontend/package.json"):
            result["has_package_json"] = True
            content = f.get("content", "")

            if _PKG_BUILD_SCRIPT.search(content):
                result["checklist"].append("✓ package.json has build script")
            else:
                result["warnings"].append(f"package.json ({path}) has no build script.")

            if _PKG_START_SCRIPT.search(content):
                result["checklist"].append("✓ package.json has start script")
            else:
                result["warnings"].append(f"package.json ({path}) missing start script.")

    return result


# ── Preview readiness validation ───────────────────────────────────────────────

def validate_preview_readiness(files: list[dict[str, Any]], mode: str = "") -> dict[str, Any]:
    """Check whether the build is ready for preview."""
    result: dict[str, Any] = {
        "can_preview": False,
        "preview_entry": None,
        "passed": True,
        "warnings": [],
        "errors": [],
        "checklist": [],
    }

    html_files = [f for f in files if f.get("path", "").endswith(".html")]
    index_html = next((f for f in html_files if f.get("path") == "index.html"), None)

    if index_html:
        content = index_html.get("content", "")
        result["preview_entry"] = "index.html"

        if _HTML_ENTRY.search(content):
            result["checklist"].append("✓ index.html has valid HTML doctype")
            result["can_preview"] = True
        else:
            result["errors"].append("index.html missing DOCTYPE declaration.")
            result["passed"] = False

        # Check for placeholder text
        placeholders_found = _PLACEHOLDER_TEXT.findall(content)
        if placeholders_found:
            result["warnings"].append(
                f"Placeholder text detected in index.html: {', '.join(set(placeholders_found[:3]))}. "
                "Replace with real content before publishing."
            )

        # Check for broken local script references
        broken = _BROKEN_SCRIPT_SRC.findall(content)
        if broken:
            result["warnings"].append(
                f"Possible broken local script references in index.html. "
                "Verify all script src paths resolve correctly."
            )

    elif html_files:
        result["preview_entry"] = html_files[0]["path"]
        result["can_preview"] = True
        result["warnings"].append(
            f"No index.html found — using {html_files[0]['path']} as entry. "
            "Rename to index.html for reliable preview."
        )

    elif mode in ("full_stack", "api_service", "automation_bot"):
        result["can_preview"] = False
        result["checklist"].append(
            f"Preview: '{mode}' mode uses server runtime — browser preview not applicable."
        )
    else:
        result["can_preview"] = False
        result["errors"].append("No HTML entry file found. Cannot generate browser preview.")
        result["passed"] = False

    return result


# ── Deployment instructions ────────────────────────────────────────────────────

def generate_deployment_instructions(files: list[dict[str, Any]], mode: str) -> str:
    """Generate human-readable deployment instructions for the build."""
    has_docker = any(f.get("path") in ("Dockerfile", "docker-compose.yml") for f in files)
    has_package_json = any(f.get("path") in ("package.json", "frontend/package.json") for f in files)
    has_index_html = any(f.get("path") == "index.html" for f in files)
    has_env_example = any(f.get("path") in (".env.example",) for f in files)

    lines: list[str] = ["# Deployment Instructions\n"]

    if has_docker:
        lines += [
            "## Docker Deployment",
            "```bash",
            "# 1. Copy environment template",
            "cp .env.example .env",
            "# 2. Fill in .env with real values",
            "# 3. Build and start containers",
            "docker compose up -d --build",
            "# 4. Verify health",
            "docker compose ps",
            "docker compose logs",
            "```\n",
        ]
    elif has_package_json:
        lines += [
            "## Node.js Deployment",
            "```bash",
            "npm install",
            "npm run build",
        ]
        if has_env_example:
            lines += ["cp .env.example .env  # fill in real values"]
        lines += ["npm start", "```\n"]
    elif has_index_html:
        lines += [
            "## Static Site Deployment",
            "Deploy the `index.html` and associated files to any static host:",
            "- Netlify: drag-and-drop the folder",
            "- Vercel: `vercel --prod`",
            "- GitHub Pages: push to `gh-pages` branch",
            "- Nginx: copy files to `/var/www/html/`\n",
        ]

    lines += [
        "## Health Verification",
        "After deployment, verify the app is running:",
        "```bash",
        "curl -fsS https://your-domain.com/health || echo 'Health check failed'",
        "```\n",
        "## Rollback",
        "If deployment fails, restore the previous version:",
        "```bash",
        "# Docker: revert to previous image tag",
        "docker compose down",
        "docker compose up -d --no-build  # uses cached image",
        "```",
    ]

    return "\n".join(lines)


# ── Main entry-point ───────────────────────────────────────────────────────────

def run_deployment_validation(
    files: list[dict[str, Any]],
    mode: str = "landing_page",
    stack_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Main Deployment Agent entry-point.
    
    Validates deployment readiness and returns a comprehensive report.
    Never marks a broken deployment as successful.
    """
    sd = stack_decision or {}

    docker_result = validate_docker_config(files)
    env_result = validate_env_template(files)
    build_result = validate_build_scripts(files)
    preview_result = validate_preview_readiness(files, mode)

    all_errors = (
        docker_result["errors"]
        + env_result["errors"]
        + preview_result["errors"]
    )
    all_warnings = (
        docker_result["warnings"]
        + env_result["warnings"]
        + build_result["warnings"]
        + preview_result["warnings"]
    )

    # Build deploy checklist
    checklist = (
        docker_result["checklist"]
        + env_result["checklist"]
        + build_result["checklist"]
        + preview_result["checklist"]
    )

    # Overall pass/fail — never fake success
    overall_passed = (
        docker_result["passed"]
        and env_result["passed"]
        and preview_result["passed"]
        and len(all_errors) == 0
    )

    instructions = generate_deployment_instructions(files, mode)

    result = {
        "passed": overall_passed,
        "deploy_checklist": checklist,
        "warnings": all_warnings,
        "errors": all_errors,
        "preview_readiness": preview_result,
        "docker_validation": docker_result,
        "env_validation": env_result,
        "build_script_validation": build_result,
        "deployment_instructions": instructions,
        "rollback_guidance": (
            "To rollback: restore previous build artifacts or use `docker compose down && "
            "docker compose up -d` with a previous image tag."
        ),
        "health_check_url": None,
    }

    # Log summary
    status = "PASSED" if overall_passed else "FAILED"
    logger.info(
        "Deployment validation %s: errors=%d warnings=%d checklist=%d",
        status, len(all_errors), len(all_warnings), len(checklist),
    )
    if all_errors:
        for err in all_errors:
            logger.warning("Deployment error: %s", err)

    return result
