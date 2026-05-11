"""
Repo Workbench: analyze an imported GitHub repository and produce a structured
repo profile that drives preview strategy, intent detection, and the UI.

Phase 2 + Phase 3 of the Amarktai App Builder final go-live spec.
"""
from __future__ import annotations

import json
import re
from typing import Any

# ── Language / extension helpers ──────────────────────────────────────────────

_EXT_LANG: dict[str, str] = {
    "py": "Python", "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript",
    "html": "HTML", "htm": "HTML",
    "css": "CSS", "scss": "CSS", "sass": "CSS",
    "go": "Go", "rs": "Rust", "rb": "Ruby", "php": "PHP",
    "java": "Java", "kt": "Kotlin", "swift": "Swift",
    "cs": "C#", "cpp": "C++", "c": "C",
    "sh": "Shell", "bash": "Shell",
    "json": "JSON", "yaml": "YAML", "yml": "YAML", "toml": "TOML",
    "md": "Markdown", "dockerfile": "Dockerfile",
    "sql": "SQL", "prisma": "Prisma",
}

_FRAMEWORK_SIGNALS: list[tuple[str, str]] = [
    # (file or content pattern, framework name)
    # Next.js — must come before React
    (r"next\.config\.(js|ts|mjs)", "Next.js"),
    (r'"next"\s*:', "Next.js"),
    # Vite
    (r"vite\.config\.(js|ts|mjs)", "Vite"),
    (r'"vite"\s*:', "Vite"),
    # React (generic — after Next.js)
    (r'"react"\s*:', "React"),
    (r"from ['\"]react['\"]", "React"),
    # Vue
    (r'"vue"\s*:', "Vue"),
    (r"\.vue$", "Vue"),
    # Svelte
    (r"svelte\.config\.", "Svelte"),
    (r'"svelte"\s*:', "Svelte"),
    # Angular
    (r"angular\.json", "Angular"),
    (r'"@angular/core"\s*:', "Angular"),
    # FastAPI
    (r"from fastapi import", "FastAPI"),
    (r"fastapi", "FastAPI"),
    # Express
    (r"require\(['\"]express['\"]", "Express"),
    (r"from ['\"]express['\"]", "Express"),
    # Django
    (r"from django", "Django"),
    (r"django", "Django"),
    # Flask
    (r"from flask import", "Flask"),
    (r"flask", "Flask"),
    # Laravel
    (r"artisan", "Laravel"),
    (r"Laravel", "Laravel"),
    # Astro
    (r"astro\.config\.", "Astro"),
    (r'"astro"\s*:', "Astro"),
]

_DB_SIGNALS: list[tuple[str, str]] = [
    (r"mongodb|mongoose|pymongo|motor", "MongoDB"),
    (r"postgresql|postgres|psycopg|pg\b", "PostgreSQL"),
    (r"mysql|mariadb|pymysql|mysqlclient", "MySQL/MariaDB"),
    (r"sqlite", "SQLite"),
    (r"prisma", "Prisma"),
    (r"redis", "Redis"),
    (r"supabase", "Supabase"),
    (r"firebase", "Firebase"),
    (r"dynamodb", "DynamoDB"),
]

_AUTH_SIGNALS: list[tuple[str, str]] = [
    (r"bcrypt|passlib|argon2", "bcrypt/passlib"),
    (r"jwt|jsonwebtoken|PyJWT|python-jose", "JWT"),
    (r"oauth|oauth2|nextauth|passport", "OAuth"),
    (r"@supabase/auth|supabase.*auth", "Supabase Auth"),
    (r"firebase.*auth|auth.*firebase", "Firebase Auth"),
]

_PACKAGE_MANAGER_SIGNALS: list[tuple[str, str]] = [
    ("yarn.lock", "yarn"),
    ("pnpm-lock.yaml", "pnpm"),
    ("package-lock.json", "npm"),
    ("requirements.txt", "pip"),
    ("Pipfile.lock", "pipenv"),
    ("poetry.lock", "poetry"),
    ("Gemfile.lock", "bundler"),
    ("go.sum", "go modules"),
    ("Cargo.lock", "cargo"),
    ("composer.lock", "composer"),
]

_PREVIEW_STRATEGIES = {
    "static": "Serve index.html directly",
    "vite_react": "npm install → vite build → serve dist/",
    "next": "npm install → next build → next start (or static export)",
    "fullstack": "Frontend preview + backend route map; may need env vars",
    "api": "Route/docs preview — no visual frontend",
    "unknown": "File tree + README + build commands + blockers",
}


def _scan_files(files: list[dict]) -> dict[str, Any]:
    """Scan a list of project file dicts and return aggregated detection state."""
    paths = {f["path"] for f in files}
    all_content = "\n".join(f.get("content", "") for f in files)
    all_paths_str = "\n".join(paths)

    # Languages from extensions
    lang_counts: dict[str, int] = {}
    for f in files:
        path = f["path"]
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        lang = _EXT_LANG.get(ext)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    languages = sorted(lang_counts, key=lambda k: lang_counts[k], reverse=True)

    # Frameworks
    frameworks: list[str] = []
    for pattern, name in _FRAMEWORK_SIGNALS:
        if re.search(pattern, all_content, re.IGNORECASE) or re.search(pattern, all_paths_str, re.IGNORECASE):
            if name not in frameworks:
                frameworks.append(name)

    # Databases
    databases: list[str] = []
    for pattern, name in _DB_SIGNALS:
        if re.search(pattern, all_content, re.IGNORECASE):
            if name not in databases:
                databases.append(name)

    # Auth
    auth_detected: list[str] = []
    for pattern, name in _AUTH_SIGNALS:
        if re.search(pattern, all_content, re.IGNORECASE):
            if name not in auth_detected:
                auth_detected.append(name)

    # Package manager
    package_manager = "unknown"
    for filename, pm in _PACKAGE_MANAGER_SIGNALS:
        if any(p == filename or p.endswith("/" + filename) for p in paths):
            package_manager = pm
            break

    # Docker
    docker_available = any(
        p == "Dockerfile" or p.endswith("/Dockerfile") or p == "docker-compose.yml"
        or p.endswith("/docker-compose.yml") or p == "docker-compose.yaml"
        for p in paths
    )

    # Frontend / backend paths
    frontend_path = ""
    backend_path = ""
    for candidate in ("frontend", "client", "web", "app/src", "src"):
        if any(p.startswith(candidate + "/") for p in paths):
            frontend_path = candidate
            break
    for candidate in ("backend", "server", "api", "app"):
        if any(p.startswith(candidate + "/") for p in paths):
            backend_path = candidate
            break

    # Route map (simple: collect route-like strings)
    route_patterns = re.compile(
        r"""(?:app|router)\.(get|post|put|patch|delete|use)\s*\(\s*["'`](/[^"'`]*?)["'`]"""
        r"""|path\s*=\s*["']([/][^"']+)["']"""
        r"""|Route\s+path=["']([/][^"']+)["']""",
        re.IGNORECASE,
    )
    route_map: list[str] = []
    for m in route_patterns.finditer(all_content):
        route = m.group(2) or m.group(3) or m.group(4) or ""
        if route and route not in route_map:
            route_map.append(route)
    route_map = sorted(set(route_map))[:50]

    return {
        "languages": languages,
        "frameworks": frameworks,
        "databases": databases,
        "auth_detected": auth_detected,
        "package_manager": package_manager,
        "docker_available": docker_available,
        "frontend_path": frontend_path,
        "backend_path": backend_path,
        "route_map": route_map,
        "paths": sorted(paths),
    }


def _detect_type_and_preview(scan: dict, files: list[dict]) -> tuple[str, str, str]:
    """Return (detectedType, previewStrategy, previewReason)."""
    frameworks = scan["frameworks"]
    paths = set(scan["paths"])

    # Static site — has index.html, no build system
    has_index = "index.html" in paths or any(p.endswith("/index.html") for p in paths)
    has_package_json = "package.json" in paths or any(p.endswith("/package.json") for p in paths)

    if has_index and not has_package_json and not frameworks:
        return "static", "static", "Has index.html; no build system detected."

    # Next.js
    if "Next.js" in frameworks:
        return "next", "next", "Next.js detected via next.config or package.json."

    # Vite / React
    if "Vite" in frameworks or ("React" in frameworks and has_package_json):
        return "vite_react", "vite_react", "Vite/React detected."

    # Static site with a build tool — use generic 'spa' type unless we can confirm Vite/React
    if has_index and has_package_json:
        if "React" in frameworks or "Vite" in frameworks:
            return "vite_react", "vite_react", "index.html + package.json — Vite/React SPA detected."
        return "vite_react", "vite_react", "index.html + package.json — generic SPA (build tool uncertain)."

    # API-only (Python/Express, no frontend)
    has_frontend = bool(scan["frontend_path"]) or any(
        p.endswith(".jsx") or p.endswith(".tsx") or p.endswith(".html")
        for p in paths
    )
    is_api = any(f in frameworks for f in ("FastAPI", "Flask", "Django", "Express"))
    if is_api and not has_frontend:
        return "api_service", "api", "API-only backend detected."

    # Full-stack: frontend + backend
    if (scan["frontend_path"] and scan["backend_path"]) or (is_api and has_frontend):
        return "fullstack", "fullstack", "Frontend and backend paths detected."

    # Unknown
    return "unknown", "unknown", "Could not detect project type reliably."


def _detect_env_requirements(files: list[dict]) -> list[str]:
    """Extract required env var names from .env.example or source code."""
    required: list[str] = []
    env_example_pattern = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=", re.MULTILINE)
    os_environ_pattern = re.compile(r'os\.environ(?:\.get)?\(["\']([A-Z][A-Z0-9_]+)["\']', re.MULTILINE)
    process_env_pattern = re.compile(r'process\.env\.([A-Z][A-Z0-9_]+)', re.MULTILINE)

    for f in files:
        content = f.get("content", "")
        path = f["path"]
        if path in (".env.example", ".env.sample") or path.endswith("/.env.example"):
            for m in env_example_pattern.finditer(content):
                var = m.group(1)
                if var not in required:
                    required.append(var)
        else:
            for m in os_environ_pattern.finditer(content):
                var = m.group(1)
                if var not in required and var not in ("PATH", "HOME", "USER"):
                    required.append(var)
            for m in process_env_pattern.finditer(content):
                var = m.group(1)
                if var not in required and var not in ("PATH", "HOME", "NODE_ENV"):
                    required.append(var)
    return required[:30]


def _detect_commands(files: list[dict], package_manager: str) -> dict[str, list[str]]:
    """Return install/build/dev/test commands based on detected stack."""
    paths = {f["path"] for f in files}
    has_pkg = "package.json" in paths or any(p.endswith("/package.json") for p in paths)
    has_req = "requirements.txt" in paths or any(p.endswith("/requirements.txt") for p in paths)
    has_pipfile = "Pipfile" in paths
    has_makefile = "Makefile" in paths
    has_docker = any(p == "docker-compose.yml" or p.endswith("/docker-compose.yml") for p in paths)

    pm = package_manager if package_manager != "unknown" else "npm"
    install: list[str] = []
    build: list[str] = []
    dev: list[str] = []
    test: list[str] = []

    if has_pkg:
        if pm == "yarn":
            install.append("yarn install")
            build.append("yarn build")
            dev.append("yarn dev")
            test.append("yarn test")
        elif pm == "pnpm":
            install.append("pnpm install")
            build.append("pnpm build")
            dev.append("pnpm dev")
            test.append("pnpm test")
        else:
            install.append("npm install")
            build.append("npm run build")
            dev.append("npm run dev")
            test.append("npm test")

    if has_req:
        install.append("pip install -r requirements.txt")
        dev.append("uvicorn main:app --reload")
        test.append("python -m pytest")
    elif has_pipfile:
        install.append("pipenv install")
        dev.append("pipenv run python main.py")

    if has_docker:
        build.append("docker compose build")
        dev.append("docker compose up")

    if has_makefile:
        build.append("make build")
        dev.append("make dev")
        test.append("make test")

    return {
        "installCommands": install,
        "buildCommands": build,
        "devCommands": dev,
        "testCommands": test,
    }


def _preview_blockers(
    detected_type: str,
    scan: dict,
    env_required: list[str],
) -> list[str]:
    """Return list of reasons the preview cannot run automatically."""
    blockers: list[str] = []
    if detected_type in ("fullstack", "api_service"):
        if env_required:
            blockers.append(f"Missing env vars: {', '.join(env_required[:8])}")
        if scan.get("databases"):
            blockers.append(f"Requires running database: {', '.join(scan['databases'])}")
    if detected_type == "unknown":
        blockers.append("Project type could not be detected — manual review required.")
    return blockers


def _risk_notes(scan: dict, detected_type: str) -> list[str]:
    """Return risk/warning notes for the repo profile."""
    notes: list[str] = []
    if not scan["databases"] and detected_type in ("fullstack", "api_service"):
        notes.append("No database detected — repo may have runtime data dependency not listed in source.")
    if not scan["auth_detected"] and detected_type in ("fullstack",):
        notes.append("No auth library detected — repo may lack authentication.")
    if scan["docker_available"]:
        notes.append("Docker configuration present — use docker compose up for full-stack preview.")
    if detected_type == "unknown":
        notes.append("Stack detection was inconclusive. Review file tree and README manually.")
    return notes


def _recommended_plan(detected_type: str, scan: dict) -> list[str]:
    """Return recommended next steps for the imported repo."""
    plan: list[str] = []
    if detected_type == "static":
        plan.append("Preview the index.html directly in the browser.")
    elif detected_type == "vite_react":
        plan.append("Run: npm install && npm run build")
        plan.append("Serve the dist/ or build/ directory.")
    elif detected_type == "next":
        plan.append("Run: npm install && npm run build && npm start")
        plan.append("Or: npm run dev for development preview.")
    elif detected_type == "fullstack":
        plan.append("Set up required env vars (see envRequired).")
        if scan["docker_available"]:
            plan.append("Run: docker compose up")
        else:
            plan.append("Start backend and frontend separately.")
    elif detected_type == "api_service":
        plan.append("Set up required env vars (see envRequired).")
        plan.append("Start the API server and check /docs or /health route.")
    else:
        plan.append("Review file tree and README for build instructions.")
        plan.append("Set up environment and run build commands listed above.")

    if scan["databases"]:
        plan.append(f"Ensure {', '.join(scan['databases'])} is running and accessible.")
    return plan


def analyze_repo_profile(files: list[dict], repo_full_name: str = "") -> dict:
    """Analyze an imported repo's files and return a structured repo profile.

    Returns a dict matching the Phase 2 contract:
    {
        repoFullName, detectedType, languages, frameworks, databases,
        frontendPath, backendPath, packageManager, authDetected,
        installCommands, buildCommands, devCommands, testCommands,
        previewStrategy, previewStrategyNote, envRequired,
        dockerAvailable, canPreview, previewBlockers,
        routeMap, riskNotes, recommendedPlan,
        fileCount, fileTree (top 50 paths)
    }
    """
    if not files:
        return {
            "repoFullName": repo_full_name,
            "detectedType": "unknown",
            "languages": [],
            "frameworks": [],
            "databases": [],
            "frontendPath": "",
            "backendPath": "",
            "packageManager": "unknown",
            "authDetected": [],
            "installCommands": [],
            "buildCommands": [],
            "devCommands": [],
            "testCommands": [],
            "previewStrategy": "unknown",
            "previewStrategyNote": "No files found in this repository.",
            "envRequired": [],
            "dockerAvailable": False,
            "canPreview": False,
            "previewBlockers": ["No files found."],
            "routeMap": [],
            "riskNotes": [],
            "recommendedPlan": ["Import the repository before analysing."],
            "fileCount": 0,
            "fileTree": [],
            "readmeContent": "",
        }

    scan = _scan_files(files)
    detected_type, preview_strategy, preview_note = _detect_type_and_preview(scan, files)
    env_required = _detect_env_requirements(files)
    commands = _detect_commands(files, scan["package_manager"])
    blockers = _preview_blockers(detected_type, scan, env_required)
    can_preview = len(blockers) == 0 and detected_type != "unknown"
    risk_notes = _risk_notes(scan, detected_type)
    recommended_plan = _recommended_plan(detected_type, scan)

    # Extract README content
    readme_content = ""
    for f in files:
        if f["path"].lower() in ("readme.md", "readme.txt", "readme"):
            readme_content = f.get("content", "")[:3000]
            break

    return {
        "repoFullName": repo_full_name,
        "detectedType": detected_type,
        "languages": scan["languages"],
        "frameworks": scan["frameworks"],
        "databases": scan["databases"],
        "frontendPath": scan["frontend_path"],
        "backendPath": scan["backend_path"],
        "packageManager": scan["package_manager"],
        "authDetected": scan["auth_detected"],
        "installCommands": commands["installCommands"],
        "buildCommands": commands["buildCommands"],
        "devCommands": commands["devCommands"],
        "testCommands": commands["testCommands"],
        "previewStrategy": preview_strategy,
        "previewStrategyNote": preview_note,
        "envRequired": env_required,
        "dockerAvailable": scan["docker_available"],
        "canPreview": can_preview,
        "previewBlockers": blockers,
        "routeMap": scan["route_map"],
        "riskNotes": risk_notes,
        "recommendedPlan": recommended_plan,
        "fileCount": len(files),
        "fileTree": sorted(scan["paths"])[:80],
        "readmeContent": readme_content,
    }


def detect_update_intent(request: str, files: list[dict]) -> str:
    """Classify the user's update request intent for an imported repo.

    Returns one of:
        small_patch          — typo fix, colour change, one-line update
        bug_fix              — crash, error, failing test
        feature_add          — add new section/feature/route
        redesign             — complete visual overhaul
        production_hardening — security, auth, rate limiting, CI/CD
        full_app_completion  — build the complete app from this skeleton
        repo_migration       — migrate to new stack/framework
        full_rebuild_inside_repo — rewrite the repo from scratch
    """
    req_lower = request.lower()
    file_count = len(files)

    # Full rebuild signals
    if re.search(
        r"\brewrite\b.*\bfrom scratch\b|\bcompletely rebuild\b|\bstart over\b",
        req_lower,
    ):
        return "full_rebuild_inside_repo"

    # Migration signals
    if re.search(
        r"\bmigrate\b|\bconvert\b.*\bto\b|\bport\b.*\bto\b|\brefactor.*stack\b",
        req_lower,
    ):
        return "repo_migration"

    # Full app completion signals
    if re.search(
        r"\bbuild.*complete\b|\bcomplete.*(?:app|website|site)\b|\bfinish.*(?:app|site)\b"
        r"|\bimplement.*everything\b"
        r"|\b(?:make|get).*(?:go.?live|production).?ready\b"
        r"|\bfull.?stack\b.*\bcomplete\b"
        r"|\badd.*all.*(?:pages?|routes?|features?)\b"
        r"|\bdescribed in.*repo\b|\bbuild.*what.*described\b"
        # Additional patterns: "complete this website", "go live ready", etc.
        r"|\bcomplete.*(?:this|the)\s+(?:website|site|repo|app)\b"
        r"|\bgo.?live.?ready\b|\bget.*(?:it|this).*(?:go.?live|live.?ready)\b"
        r"|\bfinish.*(?:this|the).*(?:repo|website|app|site)\b"
        r"|\bbuild.*(?:the\s+)?full.*app\b|\bcomplete.*(?:the\s+)?(?:build|project)\b"
        r"|\bget.*(?:it|this).*(?:production|prod).?ready\b",
        req_lower,
    ):
        return "full_app_completion"

    # Production hardening
    if re.search(
        r"\bsecur\w+\b|\bharden\b|\bproduction.?ready\b|\bauth\w*\b.*\b(?:add|implement|set up)\b"
        r"|\brate.?limit\b|\bci/?cd\b|\bdeploy\b.*\bready\b",
        req_lower,
    ):
        return "production_hardening"

    # Redesign signals
    if re.search(
        r"\bredesign\b|\bnew design\b|\boverhaul\b|\blooks?\b.*\bdifferent\b|\bnew look\b",
        req_lower,
    ):
        return "redesign"

    # Feature add
    if re.search(
        r"\badd\b.*\b(?:page|feature|section|route|api|component|auth|login|dashboard)\b"
        r"|\bimplement\b.*\b(?:feature|page|flow)\b"
        r"|\bcreate\b.*\b(?:page|route|component)\b",
        req_lower,
    ):
        return "feature_add"

    # Bug fix
    if re.search(
        r"\bfix\b|\bbug\b|\bcrash\b|\berror\b|\bbroken\b|\bfailing\b|\bnot working\b",
        req_lower,
    ):
        return "bug_fix"

    # Default: small patch for small files, feature_add for larger repos
    if file_count <= 5:
        return "small_patch"
    return "small_patch"
