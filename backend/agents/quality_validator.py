"""
Quality, design, and security validator for Amarktai App Builder.

Scores generated projects on three dimensions:
  - qualityScore  (0-100): content completeness and richness
  - designScore   (0-100): visual design presence and uniqueness
  - securityScore (0-100): security hygiene (secrets, auth guards, .env.example)

Rules (from problem statement):
  - Landing pages fail if: nav/footer only, missing hero, <6 sections,
    <500 meaningful words, no CTAs, no visual sections, no responsive layout.
  - Security fails if: plaintext passwords, hardcoded JWT secrets,
    missing .env.example for fullstack, insecure defaults.
  - canFinalize is blocked unless qualityScore >= 75, designScore >= 70,
    and (if auth/security required) securityScore >= 75.
"""
from __future__ import annotations

import re
from typing import Any

# ── HTML content helpers ────────────────────────────────────────────────────

# Tags that represent distinct semantic sections in a page
_SECTION_TAGS = re.compile(
    r"<(section|article|header|footer|main|nav|aside|div)\b[^>]*>",
    re.IGNORECASE,
)
_HERO_PATTERNS = re.compile(
    r'class=["\'][^"\']*\bhero\b[^"\']*["\']|id=["\']hero["\']|<h1\b',
    re.IGNORECASE,
)
_CTA_PATTERNS = re.compile(
    r'<(a|button)[^>]*(class=["\'][^"\']*\b(btn|button|cta|action|signup|get-started)[^"\']*["\']'
    r'|href=["\']#[^"\']+["\'])[^>]*>|<a[^>]+class=["\'][^"\']*button[^"\']*["\']',
    re.IGNORECASE,
)
_RESPONSIVE_PATTERNS = re.compile(
    r"@media\s*\([^)]*(?:max-width|min-width|screen)[^)]*\)"
    r"|viewport|grid-template-columns|flex\b",
    re.IGNORECASE,
)
_FEATURE_SECTION_PATTERNS = re.compile(
    r'id=["\'](?:features?|about|services?|pricing|testimonials?|workflow|how|why|benefits?)["\']'
    r'|class=["\'][^"\']*(?:feature|benefit|service|pricing|testimonial|team)[^"\']*["\']',
    re.IGNORECASE,
)
_GRADIENT_OR_VISUAL = re.compile(
    r"background:\s*(?:linear-gradient|radial-gradient)|background-image:"
    r"|<img\b[^>]*src=[\"'][^\"']+[\"']|<svg\b|\.visual|\.hero-image|\.banner",
    re.IGNORECASE,
)
_GENERIC_COPY = re.compile(
    r"\blorem ipsum\b|placeholder text|PLACEHOLDER|{{[^}]+}}|\[YOUR [A-Z ]+\]",
    re.IGNORECASE,
)

# ── Font & readability helpers ───────────────────────────────────────────────

# Detects a web font loaded from Bunny Fonts or Google Fonts
_WEB_FONT_LINK = re.compile(
    r'<link[^>]+href=["\'][^"\']*(?:fonts\.bunny\.net|fonts\.googleapis\.com)[^"\']*["\']'
    r'|@import\s+url\s*\([^)]*(?:fonts\.bunny\.net|fonts\.googleapis\.com)[^)]*\)',
    re.IGNORECASE,
)
# Detects only system/fallback font stacks (no custom named font)
_ONLY_SYSTEM_FONTS = re.compile(
    r"font-family\s*:[^;]*(?:sans-serif|serif|monospace|system-ui|Arial|Helvetica|Georgia|Verdana|Tahoma)[^;]*;",
    re.IGNORECASE,
)
# Detects problematic very low text opacity
_LOW_OPACITY_TEXT = re.compile(
    r"color\s*:[^;]*rgba?\([^)]*,\s*0\.[0-2]\d*\s*\)",
    re.IGNORECASE,
)
# Detects font-size explicitly set very small (< 12px) on body/p/li
_TINY_FONT_SIZE = re.compile(
    r"(?:body|p|li|span)[^{]*\{[^}]*font-size\s*:\s*([0-9]+)px",
    re.IGNORECASE,
)

# ── Security helpers ────────────────────────────────────────────────────────

_HARDCODED_SECRET = re.compile(
    r'(?i)(jwt[_-]?secret|jwt_key|secret[_-]?key|api[_-]?key|password|passwd)\s*[=:]\s*'
    r'(?!change[_-]?me|your[_-]?|example|localhost|<|{|\$|""|\'\'|placeholder|paste[_-]?here|process\.env|os\.getenv|os\.environ)'
    r'["\']?[A-Za-z0-9@#$%^&*!_\-]{12,}["\']?',
)
_PLAINTEXT_PASSWORD_STORE = re.compile(
    r"password\s*=\s*['\"](?!hash|bcrypt|\$2[aby]\$)[^'\"]{6,}['\"]",
    re.IGNORECASE,
)
_MISSING_HASH_IMPORT = re.compile(
    r"(login|register|auth|user)\s*\(",
    re.IGNORECASE,
)
_HAS_HASH_LIB = re.compile(
    r"bcrypt|passlib|argon2|hashlib|scrypt|pbkdf2",
    re.IGNORECASE,
)
_HAS_AUTH_GUARD = re.compile(
    r"@require_auth|Depends\(require|middleware\s*\([^)]*auth|jwt\.verify"
    r"|isAuthenticated|requireAuth|authMiddleware|protected_route",
    re.IGNORECASE,
)
_HAS_JWT = re.compile(r"jwt|jsonwebtoken|PyJWT|python-jose", re.IGNORECASE)

# ── Text content helpers ────────────────────────────────────────────────────

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _strip_html(content: str) -> str:
    return _WHITESPACE.sub(" ", _HTML_TAG.sub(" ", content)).strip()


def _word_count(content: str) -> int:
    text = _strip_html(content)
    return len(text.split())


def _count_sections(html_content: str) -> int:
    """Count distinct top-level section-like blocks."""
    return len(_SECTION_TAGS.findall(html_content))


# ── Scoring functions ────────────────────────────────────────────────────────

def _score_static_landing(
    files_by_path: dict[str, dict],
    project_type: str,
    build_mode: str,
) -> tuple[int, int, list[str], list[str]]:
    """Score a static landing page or multi-page site.

    Returns (quality_score, design_score, quality_errors, design_errors).
    """
    quality = 100
    design = 100
    quality_errors: list[str] = []
    design_errors: list[str] = []

    index = files_by_path.get("index.html", {})
    styles = files_by_path.get("styles.css", {})
    html = index.get("content", "")
    css = styles.get("content", "")
    combined = html + "\n" + css

    if not html.strip():
        quality -= 40
        quality_errors.append("index.html is empty or missing content.")
        design -= 40
        design_errors.append("index.html is empty or missing content.")
        return max(0, quality), max(0, design), quality_errors, design_errors

    # Hero check
    if not _HERO_PATTERNS.search(html):
        quality -= 15
        quality_errors.append("Landing page is missing a hero section or <h1>.")
        design -= 10
        design_errors.append("No hero section detected.")

    # Section count (target ≥ 6)
    section_count = _count_sections(html)
    if section_count < 6:
        penalty = max(0, (6 - section_count)) * 4
        quality -= penalty
        quality_errors.append(
            f"Only {section_count} structural sections detected (minimum 6 required)."
        )

    # Word count (target ≥ 500)
    words = _word_count(html)
    if words < 500:
        penalty = max(0, min(20, (500 - words) // 20))
        quality -= penalty
        quality_errors.append(
            f"Only {words} meaningful words detected (minimum 500 required)."
        )

    # CTA check
    if not _CTA_PATTERNS.search(html):
        quality -= 10
        quality_errors.append(
            "No CTA (call-to-action) buttons or links detected."
        )

    # Feature section check
    if not _FEATURE_SECTION_PATTERNS.search(html):
        quality -= 8
        quality_errors.append(
            "No feature/benefit/service sections detected."
        )

    # Generic placeholder copy check
    if _GENERIC_COPY.search(html):
        quality -= 12
        quality_errors.append(
            "Generic placeholder copy or lorem ipsum text found. Replace with real content."
        )

    # Responsive layout check (in CSS or inline)
    if not _RESPONSIVE_PATTERNS.search(combined):
        quality -= 10
        quality_errors.append("No responsive CSS (media queries or flexbox/grid) detected.")
        design -= 15
        design_errors.append("No responsive layout detected.")

    # Visual interest check
    if not _GRADIENT_OR_VISUAL.search(combined):
        design -= 20
        design_errors.append(
            "No visual elements detected (no gradients, images, SVGs, or visual sections)."
        )

    # CSS presence and quality check
    # Check if any CSS file exists (styles.css, main.css, etc.)
    has_css_file = bool(styles.get("content", "").strip()) or any(
        k.endswith(".css") and v.get("content", "").strip()
        for k, v in files_by_path.items()
        if k != "styles.css"
    )
    # Detect framework CSS loaded via CDN: require a link/script tag or @import pointing to the framework
    has_framework_css = bool(re.search(
        r'<link[^>]+href=["\'][^"\']*(?:tailwind|bootstrap|bulma|materialize|foundation)[^"\']*["\']'
        r'|@import\s+["\'][^"\']*(?:tailwind|bootstrap|bulma|materialize|foundation)[^"\']*["\']',
        html, re.IGNORECASE,
    ))

    css_content = css.strip()
    if not has_css_file and not has_framework_css:
        # No CSS at all: hard design fail — site will render completely unstyled
        design -= 30
        design_errors.append(
            "No CSS file found (styles.css missing) and no framework CSS detected. "
            "Site will render unstyled. Create styles.css with full styling."
        )
    elif len(css_content) < 500:
        # CSS present but very thin
        design -= 15
        design_errors.append(
            f"CSS is very thin ({len(css_content)} chars). Expected substantial styling."
        )

    # Multi-page: verify that every HTML page links a stylesheet
    # Collect all HTML pages in the files_by_path dict
    html_pages = [
        (path, f)
        for path, f in files_by_path.items()
        if isinstance(path, str) and path.endswith((".html", ".htm"))
    ]
    if len(html_pages) > 1:
        pages_without_css: list[str] = []
        for pg_path, pg_f in html_pages:
            pg_content = pg_f.get("content", "")
            has_styling = bool(
                re.search(r'<link[^>]+rel=["\']stylesheet["\']', pg_content, re.IGNORECASE)
                or re.search(r'<link[^>]+href=["\'][^"\']*\.css["\']', pg_content, re.IGNORECASE)
                or re.search(r'<style[\s>]', pg_content, re.IGNORECASE)
            )
            if not has_styling:
                pages_without_css.append(pg_path)
        if pages_without_css:
            penalty = min(30, len(pages_without_css) * 10)
            design -= penalty
            design_errors.append(
                f"{len(pages_without_css)} page(s) have no linked stylesheet: "
                f"{', '.join(pages_without_css[:3])}"
            )
        # If there are no CSS files at all and multiple pages, apply a severe design penalty
        has_any_css = any(
            path.endswith(".css") for path in files_by_path
        )
        if not has_any_css and len(html_pages) >= 2:
            design -= 50
            design_errors.append(
                "Multi-page site has no CSS file at all. "
                "All pages require a shared stylesheet."
            )

    # ── Font & readability checks ─────────────────────────────────────────────
    # Check for web font loading (Bunny Fonts or Google Fonts)
    if not _WEB_FONT_LINK.search(combined):
        design -= 8
        design_errors.append(
            "No web font loaded from Bunny Fonts or Google Fonts. "
            "Add a <link> to fonts.bunny.net to ensure custom typography renders."
        )

    # Flag very low opacity text (near-invisible)
    if _LOW_OPACITY_TEXT.search(css):
        design -= 10
        design_errors.append(
            "Very low-opacity text color detected (opacity < 0.2). "
            "Ensure body text has sufficient opacity for readability."
        )

    # Flag tiny font sizes
    for m in _TINY_FONT_SIZE.finditer(css):
        try:
            px = int(m.group(1))
            if px < 12:
                design -= 8
                design_errors.append(
                    f"Font size {px}px is too small for readable body text. "
                    "Use at least 16px for body/paragraph text."
                )
                break
        except ValueError:
            pass

    return max(0, quality), max(0, design), quality_errors, design_errors


def _score_pwa(files_by_path: dict[str, dict]) -> tuple[int, list[str]]:
    """Score a PWA project for quality. Returns (quality_score, quality_errors)."""
    quality = 100
    errors: list[str] = []

    manifest = files_by_path.get("manifest.json", {})
    sw = files_by_path.get("service-worker.js", {})
    index = files_by_path.get("index.html", {})

    if not manifest.get("content", "").strip():
        quality -= 20
        errors.append("manifest.json is missing or empty.")
    else:
        try:
            import json
            m = json.loads(manifest["content"])
            if not m.get("name"):
                quality -= 5
                errors.append("manifest.json is missing 'name' field.")
            if not m.get("start_url"):
                quality -= 5
                errors.append("manifest.json is missing 'start_url' field.")
            if not m.get("icons"):
                quality -= 5
                errors.append("manifest.json has no icons defined.")
        except Exception:
            quality -= 10
            errors.append("manifest.json is invalid JSON.")

    if not sw.get("content", "").strip():
        quality -= 25
        errors.append("service-worker.js is missing or empty.")
    elif "install" not in sw["content"] or "fetch" not in sw["content"]:
        quality -= 10
        errors.append("service-worker.js appears incomplete (missing install/fetch handlers).")

    if not index.get("content", "").strip():
        quality -= 20
        errors.append("index.html is empty.")
    elif _word_count(index.get("content", "")) < 50:
        quality -= 10
        errors.append("PWA index.html has very little meaningful UI content.")

    return max(0, quality), errors


def _score_fullstack(files_by_path: dict[str, dict]) -> tuple[int, list[str]]:
    """Score a full-stack app for quality. Returns (quality_score, quality_errors)."""
    quality = 100
    errors: list[str] = []

    # Check backend health route
    backend_main = files_by_path.get("backend/main.py", {}).get("content", "")
    if not backend_main.strip():
        quality -= 25
        errors.append("backend/main.py is missing or empty.")
    elif "/health" not in backend_main and "health" not in backend_main:
        quality -= 10
        errors.append("Backend missing /health endpoint.")

    # Check .env.example
    env_example = files_by_path.get(".env.example", {}).get("content", "")
    if not env_example.strip():
        quality -= 15
        errors.append(".env.example is missing or empty.")

    # Check frontend
    frontend_app = (
        files_by_path.get("frontend/src/App.jsx", {}).get("content", "")
        or files_by_path.get("src/App.jsx", {}).get("content", "")
    )
    if not frontend_app.strip():
        quality -= 20
        errors.append("Frontend App.jsx is missing or empty.")
    elif _word_count(frontend_app) < 30:
        quality -= 10
        errors.append("Frontend App.jsx has very little meaningful content.")

    # Check docker-compose.yml
    if not files_by_path.get("docker-compose.yml", {}).get("content", "").strip():
        quality -= 10
        errors.append("docker-compose.yml is missing or empty.")

    return max(0, quality), errors


def _score_api_service(files_by_path: dict[str, dict]) -> tuple[int, list[str]]:
    """Score an API service for quality."""
    quality = 100
    errors: list[str] = []

    backend_main = files_by_path.get("backend/main.py", {}).get("content", "")
    if not backend_main.strip():
        quality -= 35
        errors.append("backend/main.py is missing or empty.")
    else:
        if "/health" not in backend_main and "health" not in backend_main:
            quality -= 15
            errors.append("API missing /health endpoint.")
        if "route" not in backend_main.lower() and "@app." not in backend_main and "router" not in backend_main.lower():
            quality -= 15
            errors.append("API has no detectable routes.")

    if not files_by_path.get(".env.example", {}).get("content", "").strip():
        quality -= 15
        errors.append(".env.example is missing or empty.")

    return max(0, quality), errors


def _score_security(
    files_by_path: dict[str, dict],
    project_type: str,
    auth_required: bool,
) -> tuple[int, list[str]]:
    """Score security hygiene. Returns (security_score, security_errors)."""
    score = 100
    errors: list[str] = []

    all_content = "\n".join(f.get("content", "") for f in files_by_path.values())

    # Check for hardcoded secrets
    secrets_found = _HARDCODED_SECRET.findall(all_content)
    if secrets_found:
        score -= 30
        errors.append(
            f"Possible hardcoded secrets found ({len(secrets_found)} occurrence(s)). "
            "Use .env.example placeholders instead."
        )

    # Check .env exists (forbidden)
    if ".env" in files_by_path and ".env.example" not in files_by_path.get(".env", {}).get("path", ""):
        score -= 20
        errors.append("Real .env file must not be generated. Use .env.example only.")

    # Fullstack/API: require .env.example
    if project_type in {"fullstack-app", "api-service", "dashboard",
                        "automation-bot-scaffold", "trading-bot-scaffold"}:
        if not files_by_path.get(".env.example", {}).get("content", "").strip():
            score -= 15
            errors.append("Full-stack/.env.example is required but missing.")

    # Auth-required: check for auth guards and hashing
    if auth_required or project_type in {"fullstack-app", "dashboard"}:
        backend_content = "\n".join(
            f.get("content", "") for path, f in files_by_path.items()
            if path.startswith("backend/") or path.endswith(".py")
        )
        if backend_content:
            if not _HAS_HASH_LIB.search(backend_content):
                score -= 15
                errors.append(
                    "Auth routes detected but no password hashing library found "
                    "(bcrypt/passlib/argon2)."
                )
            if not _HAS_JWT.search(backend_content):
                score -= 10
                errors.append(
                    "Auth required but no JWT library detected in backend."
                )
            if not _HAS_AUTH_GUARD.search(backend_content):
                score -= 10
                errors.append(
                    "Auth required but no auth guard/middleware/dependency detected."
                )

    # Trading bot: require paper mode default
    if project_type == "trading-bot-scaffold":
        bot_content = "\n".join(
            f.get("content", "") for path, f in files_by_path.items()
            if path.startswith("bot/")
        )
        if bot_content and "LIVE_TRADING_ENABLED" not in bot_content and "paper" not in bot_content.lower():
            score -= 20
            errors.append(
                "Trading bot must have paper/safe mode as default "
                "(LIVE_TRADING_ENABLED=false or paper mode)."
            )

    return max(0, score), errors


# ── Public API ───────────────────────────────────────────────────────────────

# Minimum passing thresholds (problem statement spec)
MIN_QUALITY_SCORE = 75
MIN_DESIGN_SCORE = 70
MIN_SECURITY_SCORE = 75  # Only enforced when auth/security is relevant


def score_project_quality(
    files: list[dict],
    project_type: str,
    build_mode: str,
    prompt: str = "",
    auth_required: bool = False,
    media_strategy: dict | None = None,
) -> dict[str, Any]:
    """Run quality, design, and security scoring for a generated project.

    Returns a dict containing:
      qualityScore, designScore, securityScore,
      qualityErrors, designErrors, securityErrors,
      qualityOk, designOk, securityOk, mediaOk
    """
    files_by_path = {f["path"]: f for f in files if f.get("path")}

    quality_score = 100
    design_score = 100
    quality_errors: list[str] = []
    design_errors: list[str] = []

    # ── project-type scoring ──────────────────────────────────────────────────
    if project_type in {"static-site", "multi-page-site"}:
        quality_score, design_score, quality_errors, design_errors = _score_static_landing(
            files_by_path, project_type, build_mode
        )
        # Multi-page: check extra pages exist
        if project_type == "multi-page-site":
            prompt_lower = prompt.lower()
            page_keywords = {
                "about": "about.html",
                "service": "services.html",
                "pricing": "pricing.html",
                "contact": "contact.html",
            }
            for keyword, page_file in page_keywords.items():
                if keyword in prompt_lower and page_file not in files_by_path:
                    quality_score -= 8
                    quality_errors.append(
                        f"Prompt mentions '{keyword}' but {page_file} was not generated."
                    )
            # Multi-page: ensure all generated HTML pages link a stylesheet.
            # Cap total penalty at 16 points to avoid punishing large sites excessively.
            pages_missing_css = [
                path for path, f in files_by_path.items()
                if path.endswith(".html")
                and f.get("content", "").strip()
                and not re.search(
                    r'<link[^>]+rel=["\']stylesheet["\']'
                    r'|<link[^>]+href=["\'][^"\']*\.css[^"\']*["\']'
                    r'|tailwind|bootstrap',
                    f.get("content", ""), re.IGNORECASE,
                )
            ]
            if pages_missing_css:
                penalty = min(16, len(pages_missing_css) * 8)
                design_score -= penalty
                design_errors.append(
                    f"{len(pages_missing_css)} HTML page(s) do not link a stylesheet "
                    f"({', '.join(pages_missing_css[:3])}{'...' if len(pages_missing_css) > 3 else ''}). "
                    "Add <link rel=\"stylesheet\" href=\"styles.css\"> in <head> of each page."
                )

    elif project_type == "pwa":
        quality_score, quality_errors = _score_pwa(files_by_path)
        # Design score for PWA: check for responsive CSS
        css_content = "\n".join(
            f.get("content", "") for path, f in files_by_path.items()
            if path.endswith(".css")
        )
        if not _RESPONSIVE_PATTERNS.search(css_content):
            design_score = 60
            design_errors.append("No responsive CSS detected in PWA.")

    elif project_type in {"fullstack-app", "dashboard"}:
        quality_score, quality_errors = _score_fullstack(files_by_path)

    elif project_type == "api-service":
        quality_score, quality_errors = _score_api_service(files_by_path)

    elif project_type in {"react-app", "next-app"}:
        # React/Next: check for meaningful App component
        app_content = (
            files_by_path.get("src/App.jsx", {}).get("content", "")
            or files_by_path.get("src/App.tsx", {}).get("content", "")
            or files_by_path.get("app/page.jsx", {}).get("content", "")
            or files_by_path.get("app/page.tsx", {}).get("content", "")
        )
        if not app_content.strip():
            quality_score -= 30
            quality_errors.append("Main App component is missing or empty.")
        elif _word_count(app_content) < 30:
            quality_score -= 15
            quality_errors.append("Main App component has very little meaningful content.")
        if _GENERIC_COPY.search(app_content):
            quality_score -= 10
            quality_errors.append("Generic placeholder copy found in App component.")

    # ── security scoring ──────────────────────────────────────────────────────
    security_score, security_errors = _score_security(
        files_by_path, project_type, auth_required
    )

    # ── media validation ──────────────────────────────────────────────────────
    # Validate media choices match what was requested
    ms = media_strategy or {}
    ms_mode = ms.get("mode", "auto")
    media_ok = True
    media_errors: list[str] = []

    for path, f in files_by_path.items():
        content = f.get("content", "")
        if path.endswith(".html"):
            # css_svg: no external image URLs allowed
            if ms_mode == "css_svg":
                ext_imgs = re.findall(
                    r'src=["\']https?://[^"\']*\.(jpg|jpeg|png|gif|webp)["\']',
                    content, re.IGNORECASE,
                )
                if ext_imgs:
                    media_ok = False
                    media_errors.append(
                        f"CSS/SVG-only mode selected but external image URLs found in {path}."
                    )
            else:
                # Check for broken local image paths (non-css_svg modes)
                broken_local = re.findall(
                    r'src=["\'](?!\s*https?://|/api/|data:)([^"\']+\.(jpg|jpeg|png|gif|webp))["\']',
                    content,
                    re.IGNORECASE,
                )
                if broken_local:
                    media_ok = False
                    for img_path, _ in broken_local[:3]:
                        media_errors.append(
                            f"Possible broken local image reference: {img_path}"
                        )

    # ── threshold checks ─────────────────────────────────────────────────────
    quality_ok = quality_score >= MIN_QUALITY_SCORE
    design_ok = design_score >= MIN_DESIGN_SCORE

    # Security score only enforced for projects with auth/backend
    security_relevant = project_type in {
        "fullstack-app", "dashboard", "api-service",
        "automation-bot-scaffold", "trading-bot-scaffold",
    } or auth_required
    security_ok = (not security_relevant) or (security_score >= MIN_SECURITY_SCORE)

    return {
        "qualityScore": quality_score,
        "designScore": design_score,
        "securityScore": security_score,
        "qualityErrors": quality_errors,
        "designErrors": design_errors,
        "securityErrors": security_errors,
        "mediaErrors": media_errors,
        "qualityOk": quality_ok,
        "designOk": design_ok,
        "securityOk": security_ok,
        "mediaOk": media_ok,
    }
