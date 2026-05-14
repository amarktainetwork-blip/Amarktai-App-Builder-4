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

from .template_policy import AUTOMOTIVE_TEMPLATE_FILES, is_automotive_prompt

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
# Detects problematic very low text opacity (< 0.2)
_LOW_OPACITY_TEXT = re.compile(
    r"color\s*:[^;]*rgba?\([^)]*,\s*0\.(?:0\d*|1\d*)\s*\)",
    re.IGNORECASE,
)
# Detects font-size explicitly set very small (< 12px) on body/p/li/span
# Uses re.DOTALL so it can match across lines; scans CSS for "font-size: Npx" globally
_TINY_FONT_SIZE = re.compile(
    r"font-size\s*:\s*([0-9]+)px",
    re.IGNORECASE,
)
# Detects CSS custom properties usage (design token proof)
_CSS_CUSTOM_PROPS = re.compile(
    r"var\(--[a-zA-Z]",
    re.IGNORECASE,
)
# Detects placeholder/not-found page content that should never appear in production
_PLACEHOLDER_PAGE_PAT = re.compile(
    r"\bcoming\s+soon\b|\bunder\s+construction\b|\bdetail\s+not\s+found\b"
    r"|\bpage\s+not\s+found\b|\bno\s+content\s+yet\b|\bpage\s+in\s+progress\b"
    r"|\bcontent\s+coming\b|\bplaceholder\s+page\b|\bwork\s+in\s+progress\b",
    re.IGNORECASE,
)

# ── Extended scoring helpers (Phase 3) ───────────────────────────────────────

# Conversion score patterns
_CONVERSION_CTA_PAT = re.compile(
    r'<(a|button)[^>]*>(?:[^<]{1,60})</(a|button)>',
    re.IGNORECASE | re.DOTALL,
)
_STRONG_CTA_VERBS = re.compile(
    r'\b(start|get started|sign up|try|book|schedule|buy|purchase|download|subscribe'
    r'|join|claim|unlock|access|request|contact|learn more|see how|discover|explore)\b',
    re.IGNORECASE,
)
_TRUST_SIGNALS = re.compile(
    r'trustpilot|review|testimonial|rating|star|verified|guarantee|secure|ssl|5\s*star'
    r'|client|customer|partner|case\s+stud|social\s+proof',
    re.IGNORECASE,
)
_VALUE_PROP = re.compile(
    r'<h[12][^>]*>[^<]{8,}(?:save|grow|increase|reduce|faster|easier|smarter|better|more)[^<]{0,60}</h[12]>',
    re.IGNORECASE | re.DOTALL,
)
_FORM_PAT = re.compile(r'<form\b', re.IGNORECASE)
_PRICING_PAT = re.compile(r'pricing|price|\$\d|\d+/mo|per month|per year', re.IGNORECASE)

# UX score patterns
_NAV_PAT = re.compile(r'<nav\b', re.IGNORECASE)
_SKIP_LINK_PAT = re.compile(r'skip\s+to\s+(main|content)', re.IGNORECASE)
_FOOTER_PAT = re.compile(r'<footer\b', re.IGNORECASE)
_BREADCRUMB_PAT = re.compile(r'breadcrumb|aria-label=["\']breadcrumb', re.IGNORECASE)
_LOADING_PAT = re.compile(r'loading|spinner|skeleton|placeholder', re.IGNORECASE)

# Accessibility score patterns
_ALT_TEXT_MISSING = re.compile(r'<img\b(?![^>]*\balt=["\'][^"\']{1,}["\'])', re.IGNORECASE)
_IMG_PAT = re.compile(r'<img\b', re.IGNORECASE)
_ARIA_PAT = re.compile(r'\baria-(?:label|labelledby|describedby|role|hidden)\b', re.IGNORECASE)
_LANG_PAT = re.compile(r'<html[^>]+lang=["\'][a-z]{2}', re.IGNORECASE)
_HEADING_H1_PAT = re.compile(r'<h1\b', re.IGNORECASE)
_BUTTON_ARIA = re.compile(r'<button[^>]*(?:aria-label|title)=["\'][^"\']+["\']', re.IGNORECASE)
_FOCUS_VISIBLE = re.compile(r':focus(?:-visible)?', re.IGNORECASE)
_CONTRAST_DARK_ON_LIGHT = re.compile(
    r'(?:color\s*:\s*#(?:000|111|222|333|1a|2a)|color\s*:\s*black|color\s*:\s*rgb\s*\(\s*0)',
    re.IGNORECASE,
)

# SEO score patterns
_META_DESCRIPTION = re.compile(r'<meta[^>]+name=["\']description["\']', re.IGNORECASE)
_META_OG = re.compile(r'<meta[^>]+property=["\']og:', re.IGNORECASE)
_CANONICAL_PAT = re.compile(r'<link[^>]+rel=["\']canonical["\']', re.IGNORECASE)
_TITLE_PAT = re.compile(r'<title[^>]*>[^<]{5,}', re.IGNORECASE)
_HEADING_HIERARCHY = re.compile(r'<h[1-6]\b', re.IGNORECASE)
_STRUCTURED_DATA = re.compile(r'application/ld\+json|schema\.org', re.IGNORECASE)
_ROBOTS_PAT = re.compile(r'<meta[^>]+name=["\']robots["\']', re.IGNORECASE)
_SITEMAP_PAT = re.compile(r'sitemap\.xml', re.IGNORECASE)

# Responsiveness score patterns
_VIEWPORT_META = re.compile(
    r'<meta[^>]+name=["\']viewport["\'][^>]*content=["\'][^"\']*width=device-width',
    re.IGNORECASE,
)
_MEDIA_QUERY_PAT = re.compile(r'@media\s*\(', re.IGNORECASE)
_FLUID_UNITS = re.compile(r'\b(?:vw|vh|vmin|vmax|%|em|rem|fr)\b', re.IGNORECASE)
_GRID_FLEX_PAT = re.compile(r'display\s*:\s*(?:grid|flex)\b', re.IGNORECASE)
_MIN_MAX_WIDTH = re.compile(r'(?:min|max)-width\s*:', re.IGNORECASE)

# Performance score patterns
_INLINE_SCRIPT_PAT = re.compile(r'<script(?!\s+src=)[^>]*>\s*.{200,}', re.IGNORECASE | re.DOTALL)
_RENDER_BLOCKING = re.compile(
    r'<link[^>]+rel=["\']stylesheet["\'][^>]*>(?!\s*<link[^>]+rel=["\']preload)',
    re.IGNORECASE,
)
_PRELOAD_FONT = re.compile(r'<link[^>]+rel=["\']preload["\'][^>]*as=["\']font', re.IGNORECASE)
_LAZY_LOAD = re.compile(r'loading=["\']lazy["\']', re.IGNORECASE)
_IMG_DIMENSIONS = re.compile(r'<img[^>]+(?:width|height)=["\']', re.IGNORECASE)
_DEFER_ASYNC_PAT = re.compile(r'<script[^>]+(?:defer|async)\b', re.IGNORECASE)

def _score_conversion(html: str, css: str) -> tuple[int, list[str]]:
    """Score conversion potential (0-100)."""
    score = 60  # baseline
    errors: list[str] = []

    # Strong CTA verbs in buttons/links
    ctas = _CONVERSION_CTA_PAT.findall(html)
    cta_text = " ".join(c[0] if isinstance(c, tuple) else c for c in ctas)
    if _STRONG_CTA_VERBS.search(html):
        score += 15
    else:
        errors.append("No strong action-verb CTAs found (use 'Start', 'Get started', 'Book', etc.).")

    # Trust signals
    if _TRUST_SIGNALS.search(html):
        score += 10
    else:
        errors.append("No trust signals detected (add testimonials, ratings, or social proof).")

    # Form presence (lead capture)
    if _FORM_PAT.search(html):
        score += 10
    else:
        errors.append("No lead-capture form detected (add a contact, signup, or waitlist form).")

    # Pricing information
    if _PRICING_PAT.search(html):
        score += 5

    return min(100, max(0, score)), errors


def _score_ux(html: str, css: str) -> tuple[int, list[str]]:
    """Score UX quality (0-100)."""
    score = 60
    errors: list[str] = []

    if _NAV_PAT.search(html):
        score += 10
    else:
        errors.append("No <nav> element found. Navigation is required for good UX.")

    if _FOOTER_PAT.search(html):
        score += 5
    else:
        errors.append("No <footer> found. Footer with links improves site completion.")

    if _SKIP_LINK_PAT.search(html):
        score += 5
    else:
        errors.append("No skip-to-content link found. Add for keyboard users.")

    if _RESPONSIVE_PATTERNS.search(css + html):
        score += 10
    else:
        errors.append("No responsive layout detected. Mobile UX will suffer.")

    if _GRID_FLEX_PAT.search(css):
        score += 10
    else:
        errors.append("No CSS grid/flexbox layout found. Use modern layout for better UX.")

    return min(100, max(0, score)), errors


def _score_accessibility(html: str, css: str) -> tuple[int, list[str]]:
    """
    Score accessibility (0-100) — Phase 2B enhanced axe-core-like static analysis.
    
    Checks: lang, headings, alt text, ARIA, focus states, skip links,
    landmarks, form labels, button semantics, reduced motion, tabindex abuse.
    """
    score = 45  # Base (lower — must earn points)
    errors: list[str] = []

    # ── Language ──────────────────────────────────────────────────────────────
    if _LANG_PAT.search(html):
        score += 10
    else:
        errors.append("Missing lang attribute on <html> element (e.g. lang=\"en\"). WCAG 3.1.1")

    # ── Heading structure ─────────────────────────────────────────────────────
    if _HEADING_H1_PAT.search(html):
        score += 5
    else:
        errors.append("No <h1> heading found. Every page needs exactly one <h1>. WCAG 1.3.1")

    # Check for multiple h1s (bad practice)
    h1_count = len(re.findall(r'<h1\b', html, re.IGNORECASE))
    if h1_count > 1:
        errors.append(f"Multiple <h1> tags found ({h1_count}). Use only one <h1> per page.")
        score -= 5

    # ── Image alt text ────────────────────────────────────────────────────────
    imgs = _IMG_PAT.findall(html)
    missing_alt = _ALT_TEXT_MISSING.findall(html)
    if imgs and missing_alt:
        penalty = min(20, len(missing_alt) * 5)
        score -= penalty
        errors.append(
            f"{len(missing_alt)} image(s) missing alt text. WCAG 1.1.1. "
            "Add descriptive alt text or alt=\"\" for decorative images."
        )
    elif imgs:
        score += 10  # All images have alt text

    # ── ARIA attributes ───────────────────────────────────────────────────────
    if _ARIA_PAT.search(html):
        score += 8
    else:
        errors.append(
            "No ARIA attributes found. Add aria-label/aria-describedby for interactive elements. WCAG 4.1.2"
        )

    # ── Focus states ──────────────────────────────────────────────────────────
    if _FOCUS_VISIBLE.search(css):
        score += 7
    else:
        errors.append(
            "No :focus-visible CSS found. Add visible focus styles for keyboard navigation. WCAG 2.4.7"
        )

    # ── Skip navigation link ──────────────────────────────────────────────────
    if _SKIP_LINK_PAT.search(html):
        score += 5
    else:
        errors.append(
            "No skip-to-main-content link found. Add for keyboard users. WCAG 2.4.1"
        )

    # ── Landmark regions ──────────────────────────────────────────────────────
    has_main = bool(re.search(r'<main\b', html, re.IGNORECASE))
    has_nav = bool(re.search(r'<nav\b', html, re.IGNORECASE))
    has_header = bool(re.search(r'<header\b', html, re.IGNORECASE))
    has_footer = bool(re.search(r'<footer\b', html, re.IGNORECASE))
    landmark_count = sum([has_main, has_nav, has_header, has_footer])
    if landmark_count >= 3:
        score += 5
    elif landmark_count >= 1:
        score += 2
    else:
        errors.append(
            "No HTML5 landmark elements found (<main>, <nav>, <header>, <footer>). WCAG 1.3.6"
        )

    # ── Form label associations ───────────────────────────────────────────────
    inputs = re.findall(r'<input\b[^>]*>', html, re.IGNORECASE)
    labels = re.findall(r'<label\b', html, re.IGNORECASE)
    for_attrs = re.findall(r'<label\b[^>]+for=["\'][^"\']+["\']', html, re.IGNORECASE)
    aria_label_inputs = re.findall(r'<input\b[^>]*aria-label=["\'][^"\']+["\']', html, re.IGNORECASE)
    if inputs and not labels and not aria_label_inputs:
        errors.append(
            "Form inputs found but no <label> elements or aria-label attributes. WCAG 1.3.1"
        )
        score -= 5
    elif labels and not for_attrs and not aria_label_inputs:
        errors.append(
            "Labels found but missing 'for' attribute association. WCAG 1.3.1"
        )
    elif inputs and (labels or aria_label_inputs):
        score += 3  # Bonus for properly labelled forms

    # ── Button semantics ──────────────────────────────────────────────────────
    buttons = re.findall(r'<button\b[^>]*>', html, re.IGNORECASE)
    empty_buttons = re.findall(r'<button\b[^>]*>\s*</button>', html, re.IGNORECASE)
    if empty_buttons:
        errors.append(
            f"{len(empty_buttons)} empty <button> element(s) found. Add text or aria-label. WCAG 4.1.2"
        )
        score -= 3

    # ── Tabindex abuse ────────────────────────────────────────────────────────
    positive_tabindex = re.findall(r'tabindex=["\'][1-9][0-9]*["\']', html, re.IGNORECASE)
    if positive_tabindex:
        errors.append(
            f"{len(positive_tabindex)} element(s) with positive tabindex. Use tabindex=\"0\" instead. WCAG 2.4.3"
        )
        score -= 3

    # ── Reduced motion support ────────────────────────────────────────────────
    if re.search(r'prefers-reduced-motion', css, re.IGNORECASE):
        score += 5
    elif re.search(r'@keyframes|animation:|transition:', css, re.IGNORECASE):
        errors.append(
            "Animations found but no @media (prefers-reduced-motion) support. WCAG 2.3.3"
        )

    return min(100, max(0, score)), errors


def _score_seo(html: str) -> tuple[int, list[str]]:
    """
    Score SEO basics (0-100) — Phase 2B enhanced.
    
    Checks: title, meta description, OG tags, Twitter Card, canonical,
    heading hierarchy, structured data, image alt, robots meta, language.
    """
    score = 30  # Base (must earn points)
    errors: list[str] = []

    # ── Title tag ─────────────────────────────────────────────────────────────
    if _TITLE_PAT.search(html):
        # Check title length (optimal 30-60 chars)
        title_match = re.search(r'<title[^>]*>([^<]{5,})</title>', html, re.IGNORECASE)
        if title_match:
            title_len = len(title_match.group(1))
            if 30 <= title_len <= 60:
                score += 15
            elif title_len < 30:
                score += 10
                errors.append(
                    f"Title tag is too short ({title_len} chars). Aim for 30-60 characters."
                )
            else:
                score += 10
                errors.append(
                    f"Title tag may be too long ({title_len} chars). Keep under 60 characters."
                )
    else:
        errors.append("Missing or empty <title> tag. Critical for SEO.")

    # ── Meta description ──────────────────────────────────────────────────────
    if _META_DESCRIPTION.search(html):
        # Check description length
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{10,})["\']'
            r'|<meta[^>]+content=["\']([^"\']{10,})["\'][^>]+name=["\']description["\']',
            html, re.IGNORECASE
        )
        if desc_match:
            desc_text = desc_match.group(1) or desc_match.group(2) or ""
            desc_len = len(desc_text)
            if 120 <= desc_len <= 160:
                score += 15
            elif desc_len < 120:
                score += 10
                errors.append(
                    f"Meta description is short ({desc_len} chars). Aim for 120-160 characters."
                )
            else:
                score += 10
                errors.append(
                    f"Meta description may be too long ({desc_len} chars). Keep under 160 characters."
                )
        else:
            score += 12  # Has meta desc but couldn't parse length
    else:
        errors.append("Missing meta description tag. Add for search result snippets.")

    # ── Open Graph ────────────────────────────────────────────────────────────
    if _META_OG.search(html):
        score += 8
        # Check for og:image specifically
        if not re.search(r'property=["\']og:image["\']', html, re.IGNORECASE):
            errors.append("og:image missing from Open Graph tags. Required for social sharing.")
    else:
        errors.append("No Open Graph meta tags (og:title, og:description, og:image). Hurts social sharing.")

    # ── Twitter Card ──────────────────────────────────────────────────────────
    if re.search(r'<meta[^>]+name=["\']twitter:', html, re.IGNORECASE):
        score += 5
    else:
        errors.append("No Twitter Card meta tags found. Add for Twitter/X sharing previews.")

    # ── Canonical ─────────────────────────────────────────────────────────────
    if _CANONICAL_PAT.search(html):
        score += 5
    else:
        errors.append("No canonical link tag found. Add to prevent duplicate content issues.")

    # ── Heading hierarchy ─────────────────────────────────────────────────────
    headings = _HEADING_HIERARCHY.findall(html)
    heading_levels = sorted(set(int(re.search(r'\d', h).group()) for h in headings if re.search(r'\d', h)))
    if len(headings) >= 3:
        score += 10
        if 1 in heading_levels:
            pass  # Good
        else:
            errors.append("No h1 in heading hierarchy. Heading structure should start with h1.")
    elif headings:
        score += 5
    else:
        errors.append("No semantic heading hierarchy (h1-h6) found. Critical for SEO structure.")

    # Check for skipped heading levels (e.g. h1 → h3, skipping h2)
    for i in range(len(heading_levels) - 1):
        if heading_levels[i + 1] - heading_levels[i] > 1:
            errors.append(
                f"Heading hierarchy skips from h{heading_levels[i]} to h{heading_levels[i+1]}. "
                "Use consecutive heading levels."
            )
            score -= 2
            break

    # ── Structured data ───────────────────────────────────────────────────────
    if _STRUCTURED_DATA.search(html):
        score += 5
    else:
        errors.append("No structured data (JSON-LD/Schema.org) found. Add for rich search results.")

    # ── Image alt text (SEO angle) ────────────────────────────────────────────
    imgs_in_html = _IMG_PAT.findall(html)
    if imgs_in_html:
        missing_alt_for_seo = _ALT_TEXT_MISSING.findall(html)
        if missing_alt_for_seo:
            errors.append(
                f"{len(missing_alt_for_seo)} image(s) missing alt text. "
                "Alt text is used by search engines for image indexing."
            )
            score -= min(10, len(missing_alt_for_seo) * 3)
        else:
            score += 3  # All images have alt

    # ── Language attribute (SEO angle) ───────────────────────────────────────
    if _LANG_PAT.search(html):
        score += 4
    else:
        errors.append("Missing lang attribute on <html>. Helps search engines identify language.")

    return min(100, max(0, score)), errors


def _score_responsiveness(html: str, css: str) -> tuple[int, list[str]]:
    """Score responsiveness (0-100)."""
    score = 40
    errors: list[str] = []

    if _VIEWPORT_META.search(html):
        score += 20
    else:
        errors.append("Missing viewport meta tag (required for mobile scaling).")

    mq_count = len(_MEDIA_QUERY_PAT.findall(css))
    if mq_count >= 3:
        score += 20
    elif mq_count >= 1:
        score += 10
        errors.append(f"Only {mq_count} media query/queries found. Add breakpoints for mobile, tablet, and desktop.")
    else:
        errors.append("No CSS media queries found. Add responsive breakpoints.")

    if _GRID_FLEX_PAT.search(css):
        score += 10
    else:
        errors.append("No CSS grid or flexbox layout detected.")

    if _FLUID_UNITS.search(css):
        score += 10
    else:
        errors.append("No fluid units (%, em, rem, vw) found in CSS.")

    return min(100, max(0, score)), errors


def _score_performance(html: str, css: str) -> tuple[int, list[str]]:
    """Score performance hints (0-100)."""
    score = 60
    errors: list[str] = []

    if _DEFER_ASYNC_PAT.search(html):
        score += 15
    else:
        if re.search(r'<script\b(?!.*(?:src\s*=|type\s*=\s*["\'](?:application/ld\+json)))', html, re.IGNORECASE):
            errors.append("Scripts are not using defer/async attribute (may block rendering).")

    if _LAZY_LOAD.search(html):
        score += 10
    elif _IMG_PAT.search(html):
        errors.append("Images don't use loading='lazy' attribute.")

    if _PRELOAD_FONT.search(html):
        score += 10
    elif re.search(r'fonts\.bunny\.net|fonts\.googleapis\.com', html, re.IGNORECASE):
        errors.append("Web fonts loaded but not preloaded (<link rel='preload' as='font'>).")
        score -= 5

    if _IMG_DIMENSIONS.search(html) or not _IMG_PAT.search(html):
        score += 5
    else:
        errors.append("Images lack explicit width/height attributes (causes layout shift).")

    return min(100, max(0, score)), errors


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
# Numeric page count from prompt: "6 pages", "6-page", "six page" etc.
_PAGE_COUNT_PAT = re.compile(
    r"\b((?:\d+|two|three|four|five|six|seven|eight|nine|ten))\s*[-–]?\s*page",
    re.IGNORECASE,
)
_WORD_TO_NUM = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _strip_html(content: str) -> str:
    return _WHITESPACE.sub(" ", _HTML_TAG.sub(" ", content)).strip()


def _word_count(content: str) -> int:
    text = _strip_html(content)
    return len(text.split())


def _count_sections(html_content: str) -> int:
    """Count distinct top-level section-like blocks."""
    return len(_SECTION_TAGS.findall(html_content))


def extract_requested_page_count(prompt: str) -> int:
    """Extract the numeric page count from a prompt string.

    Returns the integer page count if found, else 0.
    Examples:
      "Build a 6-page BMW website" → 6
      "5 page website" → 5
      "complete website with five pages" → 5
    """
    m = _PAGE_COUNT_PAT.search(prompt)
    if not m:
        return 0
    raw = m.group(1).lower().strip()
    if raw.isdigit():
        return int(raw)
    return _WORD_TO_NUM.get(raw, 0)


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

    # Check for CSS custom properties usage (design token contract)
    # Sites using a design_direction must declare --font-heading, --font-body etc. via var()
    if css.strip() and not _CSS_CUSTOM_PROPS.search(css):
        design -= 8
        design_errors.append(
            "CSS does not use custom properties (var(--font-heading) etc.). "
            "Declare :root CSS vars for fonts, colors, and spacing per the design direction."
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

    # ── Placeholder page check ────────────────────────────────────────────────
    # Penalize pages with "coming soon", "under construction", "detail not found" etc.
    for path, f in files_by_path.items():
        if path.endswith(".html"):
            page_content = f.get("content", "")
            if _PLACEHOLDER_PAGE_PAT.search(page_content):
                quality -= 10
                quality_errors.append(
                    f"Placeholder/not-found content detected in {path}. "
                    "Generate complete, real page content."
                )
                design -= 5
                design_errors.append(
                    f"Placeholder content detected in {path} — page is incomplete."
                )

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


# ── Phase 1F: Strict validation additions ─────────────────────────────────────

# Duplicate section detector: finds multiple identical section-class or id patterns
_DUPLICATE_ID_PAT = re.compile(
    r'id=["\']([a-zA-Z][a-zA-Z0-9_-]{2,})["\']',
    re.IGNORECASE,
)
# Broken anchor links: <a href="#anchor"> should have a matching id="anchor"
_ANCHOR_HREF_PAT = re.compile(r'href=["\']#([a-zA-Z][a-zA-Z0-9_-]+)["\']', re.IGNORECASE)
# Detects missing/wrong CSS font-family declaration when font var is used but not declared
_FONT_VAR_USAGE = re.compile(r'var\(--font-(?:heading|body)\)', re.IGNORECASE)
_FONT_VAR_DECL = re.compile(r'--font-(?:heading|body)\s*:', re.IGNORECASE)
# Detects inline style="" blocks with !important overrides (indicates CSS not working)
_IMPORTANT_INLINE = re.compile(r'style=["\'][^"\']*!important', re.IGNORECASE)
# Runtime-error markers that sometimes appear in generated code
_RUNTIME_ERROR_MARKERS = re.compile(
    r"undefined\s+is\s+not|cannot\s+read\s+property|TypeError:|ReferenceError:|"
    r"SyntaxError:|console\.error\(|throw\s+new\s+Error\(",
    re.IGNORECASE,
)


def _check_duplicate_ids(html: str) -> list[str]:
    """Return list of IDs that appear more than once in the HTML (duplicate section anchors)."""
    ids = _DUPLICATE_ID_PAT.findall(html)
    seen: dict[str, int] = {}
    for id_val in ids:
        seen[id_val] = seen.get(id_val, 0) + 1
    return [id_val for id_val, count in seen.items() if count > 1]


def _check_broken_anchors(html: str) -> list[str]:
    """Return list of #anchor hrefs that have no matching id in the HTML."""
    anchor_hrefs = set(_ANCHOR_HREF_PAT.findall(html))
    declared_ids = set(_DUPLICATE_ID_PAT.findall(html))
    return [a for a in anchor_hrefs if a not in declared_ids]


def _check_typography_integrity(html: str, css: str) -> list[str]:
    """Return errors when font vars are used but never declared (broken typography)."""
    issues: list[str] = []
    combined = html + "\n" + css
    if _FONT_VAR_USAGE.search(combined) and not _FONT_VAR_DECL.search(combined):
        issues.append(
            "CSS font variables (var(--font-heading) / var(--font-body)) are referenced "
            "but never declared in :root. Typography will be broken at runtime."
        )
    return issues

# ── Phase 1F: Minimum passing thresholds (also exported for tests/callers) ───
MIN_QUALITY_SCORE = 80
MIN_DESIGN_SCORE = 80
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
            automotive_prompt = is_automotive_prompt(prompt)
            page_keywords = {
                "about": "about.html",
                "service": "services.html",
                "pricing": "pricing.html",
                "contact": "contact.html",
                "team": "team.html",
                "portfolio": "portfolio.html",
                "blog": "blog.html",
            }
            if automotive_prompt:
                page_keywords.update({
                    "inventory": "inventory.html",
                    "vehicle": "vehicle-detail.html",
                    "financ": "finance.html",
                })
            for keyword, page_file in page_keywords.items():
                if keyword in prompt_lower and page_file not in files_by_path:
                    quality_score -= 8
                    quality_errors.append(
                        f"Prompt mentions '{keyword}' but {page_file} was not generated."
                    )
            if not automotive_prompt:
                contaminated = sorted(path for path in files_by_path if path in AUTOMOTIVE_TEMPLATE_FILES)
                if contaminated:
                    quality_score -= 50
                    quality_errors.append(
                        "Automotive starter pages appeared in a non-automotive build: "
                        + ", ".join(contaminated)
                    )

            # Strict page count enforcement: if prompt requests N pages, require N .html files
            html_files = [p for p in files_by_path if p.endswith(".html")]
            requested_page_count = extract_requested_page_count(prompt)
            if requested_page_count >= 3 and len(html_files) < requested_page_count:
                shortage = requested_page_count - len(html_files)
                penalty = min(40, shortage * 12)
                quality_score -= penalty
                quality_errors.append(
                    f"Prompt requested {requested_page_count} pages but only {len(html_files)} "
                    f"HTML file(s) generated ({', '.join(html_files[:5])}). "
                    f"All {requested_page_count} pages must be generated."
                )

            # If only index.html exists for a multi-page request (3+ pages), fail hard
            if requested_page_count >= 3 and len(html_files) == 1 and html_files[0] == "index.html":
                quality_score -= 25
                quality_errors.append(
                    f"Only index.html generated for a {requested_page_count}-page request. "
                    "Multi-page builds require all pages as separate .html files."
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

    # ── extended scoring (Phase 3) ────────────────────────────────────────────
    # Compute extended scores from HTML/CSS content of the primary page.
    _primary_html = (
        files_by_path.get("index.html", {}).get("content", "")
        or next(
            (f.get("content", "") for p, f in files_by_path.items() if p.endswith(".html")),
            "",
        )
    )
    _all_css = "\n".join(
        f.get("content", "")
        for p, f in files_by_path.items()
        if p.endswith(".css")
    )

    conversion_score, conversion_errors = _score_conversion(_primary_html, _all_css)
    ux_score, ux_errors = _score_ux(_primary_html, _all_css)
    accessibility_score, accessibility_errors = _score_accessibility(_primary_html, _all_css)
    seo_score, seo_errors = _score_seo(_primary_html)
    responsiveness_score, responsiveness_errors = _score_responsiveness(_primary_html, _all_css)
    performance_score, performance_errors = _score_performance(_primary_html, _all_css)

    # For non-HTML project types, set extended scores to neutral defaults.
    if project_type not in {"static-site", "multi-page-site", "pwa", "react-app", "next-app"}:
        conversion_score = 70
        ux_score = 70
        accessibility_score = 70
        seo_score = 70
        responsiveness_score = 70
        performance_score = 70
        conversion_errors = ux_errors = accessibility_errors = []
        seo_errors = responsiveness_errors = performance_errors = []

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

    # ── Phase 1F: Strict supplementary checks ────────────────────────────────
    # These run on top of existing scores and can force hard failure.
    _primary_html_for_strict = (
        files_by_path.get("index.html", {}).get("content", "")
        or next(
            (f.get("content", "") for p, f in files_by_path.items() if p.endswith(".html")),
            "",
        )
    )
    _all_css_for_strict = "\n".join(
        f.get("content", "")
        for p, f in files_by_path.items()
        if p.endswith(".css")
    )

    # 1. Duplicate section/ID check
    dup_ids = _check_duplicate_ids(_primary_html_for_strict)
    if dup_ids:
        penalty = min(20, len(dup_ids) * 5)
        design_score -= penalty
        design_errors.append(
            f"Duplicate HTML IDs detected ({', '.join(dup_ids[:5])}). "
            "Sections must have unique IDs."
        )

    # 2. Broken anchor link check
    broken_anchors = _check_broken_anchors(_primary_html_for_strict)
    if broken_anchors:
        penalty = min(15, len(broken_anchors) * 5)
        quality_score -= penalty
        quality_errors.append(
            f"Broken anchor links detected (#{', #'.join(broken_anchors[:5])}). "
            "Every href='#anchor' must have a matching id='anchor' on the page."
        )

    # 3. Typography integrity check
    typo_issues = _check_typography_integrity(_primary_html_for_strict, _all_css_for_strict)
    if typo_issues:
        design_score -= 20
        design_errors.extend(typo_issues)
        design_ok = False  # Typography failure is a hard block

    # 4. Runtime error markers in JS files
    js_content = "\n".join(
        f.get("content", "")
        for p, f in files_by_path.items()
        if p.endswith((".js", ".jsx", ".ts", ".tsx"))
    )
    if _RUNTIME_ERROR_MARKERS.search(js_content):
        quality_score -= 10
        quality_errors.append(
            "Possible runtime error markers found in JavaScript files. "
            "Review and remove error conditions before shipping."
        )

    # Re-apply thresholds after Phase 1F checks
    quality_ok = quality_score >= MIN_QUALITY_SCORE and quality_ok
    design_ok = design_score >= MIN_DESIGN_SCORE and design_ok

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
        # Extended scores (Phase 3)
        "conversionScore": conversion_score,
        "uxScore": ux_score,
        "accessibilityScore": accessibility_score,
        "seoScore": seo_score,
        "responsivenessScore": responsiveness_score,
        "performanceScore": performance_score,
        "conversionErrors": conversion_errors,
        "uxErrors": ux_errors,
        "accessibilityErrors": accessibility_errors,
        "seoErrors": seo_errors,
        "responsivenessErrors": responsiveness_errors,
        "performanceErrors": performance_errors,
    }
