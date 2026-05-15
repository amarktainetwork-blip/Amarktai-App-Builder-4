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
)

BUILD_MODES = (
    "landing-page", "multi-page-website", "pwa", "fullstack-saas",
    "dashboard", "api-service", "repo-upgrade", "automation-bot",
    "trading-bot-scaffold", "custom",
)

QUALITY_TIERS = ("cheap", "balanced", "premium")

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
    sections = [
        ("hero", "Cinematic AI Software Factory", "Build, repair, continue, preview, validate, and ship premium software from one production dashboard."),
        ("media", "Generated Media System", "Provider-backed visuals and persisted media manifests keep premium builds grounded in real assets."),
        ("agents", "Agent Orchestration", "Planner, Scout, Architect, Coder, Reviewer, Runtime QA, Security, and Advisor agents each leave evidence."),
        ("github", "GitHub Workflow", "Import repositories, analyze structure, patch files, run checks, review diffs, and open pull requests safely."),
        ("quality", "Hard Quality Gates", "No fallback-only output, placeholder copy, broken assets, or missing runtime proof can be marked ready."),
        ("runtime", "Runtime QA", "Playwright screenshots, accessibility audits, performance evidence, console checks, and motion validation are required."),
        ("deployment", "Deployment Orchestration", "Preview validated files, preserve artifacts, and prepare production deployment instructions."),
        ("pricing", "Access", "Bring your provider keys, connect GitHub, and operate a premium AI software factory with truthful readiness."),
    ]
    body = "\n".join(
        f'<section id="{sid}" class="story-section" data-amarktai-motion-scene>'
        f'<p class="eyebrow">{sid}</p><h2>{heading}</h2><p>{copy}</p>'
        f'<a class="section-link" href="#hero">Back to top</a></section>'
        for sid, heading, copy in sections[1:]
    )
    nav = "".join(f'<a href="#{sid}">{sid.title()}</a>' for sid, *_ in sections[1:5])
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
    <nav aria-label="Primary">{nav}</nav>
  </header>
  <main>
    <section id="hero" class="hero" data-amarktai-motion-scene>
      <div class="hero-copy">
        <p class="eyebrow">Production AI software factory</p>
        <h1>{title}</h1>
        <p class="lede">Amarktai Builder gives founders, agencies, product teams, startups, and businesses a cinematic command center for creating premium websites, applications, repo repairs, previews, quality gates, and GitHub pull requests.</p>
        <div class="actions"><a class="button primary" href="#github">Start with GitHub</a><a class="button secondary" href="#runtime">View runtime proof</a></div>
      </div>
      <div class="hero-preview" aria-label="Animated product preview"><span></span><span></span><span></span></div>
    </section>
    {body}
  </main>
  <footer><p>Amarktai Builder ships only when files, media, motion, QA, and deployment evidence are real.</p></footer>
  <script src="script.js"></script>
</body>
</html>
"""


def _premium_styles() -> str:
    return """:root{--color-bg:#05070b;--color-panel:#101624;--color-fg:#f8fafc;--color-muted:#a8b3c7;--color-accent:#00e676;--color-violet:#8b5cf6;--font-heading:Inter,ui-sans-serif,system-ui,sans-serif;--font-body:Inter,ui-sans-serif,system-ui,sans-serif;--shadow:0 32px 120px rgba(0,0,0,.45)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 15% 8%,rgba(0,230,118,.22),transparent 28%),radial-gradient(circle at 85% 10%,rgba(139,92,246,.22),transparent 30%),var(--color-bg);color:var(--color-fg);font-family:var(--font-body);line-height:1.6}.site-header{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px clamp(18px,5vw,72px);border-bottom:1px solid rgba(255,255,255,.1);background:rgba(5,7,11,.78);backdrop-filter:blur(18px)}.brand{font-weight:900;text-decoration:none}.site-header nav{display:flex;gap:16px;flex-wrap:wrap}.site-header a{color:inherit;text-decoration:none}.hero{min-height:86vh;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(300px,.95fr);gap:48px;align-items:center;padding:clamp(56px,8vw,124px) clamp(18px,7vw,96px)}.eyebrow{margin:0 0 12px;color:var(--color-accent);font-size:12px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}h1,h2{font-family:var(--font-heading);letter-spacing:0;line-height:1.02}h1{max-width:900px;margin:0;font-size:clamp(48px,8vw,96px)}h2{margin:0 0 14px;font-size:clamp(32px,5vw,60px)}.lede,.story-section p,footer p{color:var(--color-muted);font-size:clamp(17px,2vw,22px);max-width:820px}.actions{display:flex;gap:14px;flex-wrap:wrap;margin-top:28px}.button,.section-link{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:0 18px;border-radius:8px;font-weight:900;text-decoration:none}.primary{background:var(--color-accent);color:#04110a}.secondary,.section-link{border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.06);color:var(--color-fg)}.hero-preview{min-height:430px;position:relative;border:1px solid rgba(255,255,255,.14);border-radius:18px;background:linear-gradient(150deg,rgba(255,255,255,.14),rgba(255,255,255,.04));box-shadow:var(--shadow);overflow:hidden;animation:float 7s ease-in-out infinite}.hero-preview:before{content:"";position:absolute;inset:-40%;background:conic-gradient(from 90deg,transparent,rgba(0,230,118,.34),transparent,rgba(139,92,246,.32),transparent);animation:spin 18s linear infinite}.hero-preview span{position:absolute;border:1px solid rgba(255,255,255,.14);border-radius:14px;background:rgba(5,7,11,.78);box-shadow:0 24px 70px rgba(0,0,0,.36)}.hero-preview span:nth-child(1){inset:48px 42px 170px}.hero-preview span:nth-child(2){left:76px;right:96px;bottom:86px;height:72px}.hero-preview span:nth-child(3){right:46px;top:142px;width:34%;height:96px}.story-section{padding:clamp(52px,7vw,104px) clamp(18px,7vw,96px);border-top:1px solid rgba(255,255,255,.09);background:linear-gradient(180deg,rgba(255,255,255,.025),transparent)}.story-section:nth-child(even){background:rgba(255,255,255,.035)}.story-section p{font-size:20px}.amarktai-generated-media{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;padding:clamp(2rem,6vw,5rem)}.amarktai-generated-media img,.amarktai-generated-media video{width:100%;border-radius:20px;object-fit:cover;box-shadow:var(--shadow)}footer{padding:38px clamp(18px,7vw,96px);border-top:1px solid rgba(255,255,255,.09)}@keyframes spin{to{transform:rotate(360deg)}}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}[data-amarktai-motion-scene]{animation:rise .8s ease both}@keyframes rise{from{opacity:.2;transform:translateY(26px)}to{opacity:1;transform:translateY(0)}}@media(max-width:900px){.hero{grid-template-columns:1fr}.site-header{align-items:flex-start;flex-direction:column}.hero-preview{min-height:300px}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}"""


def _motion_script() -> str:
    return """(() => { const scenes=[...document.querySelectorAll('[data-amarktai-motion-scene]')]; document.documentElement.dataset.motionRuntime='active'; const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches; if(reduce){document.documentElement.dataset.motionRuntime='reduced'; return;} const io=new IntersectionObserver((entries)=>{ entries.forEach((entry)=>{ if(entry.isIntersecting){ entry.target.classList.add('motion-in-view'); } }); },{threshold:.18}); scenes.forEach((scene,index)=>{ scene.style.transition='transform 700ms ease, opacity 700ms ease'; scene.style.transitionDelay=`${Math.min(index*70,420)}ms`; io.observe(scene); }); })();\n"""


def premium_static_fallback_files(prompt: str) -> list[dict]:
    """Generate a complete static premium site without React scaffold files."""
    html = _premium_static_index(prompt)
    css = _premium_styles()
    script = _motion_script()
    files = [
        _file("index.html", html),
        _file("styles.css", css),
        _file("script.js", script),
        _file("README.md", _readme("static-site", "landing-page", prompt)),
        _file("preview-manifest.json", json.dumps({"required": True, "strategy": "static", "status": "ready", "entry": "index.html"}, indent=2)),
    ]
    files.append(_file("amarktai.project.json", _manifest("static-site", "landing-page", prompt, files)))
    return files


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
    if not script or "data-motion-runtime" not in html and "motionRuntime" not in script:
        issues.append("script.js/motion hooks are missing.")
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
        for path, item in fallback.items():
            if files_by_path.get(path, {}).get("content") != item.get("content"):
                files_by_path[path] = item
                changed.append(path)
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
