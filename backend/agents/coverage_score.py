"""
Coverage Score Engine — Phase 5 of the Amarktai App Builder final go-live spec.

Validates that the generated output satisfies the user's original request.
Returns a coverage report used to:
  - block finalize when coverageScore < 80 for full_app_completion
  - surface missing requirements to the user
  - compute the overall canFinalize flag (alongside quality/security)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Requirement extractors ────────────────────────────────────────────────────

_PAGE_PATTERNS = re.compile(
    r"\b(\d+)[- ]?(?:page|screen|view)\b"
    r"|\b(?:home|about|contact|pricing|blog|dashboard|login|register|signup|profile|settings|admin)"
    r"\s+(?:page|screen|view)?\b",
    re.IGNORECASE,
)
_AUTH_REQ = re.compile(
    r"\b(?:login|auth(?:entication)?|sign[- ]?(?:in|up)|register|jwt|session|user account)\b",
    re.IGNORECASE,
)
_BACKEND_REQ = re.compile(
    r"\b(?:api|backend|server|endpoint|route|database|db|mongo|postgres|mysql|rest|graphql)\b",
    re.IGNORECASE,
)
_DOCKER_REQ = re.compile(
    r"\b(?:docker|container(?:ize)?|compose|deploy(?:ment)?|kubernetes|k8s)\b",
    re.IGNORECASE,
)
_README_REQ = re.compile(r"\breadme\b", re.IGNORECASE)
_ENV_REQ = re.compile(r"\.env(?:\.example)?\b", re.IGNORECASE)
_PWA_REQ = re.compile(r"\bpwa\b|\boffline\b|\bservice.?worker\b|\bmanifest\b", re.IGNORECASE)
_RESPONSIVE_REQ = re.compile(r"\bresponsive\b|\bmobile\b|\btailwind\b|\bgrid\b|\bflex\b", re.IGNORECASE)
_MEDIA_REQ = re.compile(
    r"\b(?:image|photo|video|media|pixabay|gallery|banner|hero.?image)\b",
    re.IGNORECASE,
)


# ── File presence checkers ────────────────────────────────────────────────────

def _paths(files: list[dict]) -> set[str]:
    return {f["path"] for f in files}


def _all_content(files: list[dict]) -> str:
    return "\n".join(f.get("content", "") for f in files)


def _has_readme(files: list[dict]) -> bool:
    return any(f["path"].lower() in ("readme.md", "readme.txt", "readme") for f in files)


def _has_env_example(files: list[dict]) -> bool:
    ps = _paths(files)
    return any(p in ps or p.endswith("/.env.example") for p in [".env.example", ".env.sample"])


def _has_docker(files: list[dict]) -> bool:
    ps = _paths(files)
    return any(
        p in ps
        for p in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                  "backend/Dockerfile", "frontend/Dockerfile")
    )


def _has_manifest(files: list[dict]) -> bool:
    ps = _paths(files)
    return "manifest.json" in ps or any(p.endswith("/manifest.json") for p in ps)


def _has_service_worker(files: list[dict]) -> bool:
    ps = _paths(files)
    return any("service-worker" in p or "sw.js" in p for p in ps)


def _has_auth_files(files: list[dict]) -> bool:
    ps = _paths(files)
    content = _all_content(files)
    return (
        any("auth" in p.lower() or "login" in p.lower() for p in ps)
        or bool(re.search(r"bcrypt|jwt|passlib|require_auth|@login_required|Depends\(require", content, re.IGNORECASE))
    )


def _has_backend(files: list[dict]) -> bool:
    ps = _paths(files)
    content = _all_content(files)
    return (
        any(
            p.startswith("backend/") or p.startswith("api/") or p.startswith("server/")
            or p in ("server.py", "main.py", "app.py", "index.js", "app.js")
            for p in ps
        )
        or bool(re.search(r"fastapi|express|flask|django", content, re.IGNORECASE))
    )


def _has_dashboard_page(files: list[dict]) -> bool:
    ps = _paths(files)
    content = _all_content(files)
    return (
        any("dashboard" in p.lower() for p in ps)
        or bool(re.search(r"\bdashboard\b", content, re.IGNORECASE))
    )


def _count_html_pages(files: list[dict]) -> int:
    """Estimate the number of distinct HTML pages/views in the project."""
    html_files = [f for f in files if f["path"].endswith((".html", ".htm"))]
    jsx_tsx = [f for f in files if f["path"].endswith((".jsx", ".tsx")) and
               any(kw in f["path"].lower() for kw in ("page", "view", "screen", "route"))]
    return max(len(html_files), len(jsx_tsx))


def _has_responsive(files: list[dict]) -> bool:
    content = _all_content(files)
    return bool(re.search(
        r"@media\s*\([^)]*(?:max-width|min-width)\)|tailwind|grid-template-columns|flex\b",
        content, re.IGNORECASE,
    ))


def _has_media(files: list[dict]) -> bool:
    content = _all_content(files)
    ps = _paths(files)
    return (
        bool(re.search(r'<img\b[^>]*src=["\'][^"\']+["\']|background-image:', content, re.IGNORECASE))
        or any(p.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".mp4")) for p in ps)
    )


# ── Main coverage scorer ──────────────────────────────────────────────────────

def compute_coverage_score(
    prompt: str,
    files: list[dict],
    mode: str = "web_app",
    intent: str = "small_patch",
    changed_files: list[str] | None = None,
    added_files: list[str] | None = None,
    preview_url: str = "",
    preview_fallback: dict | None = None,
) -> dict:
    """Compute the request coverage score for the generated output.

    Returns:
    {
        requestSatisfied: bool,
        coverageScore: int (0-100),
        missingRequirements: list[str],
        checkedRequirements: list[str],
        changedFiles: list[str],
        addedFiles: list[str],
        previewUrl: str,
        previewFallback: dict | None,
        canFinalize: bool,
        intent: str,
        scoredAt: str,
    }
    """
    missing: list[str] = []
    satisfied: list[str] = []
    total_points = 0
    earned_points = 0

    def check(name: str, condition: bool, points: int, required: bool = True) -> None:
        nonlocal total_points, earned_points
        if not required:
            return
        total_points += points
        if condition:
            earned_points += points
            satisfied.append(name)
        else:
            missing.append(name)

    # ── Core: always check preview or fallback ─────────────────────────────
    has_preview = bool(preview_url) or bool(preview_fallback)
    check("preview or preview fallback available", has_preview, 10)

    # ── Core: app files generated ─────────────────────────────────────────
    _meta = {"requirements.md", "tech_stack.json"}
    app_files = [f for f in files if f["path"] not in _meta]
    check("app files generated", len(app_files) > 0, 15)

    # ── Core: README ──────────────────────────────────────────────────────
    readme_required = (
        _README_REQ.search(prompt) is not None
        or mode in ("full_stack", "dashboard", "admin_panel", "api_service",
                    "fullstack-saas", "automation_bot", "trading_bot_scaffold", "repo_fix")
        or intent in ("full_app_completion", "production_hardening", "full_rebuild_inside_repo")
    )
    check("README.md present", _has_readme(files), 8, required=readme_required)

    # ── Auth ─────────────────────────────────────────────────────────────
    auth_required = bool(
        _AUTH_REQ.search(prompt)
        or mode in ("full_stack", "dashboard", "admin_panel", "fullstack-saas")
    )
    if auth_required:
        check("authentication implementation", _has_auth_files(files), 12)

    # ── Backend ──────────────────────────────────────────────────────────
    backend_required = bool(
        _BACKEND_REQ.search(prompt)
        or mode in ("full_stack", "api_service", "fullstack-saas")
    )
    if backend_required:
        check("backend / API present", _has_backend(files), 10)

    # ── Docker ───────────────────────────────────────────────────────────
    docker_required = bool(
        _DOCKER_REQ.search(prompt)
        or mode in ("full_stack", "fullstack-saas")
    )
    if docker_required:
        check("Docker configuration present", _has_docker(files), 6)
        check(".env.example present", _has_env_example(files), 5)

    # ── PWA ──────────────────────────────────────────────────────────────
    pwa_required = bool(_PWA_REQ.search(prompt) or mode == "pwa")
    if pwa_required:
        check("manifest.json present", _has_manifest(files), 8)
        check("service worker present", _has_service_worker(files), 8)

    # ── Multi-page ───────────────────────────────────────────────────────
    page_match = re.search(r"\b(\d+)[- ]?page\b", prompt, re.IGNORECASE)
    if page_match:
        requested_pages = int(page_match.group(1))
        actual_pages = _count_html_pages(files)
        pages_ok = actual_pages >= max(1, requested_pages - 1)  # allow 1 page short
        check(
            f"{requested_pages} pages/views generated (found {actual_pages})",
            pages_ok,
            10,
        )

    # ── Dashboard ────────────────────────────────────────────────────────
    if mode in ("dashboard", "admin_panel") or re.search(r"\bdashboard\b", prompt, re.IGNORECASE):
        check("dashboard page/component present", _has_dashboard_page(files), 8)

    # ── Responsive ───────────────────────────────────────────────────────
    if _RESPONSIVE_REQ.search(prompt) or mode in ("landing_page", "website", "pwa"):
        check("responsive layout present", _has_responsive(files), 6)

    # ── Media ────────────────────────────────────────────────────────────
    if _MEDIA_REQ.search(prompt):
        check("media/images present", _has_media(files), 6)

    # ── Full app completion: require substantial file count ───────────────
    if intent in ("full_app_completion", "full_rebuild_inside_repo"):
        substantial = len(app_files) >= 5
        check("substantial file set for full app completion (>=5 files)", substantial, 12)
        check("README.md present", _has_readme(files), 5)

    # ── Compute score ─────────────────────────────────────────────────────
    if total_points == 0:
        # No specific requirements detected — give full marks for having any files
        coverage_score = 85 if app_files else 0
    else:
        coverage_score = round((earned_points / total_points) * 100)

    # ── Threshold for full_app_completion ─────────────────────────────────
    min_score = 80 if intent in (
        "full_app_completion", "full_rebuild_inside_repo", "production_hardening"
    ) else 60

    request_satisfied = coverage_score >= min_score and len(app_files) > 0

    # ── canFinalize: requires satisfaction AND preview or fallback ─────────
    can_finalize = request_satisfied and has_preview

    return {
        "requestSatisfied": request_satisfied,
        "coverageScore": coverage_score,
        "missingRequirements": missing,
        "checkedRequirements": satisfied,
        "changedFiles": changed_files or [],
        "addedFiles": added_files or [],
        "previewUrl": preview_url,
        "previewFallback": preview_fallback,
        "canFinalize": can_finalize,
        "intent": intent,
        "minScore": min_score,
        "scoredAt": _now(),
    }
