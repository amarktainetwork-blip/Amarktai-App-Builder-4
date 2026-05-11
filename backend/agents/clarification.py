"""
Clarification engine for Amarktai App Builder.

Detects when a user prompt is too vague for reliable generation and returns
focused questions to ask before starting the build pipeline.

Rules:
- Ask at most 5 focused questions.
- If enough info exists, do NOT ask unnecessary questions.
- Proceed with sensible defaults when assumptions are safe.
- Questions are build-type-specific (landing page / website / PWA / SaaS / repo).
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
    r"\b(login|logout|register|sign[-\s]?up|sign[-\s]?in|auth|password|user\s+account|user\s+management|role|admin\s+access)\b",
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
    r"\b(image|photo|video|music|audio|media|gallery|background|hero|pixabay|logo)\b",
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


# ── Generic question bank ─────────────────────────────────────────────────────

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
        "Use my uploaded logo/media",
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


# ── Build-type specific question sets ────────────────────────────────────────

_LANDING_PAGE_QUESTIONS: list[dict] = [
    {
        "id": "business_name",
        "question": "What is the business or product name?",
        "type": "text",
        "required": True,
    },
    {
        "id": "audience",
        "question": "Who is the primary audience?",
        "type": "text",
        "required": False,
    },
    {
        "id": "cta",
        "question": "What is the main call-to-action (CTA)?",
        "options": [
            "Sign up / Get started",
            "Buy now / Shop",
            "Contact us",
            "Download / Get the app",
            "Learn more",
            "Book a demo",
        ],
        "required": False,
    },
    {
        "id": "media",
        "question": "Logo and media preference?",
        "options": [
            "Use my uploaded logo and media",
            "Generate SVG logo (no upload)",
            "Pixabay stock images",
            "SVG / CSS only — no external images",
            "Use recommended defaults",
        ],
        "required": False,
    },
    {
        "id": "style",
        "question": "Desired visual style?",
        "options": [
            "Modern / Clean / Minimal",
            "Bold / Colorful / Eye-catching",
            "Dark / Cinematic",
            "Luxury / Editorial / Premium",
            "Tech / Developer-focused",
            "Auto-select best fit",
        ],
        "required": False,
    },
]

_WEBSITE_QUESTIONS: list[dict] = [
    {
        "id": "pages",
        "question": "Which pages should the site include?",
        "options": [
            "Home, About, Services, Contact (4 pages)",
            "Home, About, Portfolio, Blog, Contact (5 pages)",
            "Home, Services, Pricing, About, FAQ, Contact (6 pages)",
            "Home, About, Services/Products, Contact (minimal)",
            "Use recommended defaults",
        ],
        "required": False,
    },
    {
        "id": "nav_style",
        "question": "Navigation style?",
        "options": [
            "Top navigation bar",
            "Side navigation (sidebar)",
            "Full-screen hamburger menu (mobile-first)",
            "Auto-select best fit",
        ],
        "required": False,
    },
    {
        "id": "content_tone",
        "question": "Content tone?",
        "options": [
            "Professional / Corporate",
            "Friendly / Casual",
            "Creative / Expressive",
            "Technical / Data-driven",
        ],
        "required": False,
    },
    {
        "id": "media",
        "question": "Logo and media preference?",
        "options": [
            "Use my uploaded logo and media",
            "Generate SVG logo (no upload)",
            "Pixabay stock images",
            "SVG / CSS only",
            "Use recommended defaults",
        ],
        "required": False,
    },
    {
        "id": "contact_method",
        "question": "Contact method?",
        "options": [
            "Contact form",
            "Email address only",
            "WhatsApp / social links",
            "No contact section",
        ],
        "required": False,
    },
]

_PWA_QUESTIONS: list[dict] = [
    {
        "id": "core_workflow",
        "question": "What is the core user workflow? (1 sentence)",
        "type": "text",
        "required": True,
    },
    {
        "id": "offline",
        "question": "Does the app need offline support?",
        "options": [
            "Yes — full offline with service worker cache",
            "Yes — basic offline fallback page",
            "No — online only",
        ],
        "required": True,
    },
    {
        "id": "storage",
        "question": "Local data storage?",
        "options": [
            "localStorage (simple key-value)",
            "IndexedDB (structured data)",
            "No local storage needed",
        ],
        "required": False,
    },
    {
        "id": "logo_icon",
        "question": "App icon / logo?",
        "options": [
            "Use my uploaded logo",
            "Generate SVG icon",
            "Use default placeholder",
        ],
        "required": False,
    },
    {
        "id": "auth_required",
        "question": "Does the PWA need user authentication?",
        "options": ["Yes — login required", "No auth needed"],
        "required": True,
    },
]

_SAAS_FULLSTACK_QUESTIONS: list[dict] = [
    {
        "id": "user_roles",
        "question": "What user roles are needed?",
        "options": [
            "Single role (all users equal)",
            "Admin + regular user",
            "Admin + multiple custom roles",
            "No users / single-user app",
        ],
        "required": True,
    },
    {
        "id": "auth_required",
        "question": "Authentication method?",
        "options": [
            "Email + password (JWT)",
            "Email + password + social login",
            "API key only (no user auth)",
            "No auth",
        ],
        "required": True,
    },
    {
        "id": "database",
        "question": "Preferred database?",
        "options": [
            "MongoDB (flexible, recommended for SaaS)",
            "PostgreSQL (relational)",
            "MySQL / MariaDB",
            "SQLite (lightweight)",
            "Auto-select best fit",
        ],
        "required": False,
    },
    {
        "id": "deployment",
        "question": "Deployment target?",
        "options": [
            "Docker Compose + VPS (recommended)",
            "Kubernetes / cloud-native",
            "Static frontend + serverless backend",
            "Not sure yet",
        ],
        "required": False,
    },
    {
        "id": "api_integrations",
        "question": "Any API integrations or external services?",
        "options": [
            "Stripe / payment",
            "Email service (SMTP / SendGrid)",
            "Third-party OAuth",
            "None for now",
        ],
        "required": False,
    },
]

_REPO_FIX_QUESTIONS: list[dict] = [
    {
        "id": "preserve_design",
        "question": "Should the existing design be preserved or redesigned?",
        "options": [
            "Preserve existing design and styles",
            "Redesign from scratch with new design system",
            "Keep structure, improve styling only",
            "Auto-decide based on quality assessment",
        ],
        "required": True,
    },
    {
        "id": "scope",
        "question": "What is the scope of changes?",
        "options": [
            "Complete the unfinished app (all features)",
            "Fix specific bugs or issues only",
            "Add missing features to working app",
            "Full modernization / refactor",
        ],
        "required": True,
    },
    {
        "id": "preview_cmd",
        "question": "What command runs the app locally? (e.g. npm run dev)",
        "type": "text",
        "required": False,
    },
    {
        "id": "pr_target",
        "question": "Should changes be submitted as a GitHub Pull Request?",
        "options": [
            "Yes — open a PR against the default branch",
            "Yes — open a PR against a specific branch",
            "No — just generate the files",
        ],
        "required": False,
    },
]

# Map mode → specific question set
_MODE_QUESTION_SETS: dict[str, list[dict]] = {
    "landing_page": _LANDING_PAGE_QUESTIONS,
    "website": _WEBSITE_QUESTIONS,
    "pwa": _PWA_QUESTIONS,
    "full_stack": _SAAS_FULLSTACK_QUESTIONS,
    "dashboard": _SAAS_FULLSTACK_QUESTIONS,
    "admin_panel": _SAAS_FULLSTACK_QUESTIONS,
    "repo_fix": _REPO_FIX_QUESTIONS,
}


def get_questions_for_mode(mode: str) -> list[dict]:
    """Return the build-type-specific question set for a mode."""
    return _MODE_QUESTION_SETS.get(mode, [])


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
    inferred_mode = _implied_mode(prompt_lower) or mode
    inferred_auth = bool(_AUTH_KEYWORDS.search(prompt))
    inferred_db = bool(_DB_KEYWORDS.search(prompt))
    has_framework = bool(_FRAMEWORK_KEYWORDS.search(prompt))
    has_media = bool(_MEDIA_KEYWORDS.search(prompt))
    has_deploy = bool(_DEPLOY_KEYWORDS.search(prompt))

    questions: list[dict] = []
    assumptions: list[str] = []

    # Determine if clarification is needed
    is_vague = _is_vague(prompt)

    # If mode is known, use build-type-specific questions
    if inferred_mode and inferred_mode in _MODE_QUESTION_SETS:
        mode_questions = list(_MODE_QUESTION_SETS[inferred_mode])
        if is_vague:
            # Use the specific question set (limited to 5)
            questions = mode_questions[:5]
        else:
            # Only ask required questions for clear prompts
            required_qs = [q for q in mode_questions if q.get("required") and not _answer_in_prompt(q["id"], prompt_lower)]
            questions = required_qs[:5]
        # Record assumptions for optional items skipped
        skipped_ids = {q["id"] for q in mode_questions} - {q["id"] for q in questions}
        if skipped_ids:
            assumptions.append(f"Using recommended defaults for: {', '.join(sorted(skipped_ids))}")
    else:
        # Generic question flow for unknown/web_app mode
        if not inferred_mode and is_vague:
            questions.append(_QUESTION_MODE)

        if not has_framework and (is_vague or not inferred_mode):
            questions.append(_QUESTION_FRAMEWORK)
        else:
            assumptions.append("Framework: auto-selected based on project type")

        if not inferred_auth and (is_vague or inferred_mode in {"full_stack", "dashboard", "admin_panel"}):
            questions.append(_QUESTION_AUTH)
        elif inferred_auth:
            assumptions.append("Auth: JWT + hashed passwords (requested in prompt)")
        else:
            assumptions.append("Auth: none (not requested)")

        if not inferred_db and inferred_mode in {
            "full_stack", "dashboard", "admin_panel", "api_service", "web_app",
        }:
            questions.append(_QUESTION_DB)
        else:
            assumptions.append("Database: auto-selected based on stack")

        if has_media and not any(
            kw in prompt_lower
            for kw in ("pixabay", "ai image", "ai-generated", "stock image", "svg only", "uploaded")
        ):
            questions.append(_QUESTION_MEDIA)

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
        "inferred_mode": inferred_mode or "web_app",
        "inferred_auth": inferred_auth,
        "inferred_db": inferred_db,
        "assumptions": assumptions,
        "can_skip": True,  # Always offer "use recommended defaults"
    }


def _answer_in_prompt(question_id: str, prompt_lower: str) -> bool:
    """Check if a question is already effectively answered in the prompt."""
    _ANSWER_SIGNALS = {
        "business_name": r"\b(for|called|named|brand)\b",
        "auth_required": r"\b(login|auth|sign[- ]up|register)\b",
        "database": r"\b(mongo|postgres|mysql|sqlite|database)\b",
        "deployment": r"\b(docker|vercel|netlify|vps|heroku)\b",
        "media": r"\b(pixabay|svg only|no images|uploaded logo|my logo)\b",
        "preserve_design": r"\b(redesign|preserve|keep design|new design)\b",
        "scope": r"\b(fix|complete|add|refactor|modernize)\b",
    }
    pattern = _ANSWER_SIGNALS.get(question_id)
    if not pattern:
        return False
    return bool(re.search(pattern, prompt_lower, re.IGNORECASE))


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

    if business_name := answers.get("business_name"):
        parts.append(f"Business name: {business_name}.")

    if audience := answers.get("audience"):
        parts.append(f"Target audience: {audience}.")

    if cta := answers.get("cta"):
        parts.append(f"Primary CTA: {cta}.")

    if style := answers.get("style"):
        if "auto" not in style.lower():
            params["style_preference"] = style
            parts.append(f"Visual style: {style}.")

    if pages := answers.get("pages"):
        if "defaults" not in pages.lower():
            parts.append(f"Page structure: {pages}.")

    if nav_style := answers.get("nav_style"):
        if "auto" not in nav_style.lower():
            parts.append(f"Navigation: {nav_style}.")

    if content_tone := answers.get("content_tone"):
        parts.append(f"Content tone: {content_tone}.")

    if contact_method := answers.get("contact_method"):
        parts.append(f"Contact method: {contact_method}.")

    if core_workflow := answers.get("core_workflow"):
        parts.append(f"Core workflow: {core_workflow}.")

    if offline := answers.get("offline"):
        parts.append(f"Offline support: {offline}.")

    if storage := answers.get("storage"):
        if "no" not in storage.lower():
            parts.append(f"Local storage: {storage}.")

    if logo_icon := answers.get("logo_icon"):
        if "uploaded" in logo_icon.lower():
            params["media_source"] = "uploaded"
        parts.append(f"Logo preference: {logo_icon}.")

    if user_roles := answers.get("user_roles"):
        parts.append(f"User roles: {user_roles}.")

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
        if "uploaded" in media_answer.lower():
            params["media_source"] = "uploaded"
        parts.append(f"Media strategy: {media_answer}.")

    if deploy_answer := answers.get("deployment"):
        if "not sure" not in deploy_answer.lower():
            params["deployment_target"] = deploy_answer
            parts.append(f"Deployment: {deploy_answer}.")

    if preserve_design := answers.get("preserve_design"):
        parts.append(f"Design approach: {preserve_design}.")

    if scope := answers.get("scope"):
        parts.append(f"Scope: {scope}.")

    if preview_cmd := answers.get("preview_cmd"):
        parts.append(f"Preview command: {preview_cmd}.")

    if pr_target := answers.get("pr_target"):
        parts.append(f"PR target: {pr_target}.")

    if api_integrations := answers.get("api_integrations"):
        if "none" not in api_integrations.lower():
            parts.append(f"API integrations: {api_integrations}.")

    enriched_prompt = " ".join(parts)
    return enriched_prompt, params


