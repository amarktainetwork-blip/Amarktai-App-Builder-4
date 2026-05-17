"""
Stack Decision Engine for Amarktai App Builder.

Given a user's build intent, returns a structured decision:
- recommended_mode
- complexity
- recommended_tier
- requires_upgrade_confirmation
- upgrade_reason
- stack (frontend/backend/database/auth/realtime/queue/deployment)
- preview_strategy
- required_files
- safety_notes
"""
from __future__ import annotations

from typing import Any

from app.services.tier_service import normalize_quality_tier

# ── Mode families ──────────────────────────────────────────────────────────────

RESEARCH_MODES = {"research"}
STATIC_MODES = {"landing_page", "website", "media_page"}
APP_MODES = {"web_app", "pwa"}
FULLSTACK_MODES = {"full_stack", "dashboard", "admin_panel", "ecommerce_scaffold", "booking_portal", "ai_chat_rag_app", "crm_dashboard"}
SERVICE_MODES = {"api_service", "automation_bot"}
BOT_MODES = {"trading_bot_scaffold"}
IMPORT_MODES = {"repo_fix"}
ALL_MODES = (RESEARCH_MODES | STATIC_MODES | APP_MODES |
             FULLSTACK_MODES | SERVICE_MODES | BOT_MODES | IMPORT_MODES)

# Required files by mode
REQUIRED_FILES: dict[str, list[str]] = {
    "research": [],
    "landing_page": ["index.html", "styles.css", "script.js", "README.md", "amarktai.project.json", "preview-manifest.json"],
    "website": ["index.html", "styles.css", "script.js", "README.md", "amarktai.project.json", "preview-manifest.json"],
    "media_page": ["index.html", "styles.css", "script.js", "README.md", "amarktai.project.json", "preview-manifest.json"],
    "web_app": ["index.html", "styles.css", "app.js", "README.md", "amarktai.project.json"],
    "pwa": ["index.html", "styles.css", "app.js", "manifest.json", "service-worker.js",
            "README.md", "amarktai.project.json"],
    "full_stack": ["README.md", ".env.example", "docker-compose.yml", "amarktai.project.json"],
    "dashboard": ["README.md", "amarktai.project.json"],
    "admin_panel": ["README.md", "amarktai.project.json"],
    "ecommerce_scaffold": ["README.md", ".env.example", "amarktai.project.json"],
    "booking_portal": ["README.md", ".env.example", "amarktai.project.json"],
    "ai_chat_rag_app": ["README.md", ".env.example", "amarktai.project.json"],
    "crm_dashboard": ["README.md", "amarktai.project.json"],
    "api_service": ["README.md", ".env.example", "amarktai.project.json"],
    "automation_bot": ["README.md", ".env.example", "amarktai.project.json"],
    "trading_bot_scaffold": ["README.md", ".env.example", "amarktai.project.json"],
    "repo_fix": [],
}

# Default stacks by mode
_STACK_DEFAULTS: dict[str, dict[str, str]] = {
    "research": {
        "frontend": "none", "backend": "none", "database": "none",
        "auth": "none", "realtime": "none", "queue": "none", "deployment": "none",
    },
    "landing_page": {
        "frontend": "HTML + CSS + Vanilla JS", "backend": "none", "database": "none",
        "auth": "none", "realtime": "none", "queue": "none", "deployment": "static hosting",
    },
    "website": {
        "frontend": "HTML + CSS + Vanilla JS", "backend": "none", "database": "none",
        "auth": "none", "realtime": "none", "queue": "none", "deployment": "static hosting",
    },
    "media_page": {
        "frontend": "HTML + CSS + Vanilla JS", "backend": "none", "database": "none",
        "auth": "none", "realtime": "none", "queue": "none", "deployment": "static hosting",
    },
    "web_app": {
        "frontend": "HTML + CSS + Vanilla JS", "backend": "none", "database": "localStorage",
        "auth": "none", "realtime": "none", "queue": "none", "deployment": "static hosting",
    },
    "pwa": {
        "frontend": "HTML + CSS + Vanilla JS (PWA)", "backend": "none",
        "database": "IndexedDB / localStorage", "auth": "none",
        "realtime": "none", "queue": "none", "deployment": "static hosting",
    },
    "full_stack": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB",
        "auth": "JWT", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "dashboard": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB",
        "auth": "JWT", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "admin_panel": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MariaDB",
        "auth": "JWT + RBAC", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "ecommerce_scaffold": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB",
        "auth": "JWT", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "booking_portal": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB",
        "auth": "JWT", "realtime": "SSE / WebSocket", "queue": "async task queue", "deployment": "Docker / VPS",
    },
    "ai_chat_rag_app": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB + vector store",
        "auth": "JWT", "realtime": "SSE / WebSocket", "queue": "async task queue", "deployment": "Docker / VPS",
    },
    "crm_dashboard": {
        "frontend": "React / Vite", "backend": "FastAPI", "database": "MongoDB",
        "auth": "JWT", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "api_service": {
        "frontend": "none", "backend": "FastAPI", "database": "MongoDB",
        "auth": "API key / JWT", "realtime": "none", "queue": "none", "deployment": "Docker / VPS",
    },
    "automation_bot": {
        "frontend": "none", "backend": "FastAPI worker", "database": "MongoDB / Redis",
        "auth": "API key", "realtime": "SSE / WebSocket", "queue": "async queue", "deployment": "Docker / VPS",
    },
    "trading_bot_scaffold": {
        "frontend": "React dashboard (paper mode only)", "backend": "FastAPI + async worker",
        "database": "MongoDB", "auth": "JWT + API key",
        "realtime": "WebSocket", "queue": "async task queue", "deployment": "Docker / VPS (review before live)",
    },
    "repo_fix": {
        "frontend": "preserved from source", "backend": "preserved from source",
        "database": "preserved from source", "auth": "preserved from source",
        "realtime": "none", "queue": "none", "deployment": "preserved from source",
    },
}


def _apply_stack_preference(stack: dict[str, str], stack_pref: str | None,
                             db_pref: str | None) -> dict[str, str]:
    """Adjust stack based on user preferences."""
    if not stack_pref:
        return stack
    pref = stack_pref.lower()
    if "react" in pref or "vite" in pref:
        if stack["frontend"] not in ("none", "preserved from source"):
            stack["frontend"] = "React / Vite"
    elif "vue" in pref:
        if stack["frontend"] not in ("none", "preserved from source"):
            stack["frontend"] = "Vue 3 / Vite"
    elif "vanilla" in pref or "html" in pref:
        if stack["frontend"] not in ("none", "preserved from source"):
            stack["frontend"] = "HTML + CSS + Vanilla JS"
    if "express" in pref or "node" in pref:
        if stack["backend"] not in ("none", "preserved from source"):
            stack["backend"] = "Node.js / Express"
    elif "flask" in pref:
        if stack["backend"] not in ("none", "preserved from source"):
            stack["backend"] = "Flask"
    if db_pref:
        db_lower = db_pref.lower()
        if "mysql" in db_lower or "mariadb" in db_lower or "relational" in db_lower:
            stack["database"] = "MariaDB / MySQL"
        elif "postgres" in db_lower:
            stack["database"] = "PostgreSQL"
        elif "sqlite" in db_lower:
            stack["database"] = "SQLite"
        elif "redis" in db_lower:
            stack["database"] = "Redis"
        elif "mongo" in db_lower:
            stack["database"] = "MongoDB"
    return stack


def decide_stack(
    *,
    prompt: str = "",
    mode: str = "web_app",
    quality_tier: str = "standard",
    stack_preference: str | None = None,
    database_preference: str | None = None,
    auth_required: bool = False,
    realtime_required: bool = False,
    media_requirements: str | None = None,
    deployment_target: str | None = None,
) -> dict[str, Any]:
    """
    Return a full stack decision dict.

    Inputs match Phase 4 spec. Does not call any LLM; purely rule-based.
    """
    mode = mode.lower().strip() if mode else "web_app"
    if mode not in ALL_MODES:
        mode = "web_app"

    quality_tier = normalize_quality_tier(quality_tier)

    prompt_lower = prompt.lower()

    # ── complexity classification ──────────────────────────────
    if mode in RESEARCH_MODES | STATIC_MODES:
        complexity = "simple"
    elif mode in APP_MODES:
        complexity = "simple" if not (auth_required or realtime_required) else "standard"
    elif mode in FULLSTACK_MODES | SERVICE_MODES:
        complexity = "standard"
    elif mode in BOT_MODES:
        complexity = "high_risk"
    elif mode in IMPORT_MODES:
        complexity = "standard"
    else:
        complexity = "standard"

    # Upgrade prompt complexity if certain keywords present
    # Use word-boundary-safe patterns to avoid false positives from common words
    _upgrade_keywords = (
        r"\bai\b", r"\bml\b", r"\btrading\b", r"\bpayment\b", r"\bstripe\b",
        r"\breal-time\b", r"\brealtime\b", r"\bwebsocket\b",
    )
    import re as _re
    if any(_re.search(kw, prompt_lower) for kw in _upgrade_keywords):
        if complexity == "simple":
            complexity = "standard"
        elif complexity == "standard":
            complexity = "advanced"

    # ── recommended_tier decision ──────────────────────────────
    recommended_tier: str
    requires_upgrade_confirmation = False
    upgrade_reason: str | None = None

    if complexity in ("simple", "standard"):
        recommended_tier = "standard"
    elif complexity == "advanced":
        recommended_tier = "premium"
        if quality_tier == "standard":
            requires_upgrade_confirmation = True
            upgrade_reason = (
                f"This {mode} involves advanced features. "
                f"Premium is recommended for best results. "
                f"You selected '{quality_tier}'."
            )
    elif complexity == "high_risk":
        recommended_tier = "premium"
        if quality_tier == "standard":
            requires_upgrade_confirmation = True
            upgrade_reason = (
                "Trading bots and high-risk automation require thorough code generation. "
                "Premium is strongly recommended."
            )
    else:
        recommended_tier = quality_tier

    # ── build the stack ───────────────────────────────────────
    stack = dict(_STACK_DEFAULTS.get(mode, _STACK_DEFAULTS["web_app"]))
    stack = _apply_stack_preference(stack, stack_preference, database_preference)

    # Realtime override
    if realtime_required and stack.get("realtime") == "none":
        stack["realtime"] = "WebSocket / SSE"

    # Auth override
    if auth_required and stack.get("auth") == "none":
        if stack.get("backend") not in ("none", "preserved from source"):
            stack["auth"] = "JWT"
        else:
            stack["auth"] = "localStorage token (frontend-only)"

    # Deployment target
    if deployment_target:
        stack["deployment"] = deployment_target

    # ── preview_strategy ──────────────────────────────────────
    if mode in RESEARCH_MODES:
        preview_strategy = "brief_only"
    elif mode in STATIC_MODES | APP_MODES:
        preview_strategy = "iframe"
    elif mode in FULLSTACK_MODES | SERVICE_MODES | BOT_MODES | IMPORT_MODES:
        preview_strategy = "repo_structure"
    else:
        preview_strategy = "repo_structure"

    # ── safety_notes ──────────────────────────────────────────
    safety_notes: list[str] = []
    if mode == "trading_bot_scaffold":
        safety_notes += [
            "Paper / simulation mode is enabled by default. Live trading is disabled until explicitly enabled.",
            "Risk controls and kill switch are mandatory. Review all risk parameters before going live.",
            "No profit guarantees. Past performance does not indicate future results.",
            "Thoroughly test in paper mode and with a regulated broker before live deployment.",
        ]
    if mode == "automation_bot":
        safety_notes += [
            "Automation bots must be reviewed for rate limits, error handling, and failure modes.",
            "Never hardcode credentials. Use environment variables.",
            "Include logging and alerting before production deployment.",
        ]
    if mode in FULLSTACK_MODES | SERVICE_MODES | BOT_MODES:
        safety_notes.append("Never commit real secrets. Use .env.example and add .env to .gitignore.")
    if "payment" in prompt_lower or "stripe" in prompt_lower:
        safety_notes.append("Payment integrations require PCI compliance review and live key testing outside this tool.")
    if media_requirements and "generat" in (media_requirements or "").lower():
        safety_notes.append("Media generation depends on live provider capability truth and persists manifest evidence when used.")

    # ── required_files by mode ────────────────────────────────
    required_files = list(REQUIRED_FILES.get(mode, []))

    return {
        "recommended_mode": mode,
        "complexity": complexity,
        "quality_tier": quality_tier,
        "recommended_tier": recommended_tier,
        "requires_upgrade_confirmation": requires_upgrade_confirmation,
        "upgrade_reason": upgrade_reason,
        "stack": stack,
        "preview_strategy": preview_strategy,
        "required_files": required_files,
        "safety_notes": safety_notes,
    }
