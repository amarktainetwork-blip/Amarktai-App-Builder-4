"""
Amarktai App Builder — Intelligent Build Mode Classifier (Phase 1E).

Classifies user prompts into specific build modes, detects ambiguity, and
returns targeted clarification questions when the intent is unclear.

Modes
-----
landing_page      Single-page marketing/conversion site
multipage_site    Multi-page website (2–10 pages)
pwa               Progressive Web App with offline support
saas_dashboard    SaaS product with authenticated dashboard
api_backend       Pure backend / REST API service
repo_upgrade      GitHub repository improvement
ecommerce         Online store / marketplace
portfolio         Personal or agency portfolio
admin_system      Internal admin panel / back-office
web_app           Generic interactive web application (fallback)

Usage::

    from agents.mode_classifier import classify_build_mode, ModeClassification

    result = classify_build_mode("Build me a portfolio site for a photographer")
    print(result.mode)        # "portfolio"
    print(result.confidence)  # 0.92
    print(result.needs_clarification)  # False
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Mode definitions ──────────────────────────────────────────────────────────

SUPPORTED_MODES = (
    "landing_page",
    "multipage_site",
    "pwa",
    "saas_dashboard",
    "api_backend",
    "repo_upgrade",
    "ecommerce",
    "portfolio",
    "admin_system",
    "ai_chat_rag_app",
    "crm_dashboard",
    "web_app",
)

# ── Signal patterns (keyword → mode, confidence weight) ──────────────────────

_SIGNALS: list[tuple[re.Pattern, str, float]] = [
    # landing page
    (re.compile(r"\blanding\s*page\b", re.I), "landing_page", 0.95),
    (re.compile(r"\bconversion\s+page\b|\bwaitlist\s+page\b|\blead\s+page\b", re.I), "landing_page", 0.90),
    (re.compile(r"\bsingle[- ]page\b|\bone[- ]page\b", re.I), "landing_page", 0.85),
    (re.compile(r"\bproduct\s+launch\b|\blaunch\s+page\b|\bcoming\s+soon\b", re.I), "landing_page", 0.80),

    # multipage site
    (re.compile(r"\bmulti[- ]?page\b|\b\d+[- ]?page\s+(?:site|website|web)\b", re.I), "multipage_site", 0.95),
    (re.compile(r"\bwith\s+(?:about|services?|contact)\s+page", re.I), "multipage_site", 0.80),
    (re.compile(r"\bbusiness\s+(?:site|website)\b|\bcorporate\s+(?:site|website)\b", re.I), "multipage_site", 0.75),

    # pwa
    (re.compile(r"\bprogressive\s+web\s+app\b|\bpwa\b", re.I), "pwa", 0.98),
    (re.compile(r"\boffline\s+(?:support|mode|capable|first)\b", re.I), "pwa", 0.88),
    (re.compile(r"\binstallable\s+(?:app|web)\b|\bservice\s+worker\b", re.I), "pwa", 0.85),

    # saas dashboard
    (re.compile(r"\bsaas\b", re.I), "saas_dashboard", 0.90),
    (re.compile(r"\bdashboard\b.*\b(?:auth|login|users?)\b|\b(?:auth|login)\b.*\bdashboard\b", re.I), "saas_dashboard", 0.88),
    (re.compile(r"\bsubscription\s+(?:app|platform|tool)\b", re.I), "saas_dashboard", 0.82),
    (re.compile(r"\bmulti[- ]?tenant\b|\bworkspace\b.*\busers?\b", re.I), "saas_dashboard", 0.80),

    # api backend
    (re.compile(r"\brest\s*api\b|\bgraphql\s*api\b|\bapi\s+(?:server|service|backend)\b", re.I), "api_backend", 0.95),
    (re.compile(r"\bfastapi\b|\bexpressjs?\b|\bdjango\s+(?:api|rest)\b", re.I), "api_backend", 0.88),
    (re.compile(r"\bno\s+frontend\b|\bbackend\s+only\b|\bheadless\s+api\b", re.I), "api_backend", 0.85),
    (re.compile(r"\bmicroservice\b|\bwebhook\s+(?:server|handler)\b", re.I), "api_backend", 0.82),

    # repo upgrade
    (re.compile(r"\bimprove\s+my\s+(?:repo|code|github)\b|\bfix\s+(?:this|my)\s+(?:repo|code)\b", re.I), "repo_upgrade", 0.90),
    (re.compile(r"\bgithub\.com/\S+|\bgit\s+(?:repo|repository)\b", re.I), "repo_upgrade", 0.85),
    (re.compile(r"\brefactor\b.*\bexisting\b|\bupgrade\b.*\bcodebase\b", re.I), "repo_upgrade", 0.80),

    # ecommerce
    (re.compile(r"\be[- ]?commerce\b|\bonline\s+store\b|\bonline\s+shop\b", re.I), "ecommerce", 0.95),
    (re.compile(r"\bproduct\s+catalog\b|\bshopping\s+cart\b|\bcheckout\b.*\bstore\b", re.I), "ecommerce", 0.88),
    (re.compile(r"\bshopify[- ]?like\b|\bwoocommerce[- ]?like\b|\bmarketplace\b", re.I), "ecommerce", 0.85),
    (re.compile(r"\bsell\s+(?:products?|items?|goods)\b|\bbuying\s+and\s+selling\b", re.I), "ecommerce", 0.80),

    # portfolio
    (re.compile(r"\bportfolio\b", re.I), "portfolio", 0.95),
    (re.compile(r"\bshowcase\s+(?:my|work|projects?)\b|\bmy\s+work\s+(?:page|site)\b", re.I), "portfolio", 0.88),
    (re.compile(r"\bfreelance\s+(?:designer|developer|artist)\b|\bpersonal\s+brand\b", re.I), "portfolio", 0.80),
    (re.compile(r"\bcreative\s+(?:agency|studio)\s+site\b", re.I), "portfolio", 0.75),

    # admin system
    (re.compile(r"\badmin\s+(?:panel|dashboard|portal|system|interface)\b", re.I), "admin_system", 0.95),
    (re.compile(r"\bback[- ]?office\b|\bcms\s+dashboard\b|\bcontent\s+management\b", re.I), "admin_system", 0.85),
    (re.compile(r"\bmanage\s+(?:users?|orders?|inventory|content)\b.*\bdashboard\b", re.I), "admin_system", 0.80),
    (re.compile(r"\binternal\s+tool\b|\bops\s+dashboard\b", re.I), "admin_system", 0.78),

    # ai chat / rag
    (re.compile(r"\b(ai\s+chat|chatbot|assistant)\b.*\b(rag|retrieval|vector|knowledge\s+base)\b", re.I), "ai_chat_rag_app", 0.96),
    (re.compile(r"\brag\b|\bretrieval[- ]augmented\b|\bvector\s+db\b|\bsemantic\s+search\b", re.I), "ai_chat_rag_app", 0.90),
    (re.compile(r"\bllm\s+chat\b|\bchat\s+with\s+docs\b|\bdocument\s+qa\b", re.I), "ai_chat_rag_app", 0.86),

    # crm dashboard
    (re.compile(r"\bcrm\b|\bcustomer\s+relationship\s+management\b", re.I), "crm_dashboard", 0.95),
    (re.compile(r"\b(sales|pipeline|lead|deal)\b.*\bdashboard\b", re.I), "crm_dashboard", 0.88),
    (re.compile(r"\bcontacts?\b.*\b(opportunity|pipeline|account)\b", re.I), "crm_dashboard", 0.84),
]

# Vagueness signals — prompt lacks enough specificity
_VAGUE_PATTERNS = [
    re.compile(r"^(?:build|make|create|generate)\s+(?:a|an|me\s+a|me\s+an)\s+(?:app|site|website|platform|tool|thing)\.?\s*$", re.I),
    re.compile(r"^(?:i\s+want|i\s+need)\s+(?:a|an)\s+(?:app|site|website)\.?\s*$", re.I),
]
_MIN_WORDS_CLEAR = 8  # fewer words usually means vague

# ── Clarification question banks (per mode) ───────────────────────────────────

_CLARIFICATION_QUESTIONS: dict[str, list[str]] = {
    "landing_page": [
        "What is the primary goal of this landing page? (lead capture, product demo, waitlist signup…)",
        "Who is the target audience? (developers, consumers, enterprise…)",
        "Do you need a form or sign-up section on this page?",
    ],
    "multipage_site": [
        "Which pages do you need? (e.g. Home, About, Services, Portfolio, Contact)",
        "Is this for a business, agency, or personal use?",
        "What are the main conversions or goals of the site?",
    ],
    "pwa": [
        "What functionality must work offline?",
        "Is this for mobile, desktop, or both?",
        "Does the app need user authentication?",
    ],
    "saas_dashboard": [
        "What is the core value the SaaS provides to users?",
        "What are the key dashboard metrics or data views?",
        "Does it need a subscription/billing flow?",
    ],
    "api_backend": [
        "What data does the API expose or manage?",
        "What authentication method is required? (JWT, OAuth, API keys…)",
        "Which database should be used? (PostgreSQL, MongoDB, SQLite…)",
    ],
    "repo_upgrade": [
        "Please paste the GitHub URL of the repository.",
        "What specific improvements do you want? (bugs, performance, features, tests…)",
        "Are there any areas of the code you want left unchanged?",
    ],
    "ecommerce": [
        "What types of products will be sold?",
        "Does it need a shopping cart and checkout flow?",
        "Should there be an admin panel for managing products?",
    ],
    "portfolio": [
        "What type of work do you want to showcase? (design, code, photography, writing…)",
        "Do you need a contact form or inquiry section?",
        "Should the portfolio include a blog or case studies?",
    ],
    "admin_system": [
        "What entities will administrators manage? (users, orders, content…)",
        "Does it need role-based access control?",
        "What data visualisations or charts are needed?",
    ],
    "ai_chat_rag_app": [
        "What knowledge sources should the assistant use? (docs, website pages, PDFs, DB records)",
        "Do you need ingestion/indexing workflows and where should embeddings be stored?",
        "What guardrails are required? (auth, moderation, citation requirements)",
    ],
    "crm_dashboard": [
        "Which CRM entities are required? (leads, contacts, accounts, deals, activities)",
        "What sales stages and pipeline views should be included?",
        "Do you need role-based views for sales reps, managers, and admins?",
    ],
    "web_app": [
        "What is the main function of this app?",
        "Does it require user accounts / authentication?",
        "Is there a backend or database component?",
    ],
}

_GENERIC_QUESTIONS = [
    "Can you describe what this app or site should do in one or two sentences?",
    "Who is the primary user of this product?",
    "What is the most important action a visitor should take?",
]

# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class ModeClassification:
    """Result of build mode classification."""

    mode: str
    confidence: float
    needs_clarification: bool
    clarification_questions: list[str] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)
    inferred_mode: bool = False  # True if mode was inferred rather than explicit
    override_allowed: bool = True

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_questions": self.clarification_questions,
            "matched_signals": self.matched_signals,
            "inferred_mode": self.inferred_mode,
            "override_allowed": self.override_allowed,
        }


# ── Classifier ────────────────────────────────────────────────────────────────


def classify_build_mode(
    prompt: str,
    forced_mode: str | None = None,
) -> ModeClassification:
    """Classify the build mode from a user prompt.

    Parameters
    ----------
    prompt:
        The user's build prompt.
    forced_mode:
        If set, skip signal matching and return this mode at max confidence.
        Still checks for vagueness to decide whether clarification is needed.

    Returns
    -------
    ModeClassification
    """
    if forced_mode:
        mode = _normalise_mode(forced_mode) or forced_mode
        is_vague = _is_vague(prompt)
        return ModeClassification(
            mode=mode,
            confidence=1.0,
            needs_clarification=is_vague,
            clarification_questions=_clarification_for(mode, is_vague),
            matched_signals=["forced_override"],
            inferred_mode=False,
        )

    # Score all modes
    scores: dict[str, float] = {m: 0.0 for m in SUPPORTED_MODES}
    matched: dict[str, list[str]] = {m: [] for m in SUPPORTED_MODES}

    for pattern, mode, weight in _SIGNALS:
        m = pattern.search(prompt)
        if m:
            scores[mode] = max(scores[mode], weight)
            matched[mode].append(m.group(0))

    best_mode = max(scores, key=lambda k: scores[k])
    best_score = scores[best_mode]
    is_vague = _is_vague(prompt)

    if best_score < 0.50:
        # No strong signal found — fall back to web_app with low confidence
        return ModeClassification(
            mode="web_app",
            confidence=0.35,
            needs_clarification=True,
            clarification_questions=_clarification_for("web_app", True),
            matched_signals=[],
            inferred_mode=True,
        )

    needs_clarification = is_vague or best_score < 0.70

    return ModeClassification(
        mode=best_mode,
        confidence=round(best_score, 2),
        needs_clarification=needs_clarification,
        clarification_questions=_clarification_for(best_mode, needs_clarification),
        matched_signals=matched[best_mode],
        inferred_mode=(best_score < 0.85),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_vague(prompt: str) -> bool:
    """Return True if the prompt is too short or matches vague patterns."""
    words = prompt.strip().split()
    if len(words) < _MIN_WORDS_CLEAR:
        return True
    for pat in _VAGUE_PATTERNS:
        if pat.match(prompt.strip()):
            return True
    return False


def _normalise_mode(mode: str) -> str:
    """Map legacy / variant mode strings to canonical SUPPORTED_MODES names."""
    mapping: dict[str, str] = {
        "landing-page": "landing_page",
        "website": "multipage_site",
        "multi_page_website": "multipage_site",
        "multi-page-website": "multipage_site",
        "multi_page_site": "multipage_site",
        "saas": "saas_dashboard",
        "dashboard": "saas_dashboard",
        "admin_panel": "admin_system",
        "admin-panel": "admin_system",
        "api_service": "api_backend",
        "api-service": "api_backend",
        "api-backend": "api_backend",
        "repo_fix": "repo_upgrade",
        "repo-upgrade": "repo_upgrade",
        "repo-fix": "repo_upgrade",
        "ai_chat_rag_app": "ai_chat_rag_app",
        "ai-chat-rag-app": "ai_chat_rag_app",
        "ai_chat_rag": "ai_chat_rag_app",
        "ai-chat-rag": "ai_chat_rag_app",
        "crm_dashboard": "crm_dashboard",
        "crm-dashboard": "crm_dashboard",
        "crm/dashboard": "crm_dashboard",
        "full_stack": "saas_dashboard",
        "fullstack-saas": "saas_dashboard",
        "web_app": "web_app",
        "web-app": "web_app",
        "react-app": "web_app",
        "next-app": "web_app",
    }
    key = (mode or "").lower().strip()
    if key in SUPPORTED_MODES:
        return key
    return mapping.get(key, "web_app")


def _clarification_for(mode: str, needs: bool) -> list[str]:
    """Return at most 3 targeted questions for the given mode (only when needed)."""
    if not needs:
        return []
    bank = _CLARIFICATION_QUESTIONS.get(mode, _GENERIC_QUESTIONS)
    return bank[:3]


def normalise_mode_for_orchestrator(mode: str) -> str:
    """Convert classifier output mode to the orchestrator's internal mode name.

    The orchestrator uses a slightly different naming convention inherited from
    the original build_contract.  This bridge function keeps both layers in sync
    without breaking existing code.
    """
    bridge: dict[str, str] = {
        "landing_page": "landing_page",
        "multipage_site": "website",
        "pwa": "pwa",
        "saas_dashboard": "full_stack",
        "api_backend": "api_service",
        "repo_upgrade": "repo_fix",
        "ecommerce": "landing_page",    # closest supported mode
        "portfolio": "landing_page",    # closest supported mode
        "admin_system": "dashboard",
        "ai_chat_rag_app": "ai_chat_rag_app",
        "crm_dashboard": "crm_dashboard",
        "web_app": "web_app",
    }
    return bridge.get(mode, "web_app")
