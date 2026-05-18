"""Build contract, deterministic file policy, manifest, and validation.

This module is intentionally model-free. It is the source of truth for what a
generated Amarktai project must contain before the pipeline can mark it ready.
"""
from __future__ import annotations

import json
import re
from html import escape
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from .quality_validator import score_project_quality
from .template_policy import is_automotive_prompt, remove_legacy_template_contamination
from app.services.tier_service import PUBLIC_TIERS, normalize_quality_tier


def safe_dict(value: Any) -> dict:
    """Return *value* if it is already a dict, otherwise return an empty dict.

    Prevents ``AttributeError: 'NoneType' object has no attribute 'get'`` when
    project sub-documents (selected_stack, media, deployment, etc.) are stored
    as ``None`` rather than as a missing key.
    """
    return value if isinstance(value, dict) else {}

PROJECT_STATUSES = (
    "queued", "classifying", "planning", "generating", "reviewing",
    "validating", "repairing", "preview_preparing", "ready",
    "failed_validation", "failed_generation", "failed_repair",
    "failed_preview", "cancelled", "finalized",
)

PROJECT_TYPES = (
    "static-site", "multi-page-site", "react-app", "next-app", "pwa",
    "fullstack-app", "api-service", "dashboard", "repo-upgrade",
    "automation-bot-scaffold", "trading-bot-scaffold",
    "ecommerce-scaffold", "booking-portal", "ai-chat-rag-app",
)

BUILD_MODES = (
    "landing-page", "multi-page-website", "pwa", "fullstack-saas",
    "dashboard", "api-service", "repo-upgrade", "automation-bot",
    "trading-bot-scaffold", "ecommerce-scaffold", "booking-portal",
    "ai-chat-rag-app", "crm-dashboard", "custom",
)

QUALITY_TIERS = PUBLIC_TIERS

MODE_PROJECT_TYPE = {
    "landing_page": ("static-site", "landing-page"),
    "landing-page": ("static-site", "landing-page"),
    "website": ("multi-page-site", "multi-page-website"),
    "multi-page-website": ("multi-page-site", "multi-page-website"),
    "media_page": ("static-site", "landing-page"),
    "web_app": ("react-app", "custom"),
    "react-app": ("react-app", "custom"),
    "next-app": ("next-app", "custom"),
    "pwa": ("pwa", "pwa"),
    "full_stack": ("fullstack-app", "fullstack-saas"),
    "fullstack-saas": ("fullstack-app", "fullstack-saas"),
    "dashboard": ("dashboard", "dashboard"),
    "admin_panel": ("dashboard", "dashboard"),
    "ecommerce_scaffold": ("ecommerce-scaffold", "ecommerce-scaffold"),
    "booking_portal": ("booking-portal", "booking-portal"),
    "ai_chat_rag_app": ("ai-chat-rag-app", "ai-chat-rag-app"),
    "ai_chat_rag": ("ai-chat-rag-app", "ai-chat-rag-app"),
    "ai-chat-rag": ("ai-chat-rag-app", "ai-chat-rag-app"),
    "crm_dashboard": ("dashboard", "crm-dashboard"),
    "crm/dashboard": ("dashboard", "crm-dashboard"),
    "crm": ("dashboard", "crm-dashboard"),
    "api_service": ("api-service", "api-service"),
    "api-service": ("api-service", "api-service"),
    "repo_fix": ("repo-upgrade", "repo-upgrade"),
    "repo-upgrade": ("repo-upgrade", "repo-upgrade"),
    "automation_bot": ("automation-bot-scaffold", "automation-bot"),
    "automation-bot": ("automation-bot-scaffold", "automation-bot"),
    "trading_bot_scaffold": ("trading-bot-scaffold", "trading-bot-scaffold"),
    "trading-bot-scaffold": ("trading-bot-scaffold", "trading-bot-scaffold"),
}

STATIC_FORBIDDEN_FILES = {
    "package.json",
    "src/main.jsx",
    "src/main.js",
    "src/App.jsx",
    "src/App.js",
    "src/App.css",
    "src/index.jsx",
    "src/index.js",
}

REPORT_AND_METADATA_FILES = {
    "requirements.md",
    "tech_stack.json",
    "quality_report.md",
    "quality-report.json",
    "quality_report.json",
    "content_quality_report.json",
    "runtime_qa_report.json",
    "repo_workflow_report.json",
    "audit_report.json",
    "deploy_report.json",
    "repair_plan.json",
    "avatar_manifest.json",
    "voice_avatar_manifest.json",
    "media_manifest.json",
    "motion_manifest.json",
    "preview-manifest.json",
    "amarktai.project.json",
}


def is_report_or_metadata_file(path: str | None) -> bool:
    """Return true for internal artifacts that are not generated app source.

    These files may be persisted for evidence and final gates, but they should
    never be included in agent app-file payloads or counted as required source
    files for a generated application.
    """
    rel = (path or "").replace("\\", "/").strip().lstrip("./")
    name = rel.rsplit("/", 1)[-1]
    return (
        rel in REPORT_AND_METADATA_FILES
        or name in REPORT_AND_METADATA_FILES
        or rel.startswith("runtime-qa/")
        or rel.startswith(".amarktai/")
        or name.endswith("_report.json")
        or name.endswith("-report.json")
        or name.endswith("_manifest.json")
        or name.endswith("-manifest.json")
    )


def filter_app_source_files(files: list[dict]) -> list[dict]:
    return [
        item for item in (files or [])
        if isinstance(item, dict)
        and item.get("path")
        and not is_report_or_metadata_file(str(item.get("path")))
    ]

_HTML_CLOSE_RE = re.compile(r"</html\s*>", re.IGNORECASE)
_SECTION_RE = re.compile(r"<section\b", re.IGNORECASE)
_CSS_SELECTOR_RE = re.compile(r"(^|\})\s*[.#]?[A-Za-z][^{]{0,80}\{", re.MULTILINE)
_STATIC_SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*(?!change_me|example|your_|localhost)[A-Za-z0-9_\-]{16,}")
_BAKERY_HINTS = re.compile(r"\b(bakery|baker|bread|sourdough|pastr(?:y|ies)|cafe|coffee|catering)\b", re.IGNORECASE)
_PLATFORM_HINTS = re.compile(r"\b(amarktai|app builder|software factory|repo|runtime qa|provider|github|agent orchestration)\b", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_generated_path(path: str) -> str:
    if not path or "\x00" in path:
        raise ValueError("Invalid file path")
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Path traversal is not allowed")
    cleaned = str(candidate)
    if cleaned in ("", "."):
        raise ValueError("Invalid file path")
    return cleaned


def normalize_mode(mode: str | None) -> str:
    value = (mode or "web_app").strip().lower()
    if value in MODE_PROJECT_TYPE:
        return value
    if value in ("multi_page_website", "multi-page-site"):
        return "website"
    if value == "fullstack_app":
        return "full_stack"
    if value in ("ai chat rag", "ai chat/rag", "ai-chat-rag-app", "rag-chat"):
        return "ai_chat_rag_app"
    if value in ("crm-dashboard", "crm dashboard", "crm/dashboard"):
        return "crm_dashboard"
    return "web_app"


def infer_project_type(mode: str | None, project_type: str | None = None) -> str:
    if project_type in PROJECT_TYPES:
        return project_type
    return MODE_PROJECT_TYPE.get(normalize_mode(mode), ("react-app", "custom"))[0]


def infer_build_mode(mode: str | None) -> str:
    return MODE_PROJECT_TYPE.get(normalize_mode(mode), ("react-app", "custom"))[1]


def get_required_files(project_type: str, build_mode: str | None = None,
                       prompt: str = "", plan: dict | None = None) -> list[str]:
    project_type = project_type if project_type in PROJECT_TYPES else "react-app"
    prompt_lower = (prompt or "").lower()
    if project_type == "static-site":
        return ["index.html", "styles.css", "script.js", "README.md", "amarktai.project.json", "preview-manifest.json"]
    if project_type == "multi-page-site":
        files = ["index.html", "styles.css", "script.js", "README.md", "amarktai.project.json", "preview-manifest.json"]
        # Extract numeric page count from prompt
        import re as _re
        _page_count_pat = _re.compile(
            r"\b((?:\d+|two|three|four|five|six|seven|eight|nine|ten))\s*[-–]?\s*page",
            _re.IGNORECASE,
        )
        _word_to_num = {
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        requested_count = 0
        m = _page_count_pat.search(prompt_lower)
        if m:
            raw = m.group(1).lower().strip()
            requested_count = int(raw) if raw.isdigit() else _word_to_num.get(raw, 0)

        # Domain-specific page sets
        domain_pages: list[str] = []
        is_automotive = is_automotive_prompt(prompt, plan=plan)
        if is_automotive:
            domain_pages = ["inventory.html", "vehicle-detail.html", "about.html",
                            "finance.html", "contact.html"]
        else:
            # Standard keyword-based pages
            if any(x in prompt_lower for x in ("5-page", "five page", "multi-page",
                                                "pricing", "contact", "about", "services")):
                domain_pages = ["about.html", "services.html", "pricing.html", "contact.html"]
            elif any(x in prompt_lower for x in ("about",)):
                domain_pages = ["about.html"]
            # Collect individual keyword pages not covered by the above
            keyword_pages = {
                "about": "about.html",
                "service": "services.html",
                "pric": "pricing.html",
                "contact": "contact.html",
                "team": "team.html",
                "blog": "blog.html",
                "portfolio": "portfolio.html",
                "faq": "faq.html",
            }
            for keyword, page_file in keyword_pages.items():
                if keyword in prompt_lower and page_file not in domain_pages:
                    domain_pages.append(page_file)

        # When N pages are explicitly requested, ensure we require enough page files
        for page in domain_pages:
            if page not in files:
                files.append(page)

        # If explicit count requires MORE pages than we've accumulated, note it in README
        # (we can't auto-generate unknown page names, but we enforce the known ones)
        return files
    if project_type == "react-app":
        return ["package.json", "index.html", "src/main.jsx", "src/App.jsx", "src/App.css", "styles.css", "README.md", "amarktai.project.json", ".env.example", "preview-manifest.json"]
    if project_type == "pwa":
        return ["package.json", "index.html", "src/main.jsx", "src/App.jsx", "src/App.css", "styles.css", "README.md", "amarktai.project.json", ".env.example", "manifest.json", "service-worker.js", "preview-manifest.json"]
    if project_type == "next-app":
        return ["package.json", "README.md", "amarktai.project.json", ".env.example", "app/page.jsx"]
    if project_type == "fullstack-app":
        return ["README.md", "amarktai.project.json", ".env.example", "docker-compose.yml", "backend/main.py", "backend/requirements.txt", "frontend/package.json", "frontend/src/App.jsx", "frontend/index.html"]
    if project_type == "api-service":
        return ["README.md", "amarktai.project.json", ".env.example", "backend/main.py", "backend/requirements.txt", "Dockerfile"]
    if project_type == "dashboard":
        return ["README.md", "amarktai.project.json", ".env.example", "package.json", "index.html", "src/main.jsx", "src/App.jsx"]
    if project_type == "repo-upgrade":
        return ["README.md", "amarktai.project.json"]
    if project_type == "ai-chat-rag-app":
        return [
            "README.md",
            "amarktai.project.json",
            ".env.example",
            "package.json",
            "index.html",
            "src/main.jsx",
            "src/App.jsx",
            "src/App.css",
            "backend/main.py",
            "backend/requirements.txt",
        ]
    if project_type == "automation-bot-scaffold":
        return ["README.md", "amarktai.project.json", ".env.example", "bot/main.py", "bot/config.example.json", "Dockerfile"]
    if project_type == "trading-bot-scaffold":
        return ["README.md", "amarktai.project.json", ".env.example", "bot/main.py", "bot/risk_controls.py", "Dockerfile"]
    return ["README.md", "amarktai.project.json"]


def language_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else path.lower()
    return {
        "html": "html", "css": "css", "js": "javascript", "jsx": "javascript",
        "ts": "typescript", "tsx": "typescript", "json": "json", "md": "markdown",
        "py": "python", "yml": "yaml", "yaml": "yaml", "dockerfile": "dockerfile",
    }.get(ext, "text")


def _file(path: str, content: str) -> dict:
    return {"path": path, "language": language_for(path), "content": content}


def _html_classes(html: str) -> set[str]:
    groups = re.findall(r'class=["\']([^"\']+)["\']', html or "")
    return {part for group in groups for part in group.split() if re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", part)}


def _html_ids(html: str) -> set[str]:
    return set(re.findall(r'id=["\']([^"\']+)["\']', html or ""))


def _selector_exists(selector: str, html: str) -> bool:
    if selector.startswith("#"):
        return selector[1:] in _html_ids(html)
    if selector.startswith("."):
        return selector[1:] in _html_classes(html)
    if selector.startswith("[") and selector.endswith("]"):
        attr = selector.strip("[]").split("=", 1)[0]
        return attr in html
    tag_attr = re.match(r"^([a-zA-Z][a-zA-Z0-9-]*)\[", selector)
    if tag_attr:
        return bool(re.search(rf"<{re.escape(tag_attr.group(1))}[\s>]", html, re.IGNORECASE))
    return bool(re.search(rf"<{re.escape(selector)}[\s>]", html, re.IGNORECASE))


def _project_name(prompt: str, fallback: str = "Amarktai Project") -> str:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", prompt or "").strip().split()
    if not words:
        return fallback
    return " ".join(words[:6]).title()


def _static_index(prompt: str, multi: bool = False) -> str:
    title = escape(_project_name(prompt, "Amarktai"))
    nav = "<a href=\"about.html\">About</a><a href=\"services.html\">Services</a><a href=\"pricing.html\">Pricing</a><a href=\"contact.html\">Contact</a>" if multi else "<a href=\"#features\">Features</a><a href=\"#workflow\">Workflow</a><a href=\"#deploy\">Deploy</a>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#08090c">
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="index.html">Amarktai</a>
    <nav aria-label="Primary">{nav}</nav>
  </header>
  <main>
    <section class="hero">
      <div>
        <p class="eyebrow">Amarktai Network</p>
        <h1>{title}</h1>
        <p class="lede">A modern professional web presence with clear messaging, polished visuals, and simple deployment.</p>
        <a class="button" href="#deploy">Plan deployment</a>
      </div>
      <div class="visual" role="img" aria-label="Abstract product preview with layered interface cards"></div>
    </section>
    <section id="features" class="grid">
      <article><h2>Fast Launch</h2><p>Clean sections, responsive layout, and accessible calls to action.</p></article>
      <article><h2>Professional Trust</h2><p>Structured content for services, proof points, and conversion.</p></article>
      <article><h2>Easy Updates</h2><p>Plain HTML and CSS files that are simple to edit and push to GitHub.</p></article>
    </section>
    <section id="workflow" class="band"><h2>From idea to launch</h2><p>Preview the site, request changes, then finalize to GitHub when validation passes.</p></section>
    <section id="deploy" class="deploy"><h2>Deployment</h2><p>Deploy these static files on any static host, VPS, CDN, or GitHub Pages.</p></section>
  </main>
  <footer>Built with Amarktai App Builder.</footer>
</body>
</html>
"""


def _premium_static_index(prompt: str) -> str:
    title = escape(_project_name(prompt, "Amarktai Builder"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#05070b">
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body data-motion-runtime="pending">
  <header class="site-header">
    <a class="brand" href="#hero">Amarktai Builder</a>
    <nav aria-label="Primary">
      <a href="#media-showcase">Media</a>
      <a href="#sales-agent">Sales Agent</a>
      <a href="#repo-workbench">Repo Workbench</a>
      <a href="#runtime-qa">Runtime QA</a>
      <a href="#lead-capture">Access</a>
    </nav>
  </header>
  <main>
    <section id="hero" class="hero" data-amarktai-motion-scene>
      <div class="hero-copy">
        <p class="eyebrow">Production AI software factory</p>
        <h1>{title}</h1>
        <p class="lede">Amarktai Builder helps founders, agencies, product teams, startups, and businesses create, repair, continue, preview, validate, deploy, and improve premium software from one truthful AI dashboard.</p>
        <div class="actions">
          <a class="button primary" href="#lead-capture">Request production access</a>
          <a class="button secondary" href="#repo-workbench">Inspect repo workflow</a>
        </div>
      </div>
      <div class="hero-preview" aria-label="Animated product preview">
        <span class="preview-card preview-card-one"></span>
        <span class="preview-card preview-card-two"></span>
        <span class="preview-card preview-card-three"></span>
      </div>
    </section>

    <section id="media-showcase" class="story-section split" data-amarktai-motion-scene>
      <div>
        <p class="eyebrow">AI image, video, and voice showcase</p>
        <h2>Provider-backed media becomes local build evidence.</h2>
        <p>Amarktai plans image, video, voice, and avatar slots from the brief, calls connected providers when available, persists accepted assets, writes a media manifest, and only treats downloaded files as launch evidence.</p>
      </div>
      <div class="evidence-panel">
        <b>Media manifest</b>
        <span>provider, model, job id, MIME, size, and local path</span>
      </div>
    </section>

    <section id="sales-agent" class="story-section" data-amarktai-motion-scene>
      <p class="eyebrow">AI sales-agent conversation demo</p>
      <h2>A guided conversation turns interest into a precise build brief.</h2>
      <div class="conversation" aria-label="AI sales-agent conversation">
        <p><strong>Founder:</strong> I need a premium web app that imports repos, repairs bugs, and creates pull requests.</p>
        <p><strong>Amarktai:</strong> I will route that as a repo workflow with planner, architect, repo engineer, reviewer, command runner, runtime QA, and GitHub PR evidence.</p>
        <p><strong>Founder:</strong> Make it cinematic and public-ready.</p>
        <p><strong>Amarktai:</strong> Premium mode requires local media assets, motion evidence, browser QA artifacts, content quality, and final gates before release.</p>
      </div>
    </section>

    <section id="repo-workbench" class="story-section cards" data-amarktai-motion-scene>
      <p class="eyebrow">Repo Workbench</p>
      <h2>Repository work moves through a safe branch and pull request workflow.</h2>
      <article><h3>Analyze</h3><p>Detect frontend roots, backend services, package managers, scripts, and risk areas before editing.</p></article>
      <article><h3>Patch</h3><p>Apply targeted file changes, save snapshots, show diffs, and block empty pull requests.</p></article>
      <article><h3>Verify</h3><p>Run allowed commands, capture logs, repair failures, and persist the pull request URL when GitHub accepts it.</p></article>
    </section>

    <section id="feature-hierarchy" class="story-section feature-grid" data-amarktai-motion-scene>
      <p class="eyebrow">Feature hierarchy</p>
      <h2>The page explains what matters first, then proves how the platform works.</h2>
      <p>The highest-priority story is simple: Amarktai Builder turns a brief or repository into a validated production artifact. The supporting proof is organized around connected providers, agent execution, generated files, preview output, media evidence, runtime QA, deployment notes, and GitHub pull requests so buyers understand the operational value instead of reading decorative claims.</p>
    </section>

    <section id="runtime-qa" class="story-section split" data-amarktai-motion-scene>
      <div>
        <p class="eyebrow">Runtime QA evidence</p>
        <h2>Browser checks make readiness visible.</h2>
        <p>Playwright renders desktop, tablet, and mobile views; accessibility and performance reports are written beside screenshots; broken anchors, missing assets, console errors, and absent motion selectors block premium readiness.</p>
      </div>
      <ul class="check-list">
        <li>Desktop, tablet, and mobile screenshots</li>
        <li>Accessibility and performance reports</li>
        <li>Broken link and media validation</li>
        <li>Motion selector verification</li>
      </ul>
    </section>

    <section id="media-evidence" class="story-section" data-amarktai-motion-scene>
      <p class="eyebrow">Media manifest evidence</p>
      <h2>Every media claim must point to a persisted artifact.</h2>
      <p>Generated pages reference local media paths from media_manifest.json. Remote-only URLs, CSS gradients, and SVG decoration do not count as premium AI media proof. If GenX, Qwen, and Pixabay are unavailable, the runtime may preserve honest local fallback images, but the manifest labels those assets accurately and keeps the premium gate transparent.</p>
    </section>

    <section id="production-readiness" class="story-section cards" data-amarktai-motion-scene>
      <p class="eyebrow">Deployment and production readiness</p>
      <h2>Release decisions use the same gate in API, database, dashboard, and finalize flow.</h2>
      <article><h3>Provider truth</h3><p>GenX, Qwen, GitHub, Brave, Pixabay, and runtime tools are shown as live, missing, or untested without optimistic labels.</p></article>
      <article><h3>Finalize gate</h3><p>Quality, media, motion, runtime QA, content, security, and file contract checks must pass before push.</p></article>
      <article><h3>Deploy notes</h3><p>README and manifests describe the exact files produced and the safe path to publish them.</p></article>
    </section>

    <section id="lead-capture" class="story-section lead-capture" data-amarktai-motion-scene>
      <div>
        <p class="eyebrow">CTA lead capture form</p>
        <h2>Bring a repo, a product idea, or a broken build.</h2>
        <p>Tell Amarktai what you need to launch, then inspect the generated files, media, QA reports, and pull request evidence before finalizing.</p>
      </div>
      <form class="access-form" action="#production-readiness">
        <label for="work-email">Work email</label>
        <input id="work-email" name="email" type="email" autocomplete="email" required>
        <label for="project-goal">Launch goal</label>
        <textarea id="project-goal" name="goal" rows="4" required></textarea>
        <button class="button primary" type="submit">Prepare build brief</button>
      </form>
    </section>

    <section id="footer-section" class="story-section final-section" data-amarktai-motion-scene>
      <p class="eyebrow">Footer</p>
      <h2>Amarktai Builder ships with evidence, not optimism.</h2>
      <p>Use the dashboard to validate providers, review generated artifacts, run runtime QA, and create a GitHub pull request when every required gate passes. Every launch decision should be traceable to artifacts that a human can inspect: source files, manifests, screenshots, reports, logs, diffs, and saved deployment instructions.</p>
    </section>
  </main>
  <footer class="site-footer">
    <p>Amarktai Builder | Production AI software factory | Files, media, motion, QA, and deployment evidence must be real.</p>
  </footer>
  <script src="script.js"></script>
</body>
</html>
"""


def _bakery_static_index(prompt: str) -> str:
    title = "Luma & Stone" if "luma" in (prompt or "").lower() else escape(_project_name(prompt, "Artisan Bakery"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | Artisan Bakery</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body data-motion-runtime="pending">
  <header class="site-header">
    <a class="brand" href="#hero">{title}</a>
    <nav class="site-nav" aria-label="Primary">
      <a href="#sourdough">Sourdough</a>
      <a href="#pastries">Pastries</a>
      <a href="#coffee">Coffee</a>
      <a href="#events">Events</a>
      <a href="#contact">Visit</a>
    </nav>
  </header>
  <main>
    <section id="hero" class="hero bakery-hero" data-amarktai-motion-scene data-reveal>
      <div class="hero-copy">
        <p class="eyebrow">Luxury artisan bakery</p>
        <h1>Warm ovens, slow craft, and pastries worth crossing town for.</h1>
        <p class="lede">{title} is an editorial bakery experience built around naturally leavened bread, seasonal pastry, thoughtful coffee, and quiet hospitality.</p>
        <div class="actions"><a class="button primary" href="#contact">Plan a visit</a><a class="button secondary" href="#gallery">View the bakery</a></div>
      </div>
      <div class="hero-visual" aria-label="Warm artisan bakery table with bread and coffee"></div>
    </section>
    <section id="sourdough" class="story-section sourdough-section" data-amarktai-motion-scene data-reveal><p class="eyebrow">Artisan sourdough</p><h2>Long fermentation, deep flavor, crackling crust.</h2><p>Every loaf is mixed, folded, shaped, and baked with patience so the bread feels rustic, refined, and generous.</p></section>
    <section id="pastries" class="story-section pastries-section split" data-amarktai-motion-scene data-reveal><div><p class="eyebrow">Seasonal pastries</p><h2>Small-batch pastry guided by the market.</h2><p>Expect laminated dough, fruit tarts, morning buns, and rotating weekend specials finished with a light hand.</p></div><article><h3>Today from the case</h3><p>Croissants, rye chocolate babka, citrus danish, almond cakes, and savory galettes.</p></article></section>
    <section id="coffee" class="story-section coffee-section" data-amarktai-motion-scene data-reveal><p class="eyebrow">Coffee experience</p><h2>A calm room for espresso, filter coffee, and warm pastry.</h2><p>The coffee program is designed to complement butter, grain, chocolate, and fruit without overwhelming the bake.</p></section>
    <section id="gallery" class="story-section gallery-section" data-amarktai-motion-scene data-reveal><p class="eyebrow">Bakery gallery</p><h2>Texture, steam, and golden morning light.</h2><div class="gallery-grid"><article>Bread shelves</article><article>Pastry case</article><article>Coffee bar</article><article>Private table</article></div></section>
    <section id="events" class="story-section events-section split" data-amarktai-motion-scene data-reveal><div><p class="eyebrow">Private catering and events</p><h2>Elegant trays for gatherings that should feel personal.</h2><p>Breakfast meetings, intimate dinners, seasonal parties, and weekend celebrations can be built around bread, pastry, coffee, and dessert.</p></div><article><h3>Event rhythm</h3><p>Choose a bread board, pastry selection, coffee service, and a seasonal dessert finish.</p></article></section>
    <section id="testimonials" class="story-section testimonial-section" data-amarktai-motion-scene data-reveal><p class="eyebrow">Testimonials</p><h2>Beloved for warmth as much as craft.</h2><div class="grid"><article class="testimonial is-active">The sourdough has a deep, caramel crust and the room feels like a quiet celebration.</article><article class="testimonial">Our catering table looked beautiful and disappeared in minutes.</article><article class="testimonial">Coffee, pastry, and service all feel considered without being precious.</article></div></section>
    <section id="contact" class="story-section contact-section lead-capture" data-amarktai-motion-scene data-reveal><div><p class="eyebrow">Contact and visit</p><h2>Visit for the morning bake or plan a private order.</h2><p>Open Wednesday through Sunday with catering inquiries welcomed for seasonal events.</p></div><form class="access-form" action="#contact"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required><label for="request">What can we prepare?</label><textarea id="request" name="request" rows="4" required></textarea><button class="button primary" type="submit">Send inquiry</button></form></section>
  </main>
  <footer class="site-footer">© {title}. Artisan bread, seasonal pastry, coffee, and private catering.</footer>
  <script src="script.js"></script>
</body>
</html>
"""


def _premium_styles() -> str:
    return """
@import url("https://fonts.bunny.net/css?family=inter:400,600,700,800,900");

:root {
  --color-bg: #05070b;
  --color-panel: #101624;
  --color-panel-strong: #151d2f;
  --color-fg: #f8fafc;
  --color-muted: #a8b3c7;
  --color-accent: #00e676;
  --color-cyan: #53d8ff;
  --color-violet: #8b5cf6;
  --radius: 8px;
  --shadow: 0 32px 120px rgba(0, 0, 0, .45);
  --font-heading: Inter, ui-sans-serif, system-ui, sans-serif;
  --font-body: Inter, ui-sans-serif, system-ui, sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at 14% 7%, rgba(0, 230, 118, .22), transparent 29%),
    radial-gradient(circle at 85% 10%, rgba(83, 216, 255, .16), transparent 26%),
    radial-gradient(circle at 58% 2%, rgba(139, 92, 246, .22), transparent 32%),
    var(--color-bg);
  color: var(--color-fg);
  font-family: var(--font-body);
  line-height: 1.6;
}
.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px clamp(18px, 5vw, 72px);
  border-bottom: 1px solid rgba(255, 255, 255, .1);
  background: rgba(5, 7, 11, .82);
  backdrop-filter: blur(18px);
}
.brand, .site-header a { color: inherit; text-decoration: none; }
.brand { font-weight: 900; }
.site-header nav { display: flex; gap: 16px; flex-wrap: wrap; color: var(--color-muted); font-size: 14px; }
.hero {
  min-height: 86vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(300px, .95fr);
  gap: 48px;
  align-items: center;
  padding: clamp(56px, 8vw, 124px) clamp(18px, 7vw, 96px);
}
.hero-copy { max-width: 920px; }
.eyebrow {
  margin: 0 0 12px;
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .16em;
  text-transform: uppercase;
}
h1, h2, h3 { font-family: var(--font-heading); letter-spacing: 0; }
h1 { max-width: 900px; margin: 0; font-size: clamp(48px, 8vw, 96px); line-height: .96; }
h2 { margin: 0 0 14px; font-size: clamp(32px, 5vw, 58px); line-height: 1.04; }
h3 { margin: 0 0 10px; font-size: 22px; }
.lede, .story-section p, .site-footer p, .check-list {
  color: var(--color-muted);
  font-size: clamp(17px, 2vw, 22px);
  max-width: 880px;
}
.actions { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 28px; }
.button, .section-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 0 18px;
  border-radius: var(--radius);
  font-weight: 900;
  text-decoration: none;
  border: 0;
}
.primary { background: var(--color-accent); color: #04110a; }
.secondary, .section-link { border: 1px solid rgba(255, 255, 255, .18); background: rgba(255, 255, 255, .06); color: var(--color-fg); }
.hero-preview {
  min-height: 430px;
  position: relative;
  border: 1px solid rgba(255, 255, 255, .14);
  border-radius: 18px;
  background: linear-gradient(150deg, rgba(255, 255, 255, .14), rgba(255, 255, 255, .04));
  box-shadow: var(--shadow);
  overflow: hidden;
  animation: float 7s ease-in-out infinite;
}
.hero-preview::before {
  content: "";
  position: absolute;
  inset: -40%;
  background: conic-gradient(from 90deg, transparent, rgba(0, 230, 118, .34), transparent, rgba(83, 216, 255, .28), transparent, rgba(139, 92, 246, .32), transparent);
  animation: spin 18s linear infinite;
}
.preview-card {
  position: absolute;
  border: 1px solid rgba(255, 255, 255, .14);
  border-radius: 14px;
  background: rgba(5, 7, 11, .78);
  box-shadow: 0 24px 70px rgba(0, 0, 0, .36);
}
.preview-card-one { inset: 48px 42px 170px; }
.preview-card-two { left: 76px; right: 96px; bottom: 86px; height: 72px; }
.preview-card-three { right: 46px; top: 142px; width: 34%; height: 96px; }
.story-section {
  padding: clamp(52px, 7vw, 104px) clamp(18px, 7vw, 96px);
  border-top: 1px solid rgba(255, 255, 255, .09);
  background: linear-gradient(180deg, rgba(255, 255, 255, .025), transparent);
}
.story-section:nth-child(even) { background: rgba(255, 255, 255, .035); }
.split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, .72fr);
  gap: 32px;
  align-items: center;
}
.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.cards > .eyebrow, .cards > h2 { grid-column: 1 / -1; }
.cards article, .evidence-panel, .conversation, .access-form {
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: var(--radius);
  background: linear-gradient(180deg, rgba(255, 255, 255, .075), rgba(255, 255, 255, .035));
  box-shadow: 0 20px 70px rgba(0, 0, 0, .22);
  padding: 22px;
}
.conversation { display: grid; gap: 14px; max-width: 980px; }
.conversation p { margin: 0; font-size: 17px; }
.evidence-panel { min-height: 220px; display: grid; align-content: center; gap: 8px; }
.evidence-panel b { color: var(--color-fg); font-size: 24px; }
.check-list { margin: 0; padding-left: 22px; }
.lead-capture {
  display: grid;
  grid-template-columns: minmax(0, .85fr) minmax(280px, .65fr);
  gap: 32px;
  align-items: start;
}
.access-form { display: grid; gap: 12px; }
.access-form label { font-weight: 800; color: var(--color-fg); }
.access-form input, .access-form textarea {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, .16);
  border-radius: var(--radius);
  background: rgba(3, 6, 12, .72);
  color: var(--color-fg);
  padding: 12px 14px;
  font: inherit;
}
.final-section { text-align: left; }
.site-footer { padding: 38px clamp(18px, 7vw, 96px); border-top: 1px solid rgba(255, 255, 255, .09); }
.amarktai-generated-media { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; padding: clamp(2rem, 6vw, 5rem); }
.amarktai-generated-media img, .amarktai-generated-media video { width: 100%; border-radius: 20px; object-fit: cover; box-shadow: var(--shadow); }
[data-amarktai-motion-scene] { opacity: .92; transform: translateY(0); animation: rise .8s ease both; }
.motion-in-view { opacity: 1; transform: translateY(0) scale(1); }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
@keyframes rise { from { opacity: .2; transform: translateY(26px); } to { opacity: 1; transform: translateY(0); } }
@media (max-width: 980px) {
  .hero, .split, .lead-capture { grid-template-columns: 1fr; }
  .cards { grid-template-columns: 1fr; }
  .hero-preview { min-height: 300px; }
}
@media (max-width: 720px) {
  .site-header { align-items: flex-start; flex-direction: column; }
  .site-header nav { gap: 10px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
""".strip()


def _motion_script() -> str:
    return """
(() => {
  const scenes = Array.from(document.querySelectorAll('[data-amarktai-motion-scene]'));
  const motionNodes = Array.from(document.querySelectorAll('[data-motion-runtime], [data-amarktai-motion-scene]'));
  document.documentElement.dataset.motionRuntime = 'active';
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) {
    document.documentElement.dataset.motionRuntime = 'reduced';
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('motion-in-view');
      }
    });
  }, { threshold: 0.18 });
  scenes.forEach((scene, index) => {
    scene.style.transition = 'transform 700ms ease, opacity 700ms ease';
    scene.style.transitionDelay = `${Math.min(index * 70, 420)}ms`;
    io.observe(scene);
  });
  motionNodes.forEach((node) => node.setAttribute('data-motion-runtime', 'active'));
})();
""".lstrip()


def _is_bakery_prompt(prompt: str) -> bool:
    return bool(_BAKERY_HINTS.search(prompt or ""))


def _is_platform_prompt(prompt: str) -> bool:
    return bool(_PLATFORM_HINTS.search(prompt or ""))


def _requires_deep_static_sections(prompt: str) -> bool:
    return bool(re.search(r"\b(premium|cinematic|luxury|editorial)\b", prompt or "", re.IGNORECASE) or _is_bakery_prompt(prompt) or _is_platform_prompt(prompt))


def _customer_section_requirements(prompt: str) -> list[tuple[str, str, str]]:
    if _is_bakery_prompt(prompt):
        return [
            ("hero", "Cinematic hero", "A warm editorial opening with handcrafted bakery atmosphere and a clear reservation or visit CTA."),
            ("sourdough", "Artisan sourdough", "Naturally leavened loaves, long fermentation, crackling crusts, and daily bake rhythm."),
            ("pastries", "Seasonal pastries", "Rotating viennoiserie, fruit tarts, laminated dough, and small-batch pastry craft."),
            ("coffee", "Coffee experience", "A calm cafe ritual pairing espresso, filter coffee, and bakery seating."),
            ("gallery", "Bakery gallery", "Visual moments for bread shelves, pastry cases, coffee service, and warm interior details."),
            ("events", "Private catering and events", "Thoughtful catering for intimate gatherings, office breakfasts, and seasonal celebrations."),
            ("testimonials", "Testimonials", "Customer proof with specific warmth, service, and craft details."),
            ("contact", "Contact and visit", "Hours, location cue, inquiry path, and a direct call to plan a visit."),
        ]
    if _is_platform_prompt(prompt):
        return [
            ("hero", "Cinematic hero", "A clear platform opening with the main value proposition."),
            ("media-showcase", "AI image, video, and voice showcase", "Provider-backed media evidence and local persisted assets."),
            ("sales-agent", "AI sales-agent conversation demo", "A guided conversation that turns interest into a precise build brief."),
            ("repo-workbench", "Repo Workbench", "Repository analysis, patch, test, and pull request workflow."),
            ("runtime-qa", "Runtime QA evidence", "Browser rendering, accessibility, performance, links, media, and motion proof."),
            ("media-evidence", "Media manifest evidence", "Local media paths and manifest truth for generated assets."),
            ("production-readiness", "Deployment and production readiness", "Provider truth, quality gates, and deploy notes."),
            ("lead-capture", "CTA lead capture form", "A conversion point for access or project intake."),
        ]
    if not _requires_deep_static_sections(prompt):
        return []
    return [
        ("hero", "Cinematic hero", "A clear above-the-fold story with customer-specific positioning and a primary CTA."),
        ("proof", "Transformation proof", "Concrete proof that the offer solves the requested customer problem."),
        ("gallery", "Immersive media", "A visual or editorial section that supports the product story."),
        ("testimonials", "Testimonials", "Credible customer proof or outcome-oriented validation."),
        ("contact", "Contact and CTA", "A conversion section with a direct next action."),
    ]


def _html_has_section(html: str, section_id: str, title: str) -> bool:
    if section_id in _html_ids(html):
        return True
    title_pat = re.compile(rf"<(?:h2|h3)[^>]*>\s*{re.escape(title)}", re.IGNORECASE)
    return bool(title_pat.search(html or ""))


def _ensure_customer_sections(html: str, prompt: str) -> tuple[str, list[str]]:
    """Patch missing customer sections into otherwise-valid static HTML."""
    changed: list[str] = []
    additions: list[str] = []
    for section_id, title, body in _customer_section_requirements(prompt):
        if _html_has_section(html, section_id, title):
            continue
        changed.append(section_id)
        additions.append(
            f"""    <section id="{section_id}" class="story-section {section_id}-section" data-amarktai-motion-scene data-reveal>
      <p class="eyebrow">{escape(title)}</p>
      <h2>{escape(title)}</h2>
      <p>{escape(body)}</p>
    </section>"""
        )
    if not additions:
        return html, changed
    insertion = "\n\n".join(additions) + "\n"
    if "</main>" in html:
        html = html.replace("</main>", insertion + "  </main>", 1)
    elif "</body>" in html:
        html = html.replace("</body>", f"<main>\n{insertion}</main>\n</body>", 1)
    else:
        html += "\n<main>\n" + insertion + "</main>\n</body></html>"
    return html, changed


def _ensure_motion_and_asset_hooks(html: str) -> tuple[str, bool]:
    changed = False
    if "data-amarktai-motion-scene" not in html:
        html, count = re.subn(r"<section\b", "<section data-amarktai-motion-scene data-reveal", html, count=12, flags=re.IGNORECASE)
        changed = changed or bool(count)
    if "data-motion-runtime" not in html:
        if "<body" in html:
            html, count = re.subn(r"<body([^>]*)>", r'<body\1 data-motion-runtime="pending">', html, count=1, flags=re.IGNORECASE)
            changed = changed or bool(count)
        elif "</html>" in html:
            html = html.replace(
                "</html>",
                '<body data-motion-runtime="pending"><main><section id="hero" class="hero" data-amarktai-motion-scene data-reveal><h1>Generated landing page</h1><p>Preview-ready static landing page.</p></section></main></body></html>',
                1,
            )
            changed = True
        else:
            html = html.replace("<main", '<main data-motion-runtime="pending"', 1)
            changed = True
    if 'src="script.js"' not in html and "src='script.js'" not in html:
        if "</body>" in html:
            html = html.replace("</body>", '  <script src="script.js"></script>\n</body>', 1)
        else:
            html += '\n<script src="script.js"></script>\n'
        changed = True
    if "styles.css" not in html:
        link = '  <link rel="stylesheet" href="styles.css">\n'
        if "</head>" in html:
            html = html.replace("</head>", link + "</head>", 1)
        else:
            html = link + html
        changed = True
    return html, changed


def _brand_palette(prompt: str) -> dict[str, str]:
    if _is_bakery_prompt(prompt):
        return {
            "bg": "#24160f",
            "surface": "#fff4e4",
            "panel": "#3a2318",
            "fg": "#fffaf0",
            "muted": "#d8b98c",
            "accent": "#c98242",
            "accent2": "#f2c879",
            "font_heading": '"Cormorant Garamond", Georgia, serif',
            "font_body": '"Inter", "Avenir Next", Arial, sans-serif',
        }
    return {
        "bg": "#0d1117",
        "surface": "#f8fafc",
        "panel": "#151b23",
        "fg": "#f8fafc",
        "muted": "#a7b2c3",
        "accent": "#7dd3fc",
        "accent2": "#f0abfc",
        "font_heading": '"Space Grotesk", Inter, sans-serif',
        "font_body": 'Inter, "Avenir Next", Arial, sans-serif',
    }


def _generate_coherent_static_css(html: str, prompt: str) -> str:
    palette = _brand_palette(prompt)
    classes = sorted(_html_classes(html))
    class_rules = "\n".join(
        f".{name} {{ position: relative; }}" for name in classes
        if name not in {"button", "primary", "secondary"}
    )
    return f"""
:root {{
  --color-bg: {palette['bg']};
  --color-fg: {palette['fg']};
  --color-muted: {palette['muted']};
  --color-surface: {palette['surface']};
  --color-panel: {palette['panel']};
  --color-accent: {palette['accent']};
  --color-accent-2: {palette['accent2']};
  --font-heading: {palette['font_heading']};
  --font-body: {palette['font_body']};
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: radial-gradient(circle at 20% 0%, color-mix(in srgb, var(--color-accent) 26%, transparent), transparent 36rem), var(--color-bg);
  color: var(--color-fg);
  font-family: var(--font-body);
  line-height: 1.65;
}}
a {{ color: inherit; }}
.site-header {{
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding: 1rem clamp(1rem, 5vw, 4rem);
  background: color-mix(in srgb, var(--color-bg) 82%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--color-muted) 24%, transparent);
  backdrop-filter: blur(18px);
}}
.brand {{ font-family: var(--font-heading); font-size: clamp(1.3rem, 3vw, 2rem); text-decoration: none; letter-spacing: .02em; }}
nav {{ display: flex; flex-wrap: wrap; gap: .85rem; }}
nav a {{ text-decoration: none; color: var(--color-muted); font-size: .9rem; }}
main {{ overflow: hidden; }}
section, .story-section {{
  padding: clamp(4rem, 8vw, 8rem) clamp(1rem, 6vw, 5rem);
  border-bottom: 1px solid color-mix(in srgb, var(--color-muted) 14%, transparent);
}}
.hero {{
  min-height: 88vh; display: grid; align-items: center;
  grid-template-columns: minmax(0, 1.1fr) minmax(260px, .9fr); gap: clamp(2rem, 5vw, 5rem);
}}
h1, h2, h3 {{ font-family: var(--font-heading); line-height: .96; letter-spacing: 0; margin: 0 0 1rem; }}
h1 {{ font-size: clamp(3.4rem, 9vw, 8.5rem); max-width: 12ch; }}
h2 {{ font-size: clamp(2.4rem, 6vw, 5rem); max-width: 12ch; }}
h3 {{ font-size: clamp(1.3rem, 3vw, 2rem); }}
p {{ max-width: 68ch; }}
.lede {{ font-size: clamp(1.1rem, 2vw, 1.45rem); color: var(--color-muted); max-width: 56ch; }}
.eyebrow {{ color: var(--color-accent-2); text-transform: uppercase; letter-spacing: .14em; font-size: .78rem; font-weight: 700; }}
.button, button {{
  display: inline-flex; align-items: center; justify-content: center; min-height: 3rem;
  border-radius: 999px; padding: .85rem 1.25rem; border: 1px solid color-mix(in srgb, var(--color-accent) 52%, transparent);
  background: var(--color-accent); color: #190f09; font-weight: 800; text-decoration: none;
}}
.secondary {{ background: transparent; color: var(--color-fg); }}
.actions {{ display: flex; flex-wrap: wrap; gap: .85rem; margin-top: 1.5rem; }}
.split {{ display: grid; grid-template-columns: minmax(0, .95fr) minmax(280px, 1fr); gap: clamp(2rem, 5vw, 5rem); align-items: center; }}
.grid, .cards, .feature-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }}
article, .evidence-panel, .conversation, .access-form, .gallery-grid > *, .testimonial {{
  background: color-mix(in srgb, var(--color-panel) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-muted) 20%, transparent);
  border-radius: 24px; padding: clamp(1.2rem, 3vw, 2rem);
  box-shadow: 0 24px 90px rgba(0,0,0,.28);
}}
.gallery-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; }}
.access-form {{ display: grid; gap: .75rem; max-width: 560px; }}
input, textarea {{ width: 100%; border: 1px solid color-mix(in srgb, var(--color-muted) 28%, transparent); border-radius: 16px; padding: .9rem 1rem; background: rgba(255,255,255,.08); color: var(--color-fg); font: inherit; }}
.site-footer {{ padding: 2rem clamp(1rem, 6vw, 5rem); color: var(--color-muted); }}
[data-amarktai-motion-scene], [data-reveal] {{ opacity: .72; transform: translateY(18px); transition: opacity .7s ease, transform .7s ease; }}
.motion-in-view {{ opacity: 1; transform: translateY(0); }}
@keyframes gentle-float {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
.hero-visual, .visual, .hero-preview {{ min-height: 320px; border-radius: 36px; background: linear-gradient(135deg, color-mix(in srgb, var(--color-accent) 40%, transparent), color-mix(in srgb, var(--color-panel) 90%, transparent)); animation: gentle-float 7s ease-in-out infinite; }}
{class_rules}
@media (max-width: 900px) {{
  .hero, .split, .grid, .cards, .feature-grid, .gallery-grid {{ grid-template-columns: 1fr; }}
  .site-header {{ position: relative; align-items: flex-start; flex-direction: column; }}
  h1 {{ font-size: clamp(3rem, 16vw, 5rem); }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; scroll-behavior: auto !important; }}
  [data-amarktai-motion-scene], [data-reveal] {{ opacity: 1; transform: none; }}
}}
""".strip() + "\n"


def _generate_coherent_static_script(html: str) -> str:
    has_nav_toggle = "nav-toggle" in _html_classes(html)
    nav_selector = ".site-nav" if "site-nav" in _html_classes(html) else ("nav" if "<nav" in html else "")
    has_testimonials = any(name in _html_classes(html) for name in {"testimonial", "testimonial-track", "testimonial-dot"})
    motion_selector = "[data-reveal], [data-amarktai-motion-scene]" if ("data-reveal" in html or "data-amarktai-motion-scene" in html) else "[data-motion-runtime]"
    lines = [
        "(() => {",
        "  document.documentElement.dataset.motionRuntime = 'active';",
        "  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;",
        "  if (!prefersReduced) {",
        f"    const revealTargets = document.querySelectorAll('{motion_selector}');",
        "    const observer = new IntersectionObserver((entries) => {",
        "      entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add('motion-in-view'); });",
        "    }, { threshold: 0.16 });",
        "    revealTargets.forEach((target) => observer.observe(target));",
        "  }",
        "  document.querySelectorAll('a[href^=\"#\"]').forEach((link) => {",
        "    link.addEventListener('click', (event) => {",
        "      const target = document.querySelector(link.getAttribute('href'));",
        "      if (target) { event.preventDefault(); target.scrollIntoView({ behavior: prefersReduced ? 'auto' : 'smooth', block: 'start' }); }",
        "    });",
        "  });",
    ]
    if has_nav_toggle and nav_selector:
        lines.extend([
            "  const navToggle = document.querySelector('.nav-toggle');",
            f"  const nav = document.querySelector('{nav_selector}');",
            "  if (navToggle && nav) navToggle.addEventListener('click', () => nav.toggleAttribute('data-open'));",
        ])
    if has_testimonials:
        lines.extend([
            "  const testimonials = Array.from(document.querySelectorAll('.testimonial'));",
            "  if (testimonials.length > 1) {",
            "    let active = 0;",
            "    setInterval(() => { testimonials[active]?.classList.remove('is-active'); active = (active + 1) % testimonials.length; testimonials[active]?.classList.add('is-active'); }, 5000);",
            "  }",
        ])
    lines.append("})();")
    return "\n".join(lines) + "\n"


def premium_static_fallback_files(prompt: str) -> list[dict]:
    """Generate a complete static premium site without React scaffold files."""
    html = _bakery_static_index(prompt) if _is_bakery_prompt(prompt) else _premium_static_index(prompt)
    css = _generate_coherent_static_css(html, prompt)
    script = _generate_coherent_static_script(html)
    motion_manifest = {
        "status": "ready",
        "runtime": "static-css-js",
        "selectors": ["[data-amarktai-motion-scene]", "[data-motion-runtime]"],
        "changed_files": ["index.html", "styles.css", "script.js"],
        "reduced_motion_supported": True,
        "created_at": _now(),
    }
    files = [
        _file("index.html", html),
        _file("styles.css", css),
        _file("script.js", script),
        _file("README.md", _premium_static_readme(prompt)),
        _file("preview-manifest.json", json.dumps({"required": True, "strategy": "static", "status": "ready", "entry": "index.html"}, indent=2)),
        _file("motion_manifest.json", json.dumps(motion_manifest, indent=2)),
    ]
    files.append(_file("amarktai.project.json", _manifest("static-site", "landing-page", prompt, files)))
    return files


def _premium_static_readme(prompt: str) -> str:
    return f"""# {_project_name(prompt, "Amarktai Builder")}

Generated by Amarktai App Builder as a static premium fallback bundle after severe model output corruption.

## Files

- `index.html`
- `styles.css`
- `script.js`
- `README.md`
- `preview-manifest.json`
- `motion_manifest.json`
- `amarktai.project.json`

## Runtime Contract

- Static site only; no React, Vite, or package scaffold files are part of this bundle.
- Motion is implemented with CSS keyframes and `script.js` selectors that exist in `index.html`.
- Media runtime must add `media_manifest.json` and persisted local assets before a media-required premium build can be finalized.
- Runtime QA must add `runtime-qa/` artifacts before final production release.

## Original Prompt

{prompt}
"""


def _styles() -> str:
    return """*{box-sizing:border-box}body{margin:0;background:#08090c;color:#f7f7f8;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:inherit}.site-header{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 clamp(16px,4vw,56px);border-bottom:1px solid #23252d;background:#0d0f14}.brand{font-weight:800;text-decoration:none}.site-header nav{display:flex;gap:18px;color:#a9adba;font-size:14px}.site-header nav a{text-decoration:none}.hero{min-height:68vh;display:grid;grid-template-columns:1.1fr .9fr;gap:40px;align-items:center;padding:clamp(32px,7vw,96px)}.eyebrow{color:#00e676;text-transform:uppercase;font-size:12px;font-weight:800;letter-spacing:.14em}h1{font-size:clamp(40px,7vw,82px);line-height:.95;margin:0 0 18px}h2{margin:0 0 10px}.lede{font-size:clamp(18px,2.4vw,24px);line-height:1.45;color:#c9ccd6;max-width:680px}.button{display:inline-flex;margin-top:18px;height:46px;align-items:center;padding:0 18px;background:#00e676;color:#061008;border-radius:6px;text-decoration:none;font-weight:800}.visual{min-height:360px;border:1px solid #2b2e38;border-radius:12px;background:linear-gradient(135deg,#121722,#101014),radial-gradient(circle at 30% 20%,#00e67644,transparent 35%);box-shadow:0 30px 80px #0008;position:relative}.visual:before,.visual:after{content:"";position:absolute;border:1px solid #343946;background:#171b24;border-radius:10px}.visual:before{inset:52px 38px 110px}.visual:after{inset:150px 82px 50px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;padding:0 clamp(16px,7vw,96px) 56px}.grid article,.band,.deploy{border:1px solid #23252d;background:#11141b;border-radius:8px;padding:24px}.grid p,.band p,.deploy p,footer{color:#b5b9c5;line-height:1.6}.band,.deploy{margin:0 clamp(16px,7vw,96px) 24px}footer{padding:32px clamp(16px,7vw,96px);border-top:1px solid #23252d}@media(max-width:820px){.hero{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.site-header{align-items:flex-start;height:auto;padding-block:16px;gap:10px;flex-direction:column}.site-header nav{flex-wrap:wrap}.visual{min-height:240px}}"""


def _readme(project_type: str, build_mode: str, prompt: str) -> str:
    return f"""# {_project_name(prompt)}

Generated by Amarktai App Builder.

## Project

- Type: `{project_type}`
- Build mode: `{build_mode}`
- Prompt: {prompt}

## Preview

Preview in Amarktai App Builder before publishing. Static projects can also be opened from `index.html`.

## Deployment

Push the validated files to GitHub, then deploy to any compatible static host, VPS, or container platform. Do not commit real secrets. Use `.env.example` as a template only.
"""


def _manifest(project_type: str, build_mode: str, prompt: str, files: list[dict]) -> str:
    paths = sorted({f["path"] for f in files if f.get("path") != "amarktai.project.json"} | {"amarktai.project.json"})
    entry = "index.html" if "index.html" in paths else ("frontend/index.html" if "frontend/index.html" in paths else "README.md")
    preview_type = "static" if entry.endswith(".html") and project_type not in {"fullstack-app", "api-service", "repo-upgrade", "automation-bot-scaffold", "trading-bot-scaffold"} else "repo"
    return json.dumps({
        "projectName": _project_name(prompt),
        "projectType": project_type,
        "buildMode": build_mode,
        "entry": entry,
        "preview": {"type": preview_type, "entry": entry},
        "files": paths,
        "deployment": {
            "type": "static" if preview_type == "static" else "repository",
            "notes": "Preview before deployment. Can be pushed to GitHub after validation passes.",
        },
        "createdBy": "Amarktai App Builder",
        "version": 1,
    }, indent=2)


def _env_example(project_type: str) -> str:
    if project_type in {"fullstack-app", "api-service", "dashboard"}:
        return "JWT_SECRET=change_me\nDATABASE_URL=mongodb://localhost:27017/app\nCORS_ORIGINS=http://localhost:5173\n"
    if project_type in {"automation-bot-scaffold", "trading-bot-scaffold"}:
        return "BOT_MODE=paper\nAPI_BASE_URL=https://example.invalid\nLOG_LEVEL=info\n"
    return "# Optional runtime configuration\n"


def _fallback_content(path: str, project_type: str, build_mode: str, prompt: str, files: list[dict]) -> str:
    if path == "README.md":
        return _readme(project_type, build_mode, prompt)
    if path == "amarktai.project.json":
        return _manifest(project_type, build_mode, prompt, files)
    if path == ".env.example":
        return _env_example(project_type)
    if path == "index.html" and project_type in {"react-app", "pwa", "dashboard"}:
        return "<!doctype html><html><head><meta charset=\"UTF-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" /><link rel=\"stylesheet\" href=\"styles.css\" /><title>Amarktai App</title></head><body><div id=\"root\"></div><script type=\"module\" src=\"/src/main.jsx\"></script></body></html>\n"
    if path in {"index.html", "about.html", "services.html", "pricing.html", "contact.html"}:
        return _static_index(prompt if path == "index.html" else f"{path[:-5]} - {prompt}", multi=project_type == "multi-page-site")
    if path == "styles.css":
        return _styles()
    if path in {"app.js", "script.js", "motion.js"}:
        return "document.documentElement.classList.add('ready');\n"
    if path == "package.json":
        return json.dumps({"scripts": {"dev": "vite --host 0.0.0.0", "build": "vite build"}, "dependencies": {"@vitejs/plugin-react": "latest", "vite": "latest", "react": "latest", "react-dom": "latest"}, "devDependencies": {}}, indent=2)
    if path == "src/main.jsx":
        return "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App.jsx';\nimport './App.css';\ncreateRoot(document.getElementById('root')).render(<App />);\n"
    if path == "src/App.jsx":
        return "export default function App(){return <main style={{fontFamily:'system-ui',padding:24}}><h1>Amarktai App</h1><p>Preview this generated app, request changes, then publish after validation.</p></main>}\n"
    if path == "src/App.css":
        return ":root{font-family:Inter,system-ui,sans-serif;color:#f8fafc;background:#08090c}body{margin:0}main{min-height:100vh;background:radial-gradient(circle at top left,#1f3b73,#08090c 45%);display:grid;place-items:center}a,button{cursor:pointer}\n"
    if path == "preview-manifest.json":
        return json.dumps({"required": True, "strategy": "vite", "status": "pending", "entry": "index.html"}, indent=2)
    if path == "manifest.json":
        return json.dumps({"name": _project_name(prompt), "short_name": "Amarktai", "start_url": ".", "display": "standalone", "theme_color": "#08090c", "background_color": "#08090c", "icons": []}, indent=2)
    if path == "service-worker.js":
        return "const CACHE='amarktai-pwa-v1';const ASSETS=['./','index.html','manifest.json'];self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));self.addEventListener('fetch',e=>e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))));\n"
    if path == "backend/main.py":
        return "from fastapi import FastAPI\n\napp = FastAPI(title='Amarktai Generated API')\n\n@app.get('/health')\nasync def health():\n    return {'status':'ok'}\n"
    if path == "backend/requirements.txt":
        return "fastapi\nuvicorn\npydantic\n"
    if path == "frontend/index.html":
        return "<div id=\"root\"></div><script type=\"module\" src=\"/src/App.jsx\"></script>\n"
    if path == "frontend/package.json":
        return _fallback_content("package.json", project_type, build_mode, prompt, files)
    if path == "frontend/src/App.jsx":
        return _fallback_content("src/App.jsx", project_type, build_mode, prompt, files)
    if path == "docker-compose.yml":
        return "services:\n  backend:\n    build: ./backend\n    ports: ['8000:8000']\n"
    if path == "Dockerfile":
        return "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n"
    if path == "bot/main.py":
        return "def main():\n    print('Amarktai bot scaffold running in paper/safe mode')\n\nif __name__ == '__main__':\n    main()\n"
    if path == "bot/config.example.json":
        return json.dumps({"mode": "paper", "max_actions_per_hour": 10}, indent=2)
    if path == "bot/risk_controls.py":
        return "PAPER_MODE = True\nMAX_POSITION_SIZE = 0\nLIVE_TRADING_ENABLED = False\n"
    if path == "app/page.jsx":
        return "export default function Page(){return <main><h1>Amarktai App</h1><p>Generated Next app scaffold.</p></main>}\n"
    return ""


def _ensure_index_links_css(files_by_path: dict[str, dict]) -> bool:
    index = files_by_path.get("index.html")
    css = files_by_path.get("styles.css")
    if not index or not css:
        return False
    content = index.get("content", "")
    if "styles.css" in content:
        return False
    content = content.replace("</head>", "  <link rel=\"stylesheet\" href=\"styles.css\">\n</head>") if "</head>" in content else content + "\n<link rel=\"stylesheet\" href=\"styles.css\">\n"
    index["content"] = content
    return True


def _ensure_html_pages_link_css(files_by_path: dict[str, dict]) -> list[str]:
    """Ensure ALL HTML pages (not just index.html) link styles.css.

    Returns a list of page paths that were patched.
    Only runs when styles.css is present.
    """
    if "styles.css" not in files_by_path:
        return []
    patched: list[str] = []
    for path, file_dict in files_by_path.items():
        if not path.endswith((".html", ".htm")):
            continue
        content = file_dict.get("content", "")
        # Skip if page already has a stylesheet link or inline style
        has_link = (
            re.search(r'<link[^>]+rel=["\']stylesheet["\']', content, re.IGNORECASE)
            or re.search(r'<link[^>]+href=["\'][^"\']*\.css["\']', content, re.IGNORECASE)
            or re.search(r'<style[\s>]', content, re.IGNORECASE)
        )
        if has_link:
            continue
        # Insert the stylesheet link before </head> or append at end
        css_link = '  <link rel="stylesheet" href="styles.css">\n'
        if "</head>" in content:
            file_dict["content"] = content.replace("</head>", css_link + "</head>", 1)
        else:
            file_dict["content"] = content + "\n" + css_link
        patched.append(path)
    return patched


def _static_file_issues(files_by_path: dict[str, dict], prompt: str = "") -> list[str]:
    issues: list[str] = []
    html = str(files_by_path.get("index.html", {}).get("content", ""))
    css = str(files_by_path.get("styles.css", {}).get("content", ""))
    script = str(files_by_path.get("script.js", {}).get("content", "") or files_by_path.get("motion.js", {}).get("content", ""))
    if html and not _HTML_CLOSE_RE.search(html):
        issues.append("index.html is truncated or missing </html>.")
    if html and _requires_deep_static_sections(prompt) and len(_SECTION_RE.findall(html)) < 8:
        issues.append("index.html has fewer than 8 sections.")
    if css and (len(css) < 1200 or ":root" not in css or "--color" not in css or "@media" not in css):
        issues.append("styles.css is stub-level or missing design tokens/responsive rules.")
    if css and html:
        class_names = _html_classes(html)
        missing_selectors = [name for name in sorted(class_names)[:25] if f".{name}" not in css]
        if len(missing_selectors) > 6:
            issues.append("styles.css does not match key selectors referenced by index.html.")
    if html:
        ids = set(re.findall(r'id=["\']([^"\']+)["\']', html))
        for href in re.findall(r'href=["\']#([^"\']+)["\']', html):
            if href and href not in ids:
                issues.append(f"index.html contains broken anchor: #{href}.")
        missing_sections = [
            section_id
            for section_id, title, _body in _customer_section_requirements(prompt)
            if section_id not in ids and not _html_has_section(html, section_id, title)
        ]
        if missing_sections:
            issues.append(f"index.html is missing required premium sections: {', '.join(missing_sections)}.")
    if script:
        for selector in re.findall(r"querySelector(?:All)?\(['\"]([^'\"]+)['\"]\)", script):
            parts = [s.strip() for s in selector.split(",") if s.strip()]
            if len(parts) > 1:
                if not any(_selector_exists(part, html) for part in parts):
                    issues.append(f"script.js targets missing selector: {selector}.")
                continue
            for part in parts:
                if not _selector_exists(part, html):
                    issues.append(f"script.js targets missing selector: {part}.")
    if not script or "data-motion-runtime" not in html and "motionRuntime" not in script:
        issues.append("script.js/motion hooks are missing.")
    for manifest_path in ("preview-manifest.json", "motion_manifest.json", "amarktai.project.json"):
        if manifest_path not in files_by_path:
            continue
        try:
            manifest = json.loads(str(files_by_path[manifest_path].get("content", "")))
        except Exception:
            issues.append(f"{manifest_path} is invalid JSON.")
            continue
        listed = manifest.get("files")
        if isinstance(listed, list):
            missing_listed = [path for path in listed if path not in files_by_path]
            if missing_listed:
                issues.append(f"{manifest_path} lists files that do not exist: {', '.join(missing_listed[:5])}.")
    return issues


def _static_source_is_catastrophic(files_by_path: dict[str, dict]) -> bool:
    html = str(files_by_path.get("index.html", {}).get("content", ""))
    if not filter_app_source_files(list(files_by_path.values())):
        return True
    if not html.strip():
        return True
    if html and not _HTML_CLOSE_RE.search(html):
        return True
    if _STATIC_SECRET_RE.search(html):
        return True
    return False


def _regenerate_static_manifests(files_by_path: dict[str, dict], prompt: str) -> list[str]:
    changed: list[str] = []
    file_paths = sorted(path for path in files_by_path if not is_report_or_metadata_file(path))
    preview = json.dumps({
        "required": True,
        "strategy": "static",
        "status": "ready",
        "entry": "index.html",
        "files": file_paths,
    }, indent=2)
    motion = json.dumps({
        "status": "ready",
        "runtime": "static-css-js",
        "selectors": ["[data-amarktai-motion-scene]", "[data-motion-runtime]", "[data-reveal]"],
        "changed_files": ["index.html", "styles.css", "script.js"],
        "reduced_motion_supported": True,
        "created_at": _now(),
    }, indent=2)
    for path, content in {
        "preview-manifest.json": preview,
        "motion_manifest.json": motion,
    }.items():
        if files_by_path.get(path, {}).get("content") != content:
            files_by_path[path] = _file(path, content)
            changed.append(path)
    manifest = _manifest("static-site", "landing-page", prompt, list(files_by_path.values()))
    if files_by_path.get("amarktai.project.json", {}).get("content") != manifest:
        files_by_path["amarktai.project.json"] = _file("amarktai.project.json", manifest)
        changed.append("amarktai.project.json")
    return changed


def repair_static_design_family(project: dict, prompt: str, plan: dict | None, generated_files: list[dict], *, force: bool = False) -> tuple[list[dict], list[str]]:
    """Repair static HTML/CSS/JS as one coherent family without replacing valid customer HTML."""
    project_type = infer_project_type(project.get("mode"), project.get("project_type"))
    if project_type != "static-site":
        return generated_files or [], []
    files_by_path = {
        str(item.get("path")): dict(item)
        for item in (generated_files or [])
        if isinstance(item, dict) and item.get("path")
    }
    changed: list[str] = []
    for forbidden in list(STATIC_FORBIDDEN_FILES):
        if forbidden in files_by_path:
            files_by_path.pop(forbidden, None)
            changed.append(forbidden)
    catastrophic = _static_source_is_catastrophic(files_by_path)
    if catastrophic:
        fallback = {f["path"]: f for f in premium_static_fallback_files(prompt)}
        fallback_issues = _static_file_issues(fallback, prompt)
        if fallback_issues:
            raise RuntimeError(
                "premium_static_fallback_files produced invalid output: "
                + "; ".join(fallback_issues)
            )
        changed.extend(path for path in files_by_path if path not in fallback)
        changed.extend(path for path in fallback if files_by_path.get(path, {}).get("content") != fallback[path].get("content"))
        return list(fallback.values()), list(dict.fromkeys(changed))

    html_item = files_by_path.get("index.html")
    html = str(html_item.get("content", "")) if html_item else ""
    html, section_changes = _ensure_customer_sections(html, prompt)
    html, hook_changed = _ensure_motion_and_asset_hooks(html)
    if section_changes or hook_changed or html_item.get("content") != html:
        files_by_path["index.html"] = {**html_item, "content": html, "language": "html"}
        changed.append("index.html")
    css = _generate_coherent_static_css(html, prompt)
    if force or files_by_path.get("styles.css", {}).get("content") != css:
        files_by_path["styles.css"] = _file("styles.css", css)
        changed.append("styles.css")
    script = _generate_coherent_static_script(html)
    if force or files_by_path.get("script.js", {}).get("content") != script:
        files_by_path["script.js"] = _file("script.js", script)
        changed.append("script.js")
    if "README.md" not in files_by_path:
        files_by_path["README.md"] = _file("README.md", _premium_static_readme(prompt))
        changed.append("README.md")
    changed.extend(_regenerate_static_manifests(files_by_path, prompt))
    return list(files_by_path.values()), list(dict.fromkeys(changed))


def enforce_static_contract_files(project: dict, prompt: str, plan: dict | None, generated_files: list[dict]) -> tuple[list[dict], list[str]]:
    """Remove React scaffold from static builds and repair incomplete premium static output."""
    project_type = infer_project_type(project.get("mode"), project.get("project_type"))
    if project_type != "static-site":
        return generated_files or [], []
    files_by_path = {
        str(item.get("path")): dict(item)
        for item in (generated_files or [])
        if isinstance(item, dict) and item.get("path")
    }
    changed: list[str] = []
    for forbidden in list(STATIC_FORBIDDEN_FILES):
        if forbidden in files_by_path:
            files_by_path.pop(forbidden, None)
            changed.append(forbidden)
    issues = _static_file_issues(files_by_path, prompt)
    has_secret_like_content = any(
        _STATIC_SECRET_RE.search(str(item.get("content", "")))
        for item in files_by_path.values()
    )
    if issues and not has_secret_like_content:
        repaired, repair_changed = repair_static_design_family(project, prompt, plan, list(files_by_path.values()), force=True)
        return repaired, list(dict.fromkeys(changed + repair_changed))
    return list(files_by_path.values()), list(dict.fromkeys(changed))


def ensure_required_files(project: dict, prompt: str, plan: dict | None, generated_files: list[dict]) -> tuple[list[dict], list[str]]:
    project_type = infer_project_type(project.get("mode"), project.get("project_type"))
    build_mode = project.get("build_mode") if project.get("build_mode") in BUILD_MODES else infer_build_mode(project.get("mode"))
    files_by_path: dict[str, dict] = {}
    changed: list[str] = []

    generated_files, removed_contamination = remove_legacy_template_contamination(
        generated_files or [],
        prompt=prompt,
        requirements=project,
        plan=plan,
    )
    changed.extend(removed_contamination)
    generated_files, static_changed = enforce_static_contract_files(project, prompt, plan, generated_files)
    changed.extend(static_changed)

    for item in generated_files or []:
        try:
            path = safe_generated_path(str(item.get("path", "")))
        except ValueError:
            continue
        if path == ".env":
            continue
        files_by_path[path] = {"path": path, "language": item.get("language") or language_for(path), "content": str(item.get("content", ""))}

    required = get_required_files(project_type, build_mode, prompt, plan)
    for path in required:
        if path not in files_by_path or not str(files_by_path[path].get("content", "")).strip():
            files_by_path[path] = _file(path, _fallback_content(path, project_type, build_mode, prompt, list(files_by_path.values())))
            changed.append(path)

    # Link styles.css in every HTML page (not just index.html)
    for patched_path in _ensure_html_pages_link_css(files_by_path):
        if patched_path not in changed:
            changed.append(patched_path)

    manifest_path = "amarktai.project.json"
    current = files_by_path.get(manifest_path, {})
    try:
        json.loads(str(current.get("content", "")))
    except Exception:
        if manifest_path not in changed:
            changed.append(manifest_path)
    files = list(files_by_path.values())
    manifest = _manifest(project_type, build_mode, prompt, files)
    if files_by_path.get(manifest_path, {}).get("content") != manifest:
        files_by_path[manifest_path] = _file(manifest_path, manifest)
        if manifest_path not in changed:
            changed.append(manifest_path)
    final_files, removed_final = remove_legacy_template_contamination(
        list(files_by_path.values()),
        prompt=prompt,
        requirements=project,
        plan=plan,
    )
    changed.extend(path for path in removed_final if path not in changed)
    return final_files, changed


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*(?!change_me|example|your_|localhost)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def validate_project_files(project: dict, files: list[dict], prompt: str = "", plan: dict | None = None) -> dict:
    project_type = infer_project_type(project.get("mode"), project.get("project_type"))
    build_mode = project.get("build_mode") if project.get("build_mode") in BUILD_MODES else infer_build_mode(project.get("mode"))
    required = get_required_files(project_type, build_mode, prompt or project.get("prompt", ""), plan)
    by_path = {f.get("path"): f for f in files if f.get("path")}
    errors: list[str] = []
    warnings: list[str] = []

    missing = [p for p in required if p not in by_path]
    errors.extend(f"Missing required file: {p}" for p in missing)
    for path in required:
        if path in by_path and not str(by_path[path].get("content", "")).strip():
            errors.append(f"Required file is empty: {path}")

    for path in by_path:
        try:
            safe_generated_path(path)
        except ValueError as exc:
            errors.append(f"Unsafe file path: {path}: {exc}")
        if path == ".env" or path.endswith("/.env"):
            errors.append("Real .env files cannot be generated or finalized. Use .env.example.")
        if project_type == "static-site" and path in STATIC_FORBIDDEN_FILES:
            errors.append(f"Static landing page cannot include React scaffold file: {path}")

    manifest = by_path.get("amarktai.project.json")
    manifest_data: dict[str, Any] = {}
    if manifest:
        try:
            manifest_data = json.loads(str(manifest.get("content", "")))
        except Exception as exc:
            errors.append(f"amarktai.project.json is invalid JSON: {exc}")
    if manifest_data:
        listed = set(manifest_data.get("files") or [])
        for path in required:
            if path not in listed:
                errors.append(f"Manifest files list is missing required file: {path}")
        preview_entry = manifest_data.get("preview", {}).get("entry") or manifest_data.get("entry")
        if preview_entry and preview_entry not in by_path:
            errors.append(f"Preview entry does not exist: {preview_entry}")

    if project_type == "static-site":
        errors.extend(_static_file_issues(by_path, prompt))

    if project_type in {"react-app", "pwa", "next-app", "dashboard"} and "package.json" in by_path:
        try:
            pkg = json.loads(by_path["package.json"].get("content", "{}"))
            scripts = pkg.get("scripts") or {}
            if not (scripts.get("build") or scripts.get("dev") or scripts.get("start")):
                errors.append("package.json must include at least one build/dev/start script.")
        except Exception as exc:
            errors.append(f"package.json is invalid JSON: {exc}")

    for f in files:
        content = str(f.get("content", ""))
        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                errors.append(f"Possible secret value found in {f.get('path')}.")
                break

    preview_entry = "index.html" if "index.html" in by_path else ("frontend/index.html" if "frontend/index.html" in by_path else None)
    can_preview = bool(preview_entry and project_type not in {"fullstack-app", "api-service", "repo-upgrade", "automation-bot-scaffold", "trading-bot-scaffold"})

    # ── Quality / design / security scoring ──────────────────────────────────
    selected_stack = safe_dict(project.get("selected_stack"))
    auth_required = bool(project.get("auth_required") or selected_stack.get("auth") not in (None, "none", ""))
    quality_result = score_project_quality(
        files=files,
        project_type=project_type,
        build_mode=build_mode,
        prompt=prompt,
        auth_required=auth_required,
        media_strategy=project.get("media_strategy"),
    )

    # Quality / design / security: contribute to warnings and canFinalize only.
    # They do NOT affect the structural "ok" flag to preserve backward compat —
    # structural validation ensures files are present; quality gates block finalization.
    quality_ok = quality_result["qualityOk"]
    design_ok = quality_result["designOk"]
    security_ok = quality_result["securityOk"]
    media_ok = quality_result["mediaOk"]

    if not quality_ok:
        warnings.extend(quality_result["qualityErrors"])
    if not design_ok:
        warnings.extend(quality_result["designErrors"])
    if not security_ok:
        warnings.extend(quality_result["securityErrors"])
    if not media_ok:
        warnings.extend(quality_result["mediaErrors"])

    can_finalize = (
        not errors
        and quality_ok
        and design_ok
        and security_ok
    )

    return {
        "ok": not errors,
        "structureOk": not errors,
        "securityOk": security_ok,
        "qualityOk": quality_ok,
        "designOk": design_ok,
        "mediaOk": media_ok,
        "projectType": project_type,
        "buildMode": build_mode,
        "errors": errors,
        "warnings": warnings,
        "securityErrors": quality_result["securityErrors"],
        "qualityErrors": quality_result["qualityErrors"],
        "designErrors": quality_result["designErrors"],
        "mediaErrors": quality_result["mediaErrors"],
        "missingFiles": missing,
        "previewEntry": preview_entry,
        "canPreview": can_preview,
        "canFinalize": can_finalize,
        "qualityScore": quality_result["qualityScore"],
        "designScore": quality_result["designScore"],
        "securityScore": quality_result["securityScore"],
        "validatedAt": _now(),
    }


def extract_files_from_model_output(text: str) -> tuple[list[dict], list[str], str]:
    warnings: list[str] = []
    files: list[dict] = []
    summary = ""
    used_default_paths: set[str] = set()

    def add(path: str, content: str, language: str | None = None) -> None:
        try:
            cleaned = safe_generated_path(path)
        except ValueError as exc:
            warnings.append(f"Rejected unsafe path {path}: {exc}")
            return
        for i, existing in enumerate(files):
            if existing["path"] == cleaned:
                warnings.append(f"Duplicate path normalized to last writer: {cleaned}")
                files[i] = _file(cleaned, content)
                files[i]["language"] = language or language_for(cleaned)
                return
        files.append({"path": cleaned, "language": language or language_for(cleaned), "content": content})

    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            if isinstance(parsed.get("files"), list):
                for item in parsed["files"]:
                    if isinstance(item, dict):
                        add(str(item.get("path", "")), str(item.get("content", "")), item.get("language"))
                summary = str(parsed.get("summary", ""))
            else:
                for path, content in parsed.items():
                    if isinstance(content, str) and ("/" in path or "." in path):
                        add(path, content)
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    add(str(item.get("path", "")), str(item.get("content", "")), item.get("language"))
        if files:
            return files, warnings, summary
    except Exception:
        pass

    default_path_by_lang = {
        "html": "index.html",
        "htm": "index.html",
        "css": "styles.css",
        "javascript": "script.js",
        "js": "script.js",
        "jsx": "src/App.jsx",
        "markdown": "README.md",
        "md": "README.md",
    }

    fence = re.compile(r"```(?P<lang>[A-Za-z0-9_.+-]*)[ \t]*(?P<path>[^\n`]*)\n(?P<content>[\s\S]*?)```", re.MULTILINE)
    for match in fence.finditer(text or ""):
        lang = (match.group("lang") or "").strip()
        path = (match.group("path") or "").strip()
        if not path and re.match(r"^[\w./-]+\.[A-Za-z0-9]+$", lang):
            path, lang = lang, ""
        if not path:
            before = text[:match.start()].splitlines()[-2:]
            for line in reversed(before):
                m = re.search(r"(?:file|path|filename)\s*[:=]\s*`?([\w./-]+\.[A-Za-z0-9]+)`?", line, re.I)
                if m:
                    path = m.group(1)
                    break
                cleaned_line = re.sub(r"^[#*\-\s`]+|[`*:]+$", "", line.strip())
                if re.fullmatch(r"[\w./-]+\.[A-Za-z0-9]+", cleaned_line):
                    path = cleaned_line
                    break
        if not path:
            default_path = default_path_by_lang.get(lang.lower())
            content = match.group("content")
            if default_path and default_path not in used_default_paths:
                if default_path == "index.html" and "<html" not in content.lower() and "<!doctype" not in content.lower():
                    pass
                else:
                    path = default_path
                    used_default_paths.add(default_path)
        if path:
            add(path, match.group("content"), lang or None)
    if not files and "```json" not in (text or "").lower():
        html_match = re.search(r"(<!doctype\s+html[\s\S]*|<html[\s\S]*)", text or "", re.IGNORECASE)
        if html_match:
            add("index.html", html_match.group(1))
    if not files and (text or "").strip():
        warnings.append("No structured files found in model output.")
    return files, warnings, summary
