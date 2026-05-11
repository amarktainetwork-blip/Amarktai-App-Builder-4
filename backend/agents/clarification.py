"""
Clarification engine for Amarktai App Builder.

Detects when a user prompt is too vague for reliable generation and returns
focused questions to ask before starting the build pipeline.

Rules:
- Ask at most 5 focused questions.
- If enough info exists, do NOT ask unnecessary questions.
- Proceed with sensible defaults when assumptions are safe.
"""
from __future__ import annotations

import re
from typing import Any

# ── Vagueness detection ──────────────────────────────────────────────────────

# Short prompts or prompts that only describe a generic concept
_MIN_WORDS_FOR_CLEAR_PROMPT = 12
_VAGUE_INTROS_WORDS = {"app", "site", "website", "platform", "saas", "dashboard", "tool", "product", "thing", "project"}
_VAGUE_PREFIXES = {"build", "make", "create", "generate"}

# Keywords that imply a known mode — prompt is likely specific enough
_MODE_KEYWORDS: dict[str, str] = {
    "landing page": "landing_page",
    "landing-page": "landing_page",
    "multi-page": "website",
    "multi page": "website",
    "5-page": "website",
    "five page": "website",
    "react app": "web_app",
    "vite app": "web_app",
    "pwa": "pwa",
    "progressive web app": "pwa",
    "full stack": "full_stack",
    "full-stack": "full_stack",
    "saas": "full_stack",
    "dashboard": "dashboard",
    "admin panel": "admin_panel",
    "api": "api_service",
    "backend": "api_service",
    "trading bot": "trading_bot_scaffold",
    "automation bot": "automation_bot",
    "research": "research",
    "repo": "repo_fix",
    "github repo": "repo_fix",
}

# Keywords that indicate auth is requested
_AUTH_KEYWORDS = re.compile(
    r"\b(login|logout|register|sign.?up|sign.?in|auth|password|user\s+account|user\s+management|role|admin\s+access)\b",
    re.IGNORECASE,
)

# Keywords that indicate a database choice is mentioned
_DB_KEYWORDS = re.compile(
    r"\b(mongodb|mongo|postgres|postgresql|mysql|mariadb|sqlite|database|db)\b",
    re.IGNORECASE,
)

# Keywords that indicate a framework is mentioned
_FRAMEWORK_KEYWORDS = re.compile(
    r"\b(react|vue|svelte|next\.?js|fastapi|flask|express|django|laravel|rails|tailwind)\b",
    re.IGNORECASE,
)

# Keywords that indicate media is relevant
_MEDIA_KEYWORDS = re.compile(
    r"\b(image|photo|video|music|audio|media|gallery|background image|hero image|pixabay)\b",
    re.IGNORECASE,
)

# Keywords that indicate deployment target
_DEPLOY_KEYWORDS = re.compile(
    r"\b(docker|vps|heroku|vercel|netlify|aws|gcp|azure|kubernetes|k8s|deploy)\b",
    re.IGNORECASE,
)


def _word_count(text: str) -> int:
    return len(text.split())


def _implied_mode(prompt_lower: str) -> str | None:
    for keyword, mode in _MODE_KEYWORDS.items():
        if keyword in prompt_lower:
            return mode
    return None


def _is_vague(prompt: str) -> bool:
    """Return True if the prompt is too vague for reliable generation."""
    stripped = prompt.strip().rstrip(".!?,")
    words_lower = stripped.lower().split()
    # Only 1-3 words total → definitely vague
    if len(words_lower) <= 3:
        # e.g. "build an app", "build site", "make a dashboard"
        non_articles = [w for w in words_lower if w not in ("a", "an", "the", "me")]
        if len(non_articles) <= 2:
            has_vague_obj = any(w in _VAGUE_INTROS_WORDS for w in non_articles)
            has_verb = any(w in _VAGUE_PREFIXES for w in non_articles)
            if has_verb or has_vague_obj:
                return True
    words = _word_count(stripped)
    if words < _MIN_WORDS_FOR_CLEAR_PROMPT:
        # Short prompt — only vague unless it names a specific known mode
        prompt_lower = stripped.lower()
        if _implied_mode(prompt_lower):
            # Named a specific mode — still vague if under 6 words
            if words < 6:
                return True
        else:
            return True
    return False


# ── Question builders ─────────────────────────────────────────────────────────

_QUESTION_MODE = {
    "id": "mode",
    "question": "What type of project do you want to build?",
    "options": [
        "Landing page",
        "Multi-page website",
        "React / Vite web app",
        "PWA (Progressive Web App)",
        "Full-stack SaaS",
        "Dashboard / Admin panel",
        "API / Backend service",
        "Research brief",
        "Import & fix a GitHub repo",
    ],
    "required": True,
}

_QUESTION_FRAMEWORK = {
    "id": "framework",
    "question": "Preferred language / framework? (or leave blank for smart default)",
    "options": [
        "HTML / CSS / Vanilla JS (static)",
        "React / Vite",
        "Next.js",
        "Vue 3 / Vite",
        "Svelte",
        "FastAPI (Python backend)",
        "Express / Node.js",
        "Auto-select best fit",
    ],
    "required": False,
}

_QUESTION_AUTH = {
    "id": "auth_required",
    "question": "Does the app need user authentication (login / register / roles)?",
    "options": ["Yes — login, register, JWT", "No auth needed"],
    "required": True,
}

_QUESTION_DB = {
    "id": "database",
    "question": "Preferred database? (or leave blank for smart default)",
    "options": [
        "MongoDB (flexible documents)",
        "MariaDB / MySQL (relational)",
        "PostgreSQL (relational)",
        "SQLite (lightweight local)",
        "No database",
        "Auto-select best fit",
    ],
    "required": False,
}

_QUESTION_MEDIA = {
    "id": "media",
    "question": "Do you need images or video in the generated project?",
    "options": [
        "AI-generated images (GenX)",
        "Stock images from Pixabay",
        "SVG / CSS visuals only (no external images)",
        "No media needed",
    ],
    "required": False,
}

_QUESTION_DEPLOY = {
    "id": "deployment",
    "question": "Deployment target?",
    "options": [
        "Docker Compose + VPS",
        "Static hosting (GitHub Pages, Netlify, Vercel)",
        "Self-hosted / manual",
        "Not sure yet",
    ],
    "required": False,
}


def check_clarification_needed(
    prompt: str,
    mode: str | None = None,
) -> dict[str, Any]:
    """Analyse the prompt and return clarification questions if needed.

    Returns::

        {
          "needs_clarification": True | False,
          "questions": [...],             # list of question dicts
          "inferred_mode": "...",         # if mode was inferred
          "inferred_auth": True | False,
          "inferred_db": "...",
          "assumptions": ["..."],         # what the system will assume if not asked
        }
    """
    prompt_lower = prompt.lower().strip()
    inferred_mode = _implied_mode(prompt_lower)
    inferred_auth = bool(_AUTH_KEYWORDS.search(prompt))
    inferred_db = bool(_DB_KEYWORDS.search(prompt))
    has_framework = bool(_FRAMEWORK_KEYWORDS.search(prompt))
    has_media = bool(_MEDIA_KEYWORDS.search(prompt))
    has_deploy = bool(_DEPLOY_KEYWORDS.search(prompt))

    questions: list[dict] = []
    assumptions: list[str] = []

    # Determine if clarification is needed
    is_vague = _is_vague(prompt)

    # If mode is not inferred and prompt is vague, ask for mode
    if not inferred_mode and is_vague:
        questions.append(_QUESTION_MODE)

    # If mode is known but prompt is vague, still skip mode question
    if not has_framework and (is_vague or not inferred_mode):
        questions.append(_QUESTION_FRAMEWORK)
    else:
        assumptions.append("Framework: auto-selected based on project type")

    # Auth — only ask if not clearly mentioned in prompt
    if not inferred_auth and (is_vague or inferred_mode in {"full_stack", "dashboard", "admin_panel"}):
        questions.append(_QUESTION_AUTH)
    elif inferred_auth:
        assumptions.append("Auth: JWT + hashed passwords (requested in prompt)")
    else:
        assumptions.append("Auth: none (not requested)")

    # DB — only ask if not mentioned and likely relevant
    if not inferred_db and inferred_mode in {
        "full_stack", "dashboard", "admin_panel", "api_service", "web_app",
    }:
        questions.append(_QUESTION_DB)
    else:
        assumptions.append("Database: auto-selected based on stack")

    # Media — only ask if prompt mentions images/video but not how
    if has_media and not any(
        kw in prompt_lower
        for kw in ("pixabay", "ai image", "ai-generated", "stock image", "svg only")
    ):
        questions.append(_QUESTION_MEDIA)

    # Deployment — only ask for server-side or complex projects
    if not has_deploy and inferred_mode in {
        "full_stack", "dashboard", "admin_panel", "api_service",
        "automation_bot", "trading_bot_scaffold",
    }:
        questions.append(_QUESTION_DEPLOY)
    else:
        assumptions.append("Deployment: Docker Compose + README (default)")

    # Limit to 5 questions max
    questions = questions[:5]

    needs = bool(questions) and is_vague
    return {
        "needs_clarification": needs,
        "questions": questions,
        "inferred_mode": inferred_mode or mode or "web_app",
        "inferred_auth": inferred_auth,
        "inferred_db": inferred_db,
        "assumptions": assumptions,
    }


def apply_clarification_answers(
    original_prompt: str,
    answers: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """Merge user answers with the original prompt to produce an enriched prompt.

    Returns (enriched_prompt, params_dict) where params_dict can be passed
    directly to ProjectCreate / stack_decision.
    """
    parts = [original_prompt.strip()]
    params: dict[str, Any] = {}

    if mode_answer := answers.get("mode"):
        _mode_map = {
            "landing page": "landing_page",
            "multi-page website": "website",
            "react / vite web app": "web_app",
            "pwa (progressive web app)": "pwa",
            "full-stack saas": "full_stack",
            "dashboard / admin panel": "dashboard",
            "api / backend service": "api_service",
            "research brief": "research",
            "import & fix a github repo": "repo_fix",
        }
        params["mode"] = _mode_map.get(mode_answer.lower(), "web_app")
        parts.append(f"Build mode: {mode_answer}.")

    if framework_answer := answers.get("framework"):
        if "auto" not in framework_answer.lower():
            params["stack_preference"] = framework_answer
            parts.append(f"Framework preference: {framework_answer}.")

    if auth_answer := answers.get("auth_required"):
        auth_required = "yes" in auth_answer.lower()
        params["auth_required"] = auth_required
        if auth_required:
            parts.append("Auth required: login, register, JWT, hashed passwords, roles.")

    if db_answer := answers.get("database"):
        if "auto" not in db_answer.lower() and "no database" not in db_answer.lower():
            params["database_preference"] = db_answer
            parts.append(f"Database: {db_answer}.")
        elif "no database" in db_answer.lower():
            params["database_preference"] = "none"

    if media_answer := answers.get("media"):
        params["media_requirements"] = media_answer
        parts.append(f"Media strategy: {media_answer}.")

    if deploy_answer := answers.get("deployment"):
        if "not sure" not in deploy_answer.lower():
            params["deployment_target"] = deploy_answer
            parts.append(f"Deployment: {deploy_answer}.")

    enriched_prompt = " ".join(parts)
    return enriched_prompt, params
