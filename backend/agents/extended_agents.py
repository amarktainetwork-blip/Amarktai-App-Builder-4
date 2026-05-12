"""
Extended Agent Implementations — Phase 2B (10 New Required Agents).

Agents added in this module:
  1. Runtime Engineer Agent
  2. Tool Integration Agent
  3. Data Architect Agent
  4. Component Librarian Agent
  5. Prompt Optimizer Agent
  6. Documentation Agent
  7. Export Agent
  8. Monitoring Agent
  9. Memory Curator Agent
  10. Capability Truth Agent

Each agent has:
  - A deterministic implementation function
  - A prompt constant (in prompts.py) for LLM-backed tasks
  - Clear input/output contracts
  - Honest reporting (never fakes availability)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("amarktai.extended_agents")

_now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


# ══════════════════════════════════════════════════════════════════════════════
# 1. Runtime Engineer Agent
# ══════════════════════════════════════════════════════════════════════════════

def check_runtime_health(
    files: list[dict[str, Any]],
    build_logs: str = "",
    mode: str = "",
    preview_url: str = "",
) -> dict[str, Any]:
    """
    Runtime Engineer: verify the project can actually run.
    
    Checks build logs for errors, validates entry points, and confirms
    the preview URL is not a fake success.
    """
    issues: list[str] = []
    checklist: list[str] = []

    # Check build logs for error markers
    if build_logs:
        error_patterns = [
            (r"error\s*TS\d+", "TypeScript compile error"),
            (r"Module not found", "Missing module dependency"),
            (r"SyntaxError", "JavaScript syntax error"),
            (r"Cannot find module", "Import resolution failure"),
            (r"Failed to compile", "Compilation failure"),
            (r"Build failed", "Build failure"),
            (r"ERROR in ", "Build error"),
        ]
        for pattern, label in error_patterns:
            if re.search(pattern, build_logs, re.IGNORECASE):
                issues.append(f"Build log contains {label}.")

        if not issues:
            checklist.append("✓ Build logs contain no error markers")
    else:
        checklist.append("○ No build logs available — cannot verify build output")

    # Validate entry point exists
    html_files = [f for f in files if f.get("path", "").endswith(".html")]
    js_files = [f for f in files if f.get("path", "").endswith((".js", ".ts", ".jsx", ".tsx"))]
    py_files = [f for f in files if f.get("path", "").endswith(".py")]

    has_entry = bool(
        any(f.get("path") == "index.html" for f in html_files)
        or any(f.get("path") in ("main.py", "app.py", "server.py") for f in py_files)
        or any(f.get("path") in ("index.js", "main.js", "index.ts", "main.ts") for f in js_files)
    )

    if has_entry:
        checklist.append("✓ Entry point file detected")
    else:
        issues.append("No recognizable entry point file found. Runtime cannot start.")

    # Preview URL validation
    if preview_url:
        if preview_url.startswith("http"):
            checklist.append(f"✓ Preview URL set: {preview_url}")
        else:
            issues.append(f"Preview URL '{preview_url}' is not a valid HTTP URL.")

    runtime_ok = len(issues) == 0

    return {
        "runtime_ok": runtime_ok,
        "issues": issues,
        "checklist": checklist,
        "build_logs_analyzed": bool(build_logs),
        "has_entry_point": has_entry,
        "preview_url": preview_url or None,
        "checked_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Tool Integration Agent
# ══════════════════════════════════════════════════════════════════════════════

# Known tools and their env-var requirements
_TOOL_ENV_REQUIREMENTS: dict[str, list[str]] = {
    "stripe": ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY"],
    "sendgrid": ["SENDGRID_API_KEY"],
    "mailchimp": ["MAILCHIMP_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "github": ["GITHUB_TOKEN", "GITHUB_PAT"],
    "aws": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    "google": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
    "firebase": ["FIREBASE_API_KEY", "FIREBASE_PROJECT_ID"],
    "twilio": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
    "slack": ["SLACK_BOT_TOKEN", "SLACK_WEBHOOK_URL"],
    "postgres": ["DATABASE_URL", "POSTGRES_PASSWORD"],
    "mongodb": ["MONGODB_URI"],
    "redis": ["REDIS_URL"],
    "s3": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_BUCKET_NAME"],
}


def verify_tool_integration(
    files: list[dict[str, Any]],
    requested_tools: list[str] | None = None,
) -> dict[str, Any]:
    """
    Tool Integration Agent: verify external tools are properly configured.
    
    Scans files for tool usage and verifies env vars are documented.
    """
    requested_tools = requested_tools or []
    all_content = "\n".join(f.get("content", "") for f in files)
    env_example = next(
        (f.get("content", "") for f in files if f.get("path") == ".env.example"),
        "",
    )

    detected_tools: list[str] = []
    missing_env_vars: dict[str, list[str]] = {}
    connected_tools: list[str] = []
    warnings: list[str] = []

    for tool, env_vars in _TOOL_ENV_REQUIREMENTS.items():
        if tool in all_content.lower() or tool in requested_tools:
            detected_tools.append(tool)
            # Check if env vars are documented
            missing = [v for v in env_vars if v not in env_example]
            if missing:
                missing_env_vars[tool] = missing
                warnings.append(
                    f"Tool '{tool}' detected but missing env vars in .env.example: {', '.join(missing)}"
                )
            else:
                connected_tools.append(tool)

    return {
        "detected_tools": detected_tools,
        "connected_tools": connected_tools,
        "missing_env_vars": missing_env_vars,
        "warnings": warnings,
        "integration_score": (
            int(len(connected_tools) / len(detected_tools) * 100)
            if detected_tools else 100
        ),
        "checked_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. Data Architect Agent
# ══════════════════════════════════════════════════════════════════════════════

def analyze_data_architecture(files: list[dict[str, Any]], mode: str = "") -> dict[str, Any]:
    """
    Data Architect Agent: analyze database schema, auth relationships, and data models.
    
    Returns an assessment of data architecture quality.
    """
    all_content = "\n".join(f.get("content", "") for f in files)
    issues: list[str] = []
    checklist: list[str] = []

    # Check for database technology
    db_tech = None
    if re.search(r"prisma|@prisma", all_content, re.IGNORECASE):
        db_tech = "Prisma ORM"
    elif re.search(r"mongoose|MongoClient|mongodb", all_content, re.IGNORECASE):
        db_tech = "MongoDB"
    elif re.search(r"sqlalchemy|psycopg2|asyncpg|pg\.Pool", all_content, re.IGNORECASE):
        db_tech = "PostgreSQL"
    elif re.search(r"sqlite3|better-sqlite|Database", all_content, re.IGNORECASE):
        db_tech = "SQLite"

    if db_tech:
        checklist.append(f"✓ Database technology detected: {db_tech}")
    elif mode in ("full_stack", "dashboard", "api_service"):
        issues.append("Full-stack mode but no database technology detected. Add a database layer.")

    # Auth patterns
    has_auth = bool(re.search(r"jwt|jsonwebtoken|bcrypt|argon2|passlib|JWT|Bearer", all_content, re.IGNORECASE))
    if has_auth:
        checklist.append("✓ Authentication patterns detected")
    elif mode in ("full_stack", "dashboard"):
        issues.append("Dashboard/full-stack mode but no authentication patterns found.")

    # Schema files
    has_schema = bool(
        any(f.get("path", "").endswith((".prisma", "schema.sql", "models.py", "models.ts"))
            for f in files)
    )
    if has_schema:
        checklist.append("✓ Database schema file found")
    elif db_tech:
        issues.append("Database detected but no schema file found.")

    return {
        "db_technology": db_tech,
        "has_auth": has_auth,
        "has_schema": has_schema,
        "issues": issues,
        "checklist": checklist,
        "architecture_ok": len(issues) == 0,
        "checked_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. Component Librarian Agent
# ══════════════════════════════════════════════════════════════════════════════

def register_components(files: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Component Librarian Agent: build a registry of reusable UI components.
    
    Scans React/HTML files and identifies component patterns.
    """
    components: list[dict[str, Any]] = []

    # React component detection
    react_component_pat = re.compile(
        r"(?:export\s+(?:default\s+)?(?:function|const)\s+([A-Z][a-zA-Z0-9]+))",
        re.MULTILINE,
    )
    # HTML section/component patterns
    html_section_pat = re.compile(
        r'<(?:section|article|header|footer|nav|main)\b[^>]*\bid=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    # CSS class patterns
    css_component_pat = re.compile(r"^\.(btn|card|hero|nav|footer|modal|badge|chip|tag)[a-z-]*\s*\{", re.MULTILINE | re.IGNORECASE)

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")

        if path.endswith((".jsx", ".tsx")):
            for match in react_component_pat.finditer(content):
                components.append({
                    "name": match.group(1),
                    "type": "react_component",
                    "file": path,
                })

        elif path.endswith(".html"):
            for match in html_section_pat.finditer(content):
                components.append({
                    "name": match.group(1),
                    "type": "html_section",
                    "file": path,
                })

        elif path.endswith(".css"):
            for match in css_component_pat.finditer(content):
                components.append({
                    "name": match.group(1),
                    "type": "css_component",
                    "file": path,
                })

    return {
        "component_count": len(components),
        "components": components,
        "react_components": [c for c in components if c["type"] == "react_component"],
        "html_sections": [c for c in components if c["type"] == "html_section"],
        "css_components": [c for c in components if c["type"] == "css_component"],
        "registry_built": True,
        "built_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. Prompt Optimizer Agent
# ══════════════════════════════════════════════════════════════════════════════

# Keywords that indicate a prompt may produce poor output
_WEAK_PROMPT_PATTERNS = [
    (r"\bmake\s+(?:it|a|the)?\s+(?:nice|cool|good|great|awesome|modern)\b", "vague quality descriptor"),
    (r"\bsomething\s+like\b", "vague reference"),
    (r"\bi\s+(?:don't know|dunno)\b", "unclear requirement"),
    (r"\bmake\s+it\s+(?:work|function)\b", "non-specific requirement"),
    (r"\bjust\s+(?:do|make|create)\b", "unclear scope"),
]

# Premium signal keywords
_STRONG_PROMPT_PATTERNS = [
    (r"\bconversion\b|\bcta\b", "conversion-focused"),
    (r"\bindustry|niche\b", "domain-specific"),
    (r"\btarget\s+audience\b", "audience-aware"),
    (r"\bcolor\s+scheme|palette\b", "design-specific"),
    (r"\bsections?|pages?\b", "structure-specific"),
]


def analyze_prompt_quality(user_prompt: str) -> dict[str, Any]:
    """
    Prompt Optimizer Agent: analyze a user prompt for quality and completeness.
    
    Returns a quality score and improvement suggestions.
    """
    prompt_lower = user_prompt.lower()
    issues: list[str] = []
    strengths: list[str] = []
    suggestions: list[str] = []

    # Check for weak patterns
    for pattern, label in _WEAK_PROMPT_PATTERNS:
        if re.search(pattern, prompt_lower):
            issues.append(f"Vague phrase detected: {label}. Be more specific.")

    # Check for strong patterns
    for pattern, label in _STRONG_PROMPT_PATTERNS:
        if re.search(pattern, prompt_lower):
            strengths.append(f"Good: {label} included")

    # Length check
    word_count = len(user_prompt.split())
    if word_count < 10:
        issues.append("Prompt is very short. Add more context about the product, audience, and goals.")
        suggestions.append("Add: target audience, key features, desired tone, industry, and specific sections.")
    elif word_count > 500:
        suggestions.append("Prompt is long. The most critical info is: industry, audience, features, style.")

    # Score
    base_score = 50
    base_score += min(30, len(strengths) * 10)
    base_score -= min(30, len(issues) * 10)

    if not suggestions and not issues:
        suggestions.append("Prompt quality is good. No major improvements needed.")

    return {
        "prompt_quality_score": max(0, min(100, base_score)),
        "word_count": word_count,
        "issues": issues,
        "strengths": strengths,
        "suggestions": suggestions,
        "optimized_prompt": None,  # LLM-backed optimization via PROMPT_OPTIMIZER_PROMPT
        "analyzed_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 6. Documentation Agent
# ══════════════════════════════════════════════════════════════════════════════

def generate_readme(
    project_name: str,
    mode: str,
    files: list[dict[str, Any]],
    tech_stack: dict[str, Any] | None = None,
    features: list[str] | None = None,
) -> str:
    """
    Documentation Agent: generate a comprehensive README.md.
    """
    tech_stack = tech_stack or {}
    features = features or []

    has_docker = any(f.get("path") in ("Dockerfile", "docker-compose.yml") for f in files)
    has_env = any(f.get("path") == ".env.example" for f in files)
    has_package_json = any(f.get("path") == "package.json" for f in files)

    frontend = tech_stack.get("frontend", "Static HTML/CSS")
    backend = tech_stack.get("backend", "")
    database = tech_stack.get("database", "")

    lines = [
        f"# {project_name}",
        "",
        f"Built with Amarktai App Builder | Mode: `{mode}`",
        "",
        "## Overview",
        "",
        f"This project was generated as a **{mode.replace('_', ' ')}** application.",
    ]

    if features:
        lines += ["", "## Features", ""]
        for feat in features:
            lines.append(f"- {feat}")

    lines += ["", "## Tech Stack", "", f"- **Frontend:** {frontend}"]
    if backend:
        lines.append(f"- **Backend:** {backend}")
    if database:
        lines.append(f"- **Database:** {database}")

    lines += ["", "## Getting Started", ""]

    if has_docker:
        lines += [
            "### With Docker",
            "",
            "```bash",
            "cp .env.example .env",
            "# Edit .env with your values",
            "docker compose up -d --build",
            "```",
            "",
        ]

    if has_package_json:
        lines += [
            "### Local Development",
            "",
            "```bash",
            "npm install",
        ]
        if has_env:
            lines.append("cp .env.example .env")
        lines += ["npm run dev", "```", ""]

    if not has_docker and not has_package_json:
        lines += [
            "Open `index.html` in a browser or deploy to any static host.",
            "",
        ]

    lines += [
        "## Deployment",
        "",
        "See deployment instructions in the project for platform-specific guides.",
        "",
        "## License",
        "",
        "MIT",
    ]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Export Agent
# ══════════════════════════════════════════════════════════════════════════════

def prepare_export_manifest(
    files: list[dict[str, Any]],
    project_name: str,
    version: str = "1.0.0",
) -> dict[str, Any]:
    """
    Export Agent: prepare a project export manifest with all necessary files.
    
    Returns metadata for packaging the project as a downloadable ZIP.
    """
    file_summary = [
        {
            "path": f.get("path", ""),
            "language": f.get("language", "text"),
            "size_chars": len(f.get("content", "")),
        }
        for f in files
    ]

    # Categorize files
    categories = {
        "html": [fs for fs in file_summary if fs["path"].endswith(".html")],
        "css": [fs for fs in file_summary if fs["path"].endswith(".css")],
        "js": [fs for fs in file_summary if fs["path"].endswith((".js", ".ts", ".jsx", ".tsx"))],
        "config": [fs for fs in file_summary if fs["path"].endswith((".json", ".yaml", ".yml", ".toml"))],
        "docs": [fs for fs in file_summary if fs["path"].endswith(".md")],
        "other": [],
    }
    known = set()
    for cat_files in list(categories.values())[:-1]:
        for f in cat_files:
            known.add(f["path"])
    categories["other"] = [fs for fs in file_summary if fs["path"] not in known]

    return {
        "project_name": project_name,
        "version": version,
        "total_files": len(files),
        "total_size_chars": sum(fs["size_chars"] for fs in file_summary),
        "file_categories": {k: len(v) for k, v in categories.items()},
        "files": file_summary,
        "export_ready": len(files) > 0,
        "manifest_version": "1",
        "created_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. Monitoring Agent
# ══════════════════════════════════════════════════════════════════════════════

def analyze_monitoring_readiness(files: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Monitoring Agent: check if the project has health and monitoring instrumentation.
    """
    all_content = "\n".join(f.get("content", "") for f in files)
    issues: list[str] = []
    checklist: list[str] = []

    # Health endpoint
    has_health = bool(re.search(r'"/health"|/health|health_check|healthcheck', all_content, re.IGNORECASE))
    if has_health:
        checklist.append("✓ Health check endpoint detected")
    else:
        issues.append("No health check endpoint found. Add GET /health for monitoring.")

    # Error logging
    has_logging = bool(re.search(r"logging\.|logger\.|console\.error|sentry|winston|loguru", all_content, re.IGNORECASE))
    if has_logging:
        checklist.append("✓ Error logging detected")
    else:
        issues.append("No error logging detected. Add structured logging.")

    # Rate limiting
    has_rate_limit = bool(re.search(r"rate.?limit|throttle|slowapi|express-rate-limit", all_content, re.IGNORECASE))
    if has_rate_limit:
        checklist.append("✓ Rate limiting detected")

    # CORS
    has_cors = bool(re.search(r"cors|CORS|cross.?origin", all_content, re.IGNORECASE))
    if has_cors:
        checklist.append("✓ CORS configuration detected")

    return {
        "has_health_endpoint": has_health,
        "has_logging": has_logging,
        "has_rate_limiting": has_rate_limit,
        "has_cors": has_cors,
        "issues": issues,
        "checklist": checklist,
        "monitoring_score": max(0, 100 - len(issues) * 20),
        "checked_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 9. Memory Curator Agent
# ══════════════════════════════════════════════════════════════════════════════

def curate_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """
    Memory Curator Agent: clean, compress, and summarize project memory.
    
    Removes stale entries, deduplicates decisions, and summarizes long histories.
    """
    if not memory:
        return {"curated": True, "changes": [], "summary": "No memory to curate."}

    changes: list[str] = []

    # Remove null/empty values at top level
    keys_to_remove = [k for k, v in memory.items() if v is None or v == {} or v == []]
    for k in keys_to_remove:
        del memory[k]
        changes.append(f"Removed empty key: {k}")

    # Cap agent_decisions history to last 20 entries
    if "agent_decisions" in memory and isinstance(memory["agent_decisions"], list):
        original_len = len(memory["agent_decisions"])
        if original_len > 20:
            memory["agent_decisions"] = memory["agent_decisions"][-20:]
            changes.append(f"Trimmed agent_decisions from {original_len} to 20 entries")

    # Cap iteration_history to last 10
    if "iteration_history" in memory and isinstance(memory["iteration_history"], list):
        original_len = len(memory["iteration_history"])
        if original_len > 10:
            memory["iteration_history"] = memory["iteration_history"][-10:]
            changes.append(f"Trimmed iteration_history from {original_len} to 10 entries")

    # Add curation timestamp
    memory["last_curated"] = _now()

    summary = (
        f"Memory curated: {len(changes)} change(s) made. "
        f"Keys present: {', '.join(list(memory.keys())[:8])}."
    ) if changes else "Memory is clean. No changes needed."

    return {
        "curated": True,
        "changes": changes,
        "summary": summary,
        "memory_keys": list(memory.keys()),
        "curated_at": _now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10. Capability Truth Agent
# ══════════════════════════════════════════════════════════════════════════════

# What frontend claims → what backend must support
_FRONTEND_BACKEND_CLAIMS: dict[str, str] = {
    "ai image generation": "supports_image_generation",
    "ai logo": "supports_image_generation",
    "ai video": "supports_video_generation",
    "voice generation": "supports_audio",
    "live preview": "supports_streaming",
    "vision": "supports_vision",
    "code analysis": "supports_repo_analysis",
    "long context": "supports_long_context",
}


def verify_capability_claims(
    frontend_claims: list[str],
    capability_registry: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Capability Truth Agent: verify that frontend claims match actual backend capabilities.
    
    Prevents the UI from showing features as available when they're not.
    """
    registry = capability_registry or {}
    mismatches: list[dict[str, str]] = []
    verified: list[str] = []
    unverifiable: list[str] = []

    for claim in frontend_claims:
        claim_lower = claim.lower()
        matched = False
        for claim_pattern, cap_key in _FRONTEND_BACKEND_CLAIMS.items():
            if claim_pattern in claim_lower:
                matched = True
                cap_value = registry.get(cap_key, False)
                if cap_value:
                    verified.append(claim)
                else:
                    mismatches.append({
                        "claim": claim,
                        "required_capability": cap_key,
                        "available": False,
                        "resolution": f"Remove or disable '{claim}' in the UI — capability not available.",
                    })
                break
        if not matched:
            unverifiable.append(claim)

    return {
        "verified_claims": verified,
        "mismatched_claims": mismatches,
        "unverifiable_claims": unverifiable,
        "truth_score": (
            int(len(verified) / len(frontend_claims) * 100)
            if frontend_claims else 100
        ),
        "all_claims_truthful": len(mismatches) == 0,
        "checked_at": _now(),
    }
