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
    "crm_dashboard": ("dashboard", "crm-dashboard"),
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


def premium_static_fallback_files(prompt: str) -> list[dict]:
    """Generate a complete static premium site without React scaffold files."""
    html = _premium_static_index(prompt)
    css = _premium_styles()
    script = _motion_script()
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


def _static_file_issues(files_by_path: dict[str, dict]) -> list[str]:
    issues: list[str] = []
    html = str(files_by_path.get("index.html", {}).get("content", ""))
    css = str(files_by_path.get("styles.css", {}).get("content", ""))
    script = str(files_by_path.get("script.js", {}).get("content", "") or files_by_path.get("motion.js", {}).get("content", ""))
    if html and not _HTML_CLOSE_RE.search(html):
        issues.append("index.html is truncated or missing </html>.")
    if html and len(_SECTION_RE.findall(html)) < 8:
        issues.append("index.html has fewer than 8 sections.")
    if css and (len(css) < 1200 or ":root" not in css or "--color" not in css or "@media" not in css):
        issues.append("styles.css is stub-level or missing design tokens/responsive rules.")
    if css and html:
        classes = set(re.findall(r'class=["\']([^"\']+)["\']', html))
        class_names = {part for group in classes for part in group.split()}
        missing_selectors = [name for name in sorted(class_names)[:25] if f".{name}" not in css]
        if len(missing_selectors) > 6:
            issues.append("styles.css does not match key selectors referenced by index.html.")
    if html:
        ids = set(re.findall(r'id=["\']([^"\']+)["\']', html))
        for href in re.findall(r'href=["\']#([^"\']+)["\']', html):
            if href and href not in ids:
                issues.append(f"index.html contains broken anchor: #{href}.")
        required_sections = {
            "hero",
            "media-showcase",
            "sales-agent",
            "repo-workbench",
            "runtime-qa",
            "media-evidence",
            "production-readiness",
            "lead-capture",
        }
        missing_sections = sorted(required_sections - ids)
        if missing_sections:
            issues.append(f"index.html is missing required premium sections: {', '.join(missing_sections)}.")
    if script:
        for selector in re.findall(r"querySelector(?:All)?\(['\"]([^'\"]+)['\"]\)", script):
            if selector.startswith("#") and selector[1:] not in re.findall(r'id=["\']([^"\']+)["\']', html):
                issues.append(f"script.js targets missing selector: {selector}.")
            if selector.startswith(".") and f'class="' in html and selector[1:] not in re.findall(r'class=["\']([^"\']+)["\']', html):
                issues.append(f"script.js targets missing selector: {selector}.")
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
    issues = _static_file_issues(files_by_path)
    has_secret_like_content = any(
        _STATIC_SECRET_RE.search(str(item.get("content", "")))
        for item in files_by_path.values()
    )
    if issues and not has_secret_like_content:
        fallback = {f["path"]: f for f in premium_static_fallback_files(prompt)}
        fallback_issues = _static_file_issues(fallback)
        if fallback_issues:
            raise RuntimeError(
                "premium_static_fallback_files produced invalid output: "
                + "; ".join(fallback_issues)
            )
        changed.extend(path for path in files_by_path if path not in fallback)
        changed.extend(path for path in fallback if files_by_path.get(path, {}).get("content") != fallback[path].get("content"))
        files_by_path = fallback
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
        errors.extend(_static_file_issues(by_path))

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
