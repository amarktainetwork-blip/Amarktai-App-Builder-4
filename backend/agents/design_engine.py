"""
Unique design direction generator for Amarktai App Builder.

Creates a distinctive visual style for each generated project so that
outputs don't all look like the same generic Tailwind/shadcn template.

Usage::

    direction = create_design_direction(
        prompt="A SaaS for horse management",
        project_type="static-site",
        audience="equestrian professionals",
        tier="balanced",
    )

The returned dict is passed to the Coder agent as part of the shared context
so it can apply the style consistently across all generated files.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

# ── Design style catalog ─────────────────────────────────────────────────────

_DESIGN_STYLES: list[dict[str, Any]] = [
    {
        "name": "cinematic-dark-glass",
        "label": "Cinematic Dark Glass",
        "palette": {
            "background": "#080a10",
            "surface": "#111520",
            "border": "#ffffff1a",
            "accent": "#00d4ff",
            "text_primary": "#f0f4ff",
            "text_secondary": "#8a9bb5",
            "cta_bg": "#00d4ff",
            "cta_text": "#000c14",
        },
        "typography": {
            "heading": "'Space Grotesk', system-ui, sans-serif",
            "body": "'DM Sans', system-ui, sans-serif",
            "weight_heading": "900",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=space-grotesk:700,900|dm-sans:400,500&display=swap",
            "css_vars": "--font-heading: 'Space Grotesk', system-ui, sans-serif; --font-body: 'DM Sans', system-ui, sans-serif;",
        },
        "spacing": "generous",
        "layout_rhythm": "asymmetric_hero_left",
        "visual_motifs": "glassmorphism panels, subtle grain texture, blue neon glow",
        "media_direction": "cinematic widescreen hero images, dark with light foreground subjects",
        "motion": "smooth 300ms ease, parallax subtle",
        "mobile": "stacked, full-bleed sections",
        "tailwind_config": "dark mode, blue/cyan accent, backdrop-blur cards",
    },
    {
        "name": "editorial-luxury",
        "label": "Editorial Luxury",
        "palette": {
            "background": "#f9f6f0",
            "surface": "#ffffff",
            "border": "#e5ddd0",
            "accent": "#c8a96e",
            "text_primary": "#1a1610",
            "text_secondary": "#7a6f60",
            "cta_bg": "#1a1610",
            "cta_text": "#f9f6f0",
        },
        "typography": {
            "heading": "'Cormorant Garamond', Georgia, serif",
            "body": "'Lora', Georgia, serif",
            "weight_heading": "700",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=cormorant-garamond:400,600,700|lora:400,500&display=swap",
            "css_vars": "--font-heading: 'Cormorant Garamond', Georgia, serif; --font-body: 'Lora', Georgia, serif;",
        },
        "spacing": "spacious",
        "layout_rhythm": "magazine_columns",
        "visual_motifs": "thin borders, gold highlights, generous whitespace, typographic hierarchy",
        "media_direction": "high-end editorial photography, neutral tones, architectural shots",
        "motion": "gentle 200ms ease-out",
        "mobile": "single column, large typography",
        "tailwind_config": "light mode, amber/stone palette, serif headings via CDN font",
    },
    {
        "name": "fintech-dashboard",
        "label": "Fintech Dashboard",
        "palette": {
            "background": "#0a0e1a",
            "surface": "#111827",
            "border": "#1f2937",
            "accent": "#3b82f6",
            "text_primary": "#f9fafb",
            "text_secondary": "#6b7280",
            "cta_bg": "#3b82f6",
            "cta_text": "#ffffff",
        },
        "typography": {
            "heading": "'IBM Plex Sans', system-ui, sans-serif",
            "body": "'DM Sans', system-ui, sans-serif",
            "weight_heading": "700",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=ibm-plex-sans:400,500,700|dm-sans:400,500&display=swap",
            "css_vars": "--font-heading: 'IBM Plex Sans', system-ui, sans-serif; --font-body: 'DM Sans', system-ui, sans-serif;",
        },
        "spacing": "compact",
        "layout_rhythm": "dashboard_grid",
        "visual_motifs": "data charts, progress bars, status badges, monospace labels",
        "media_direction": "abstract tech / circuit patterns, blue data visualizations",
        "motion": "150ms ease for interactions, no decorative animation",
        "mobile": "scrollable card stack",
        "tailwind_config": "dark mode, blue/gray palette, mono font for headings",
    },
    {
        "name": "neo-brutalist",
        "label": "Neo-Brutalist",
        "palette": {
            "background": "#ffffff",
            "surface": "#f5f5f5",
            "border": "#000000",
            "accent": "#ff3e00",
            "text_primary": "#000000",
            "text_secondary": "#333333",
            "cta_bg": "#ff3e00",
            "cta_text": "#ffffff",
        },
        "typography": {
            "heading": "'Space Grotesk', Impact, Arial Black, sans-serif",
            "body": "'Space Grotesk', Arial, sans-serif",
            "weight_heading": "900",
            "weight_body": "500",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=space-grotesk:500,700,900&display=swap",
            "css_vars": "--font-heading: 'Space Grotesk', Impact, Arial Black, sans-serif; --font-body: 'Space Grotesk', Arial, sans-serif;",
        },
        "spacing": "tight",
        "layout_rhythm": "chunky_blocks",
        "visual_motifs": "thick 2-4px black borders, offset shadows, raw grid, bold color blocks",
        "media_direction": "high contrast editorial, bold product shots",
        "motion": "none — brutalist sites avoid animation",
        "mobile": "stacked blocks, full-width",
        "tailwind_config": "light mode, red accent, ring-0, shadow-[4px_4px_0_#000]",
    },
    {
        "name": "futuristic-mesh",
        "label": "Futuristic Mesh Gradient",
        "palette": {
            "background": "#0d0d1a",
            "surface": "#131324",
            "border": "#2d2d5e",
            "accent": "#7c3aed",
            "text_primary": "#e8e8ff",
            "text_secondary": "#9999cc",
            "cta_bg": "#7c3aed",
            "cta_text": "#ffffff",
        },
        "typography": {
            "heading": "'Outfit', system-ui, sans-serif",
            "body": "'Outfit', system-ui, sans-serif",
            "weight_heading": "800",
            "weight_body": "300",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=outfit:300,400,700,800&display=swap",
            "css_vars": "--font-heading: 'Outfit', system-ui, sans-serif; --font-body: 'Outfit', system-ui, sans-serif;",
        },
        "spacing": "generous",
        "layout_rhythm": "centered_hero_gradient",
        "visual_motifs": "mesh gradient background, floating UI cards, glow effects, aurora colors",
        "media_direction": "abstract 3D renders, gradient orbs, neon-lit scenes",
        "motion": "smooth 400ms, subtle floating animations",
        "mobile": "centered stacked, glowing CTA",
        "tailwind_config": "dark mode, violet/purple palette, mesh gradient via inline style",
    },
    {
        "name": "premium-monochrome",
        "label": "Premium Monochrome",
        "palette": {
            "background": "#000000",
            "surface": "#111111",
            "border": "#222222",
            "accent": "#ffffff",
            "text_primary": "#ffffff",
            "text_secondary": "#888888",
            "cta_bg": "#ffffff",
            "cta_text": "#000000",
        },
        "typography": {
            "heading": "'Manrope', Helvetica Neue, Arial, sans-serif",
            "body": "'Manrope', Helvetica Neue, Arial, sans-serif",
            "weight_heading": "800",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=manrope:400,500,700,800&display=swap",
            "css_vars": "--font-heading: 'Manrope', Helvetica Neue, Arial, sans-serif; --font-body: 'Manrope', Helvetica Neue, Arial, sans-serif;",
        },
        "spacing": "generous",
        "layout_rhythm": "minimal_centered",
        "visual_motifs": "pure black/white, thin separators, oversized typography",
        "media_direction": "black & white photography, high contrast subjects",
        "motion": "200ms ease",
        "mobile": "full-bleed centered",
        "tailwind_config": "dark mode, zinc/neutral palette, no color accents",
    },
    {
        "name": "blueprint-lab",
        "label": "Blueprint Lab",
        "palette": {
            "background": "#001233",
            "surface": "#002366",
            "border": "#0066cc",
            "accent": "#00aaff",
            "text_primary": "#e0f0ff",
            "text_secondary": "#7db8e8",
            "cta_bg": "#00aaff",
            "cta_text": "#001233",
        },
        "typography": {
            "heading": "'JetBrains Mono', Consolas, monospace",
            "body": "'IBM Plex Mono', Consolas, monospace",
            "weight_heading": "700",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=jetbrains-mono:400,700|ibm-plex-mono:400&display=swap",
            "css_vars": "--font-heading: 'JetBrains Mono', Consolas, monospace; --font-body: 'IBM Plex Mono', Consolas, monospace;",
        },
        "spacing": "compact",
        "layout_rhythm": "technical_grid",
        "visual_motifs": "blueprint grid lines, technical annotations, circuit-like borders",
        "media_direction": "engineering blueprints, technical diagrams, dark blue backgrounds",
        "motion": "none — technical/analytical feel",
        "mobile": "scrollable table layout",
        "tailwind_config": "dark mode, blue/sky palette, grid background via CSS",
    },
    {
        "name": "organic-nature",
        "label": "Organic Nature-Inspired",
        "palette": {
            "background": "#f0f4e8",
            "surface": "#ffffff",
            "border": "#b8d4a0",
            "accent": "#3d8b37",
            "text_primary": "#1a2e0e",
            "text_secondary": "#4a6e3a",
            "cta_bg": "#3d8b37",
            "cta_text": "#ffffff",
        },
        "typography": {
            "heading": "'Lora', Georgia, serif",
            "body": "'Nunito Sans', system-ui, sans-serif",
            "weight_heading": "600",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=lora:400,500,600|nunito-sans:400,600&display=swap",
            "css_vars": "--font-heading: 'Lora', Georgia, serif; --font-body: 'Nunito Sans', system-ui, sans-serif;",
        },
        "spacing": "generous",
        "layout_rhythm": "flowing_sections",
        "visual_motifs": "leaf patterns, organic shapes, earthy textures, rounded cards",
        "media_direction": "nature photography, green landscapes, organic product shots",
        "motion": "smooth 400ms ease-in-out, gentle fade transitions",
        "mobile": "card-based, rounded corners",
        "tailwind_config": "light mode, green/emerald palette, rounded-2xl cards",
    },
    {
        "name": "luxury-black-gold",
        "label": "Luxury Black & Gold",
        "palette": {
            "background": "#0a0800",
            "surface": "#161200",
            "border": "#c8a96e44",
            "accent": "#c8a96e",
            "text_primary": "#f5e6c8",
            "text_secondary": "#9a8060",
            "cta_bg": "#c8a96e",
            "cta_text": "#0a0800",
        },
        "typography": {
            "heading": "'Playfair Display', Didot, Georgia, serif",
            "body": "'Cormorant Garamond', Georgia, serif",
            "weight_heading": "600",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=playfair-display:400,600,700|cormorant-garamond:400,500&display=swap",
            "css_vars": "--font-heading: 'Playfair Display', Didot, Georgia, serif; --font-body: 'Cormorant Garamond', Georgia, serif;",
        },
        "spacing": "spacious",
        "layout_rhythm": "centered_luxury",
        "visual_motifs": "gold ornamental dividers, dark velvet background, serif headings",
        "media_direction": "luxury product photography, gold accents, dark dramatic lighting",
        "motion": "slow 600ms ease, luxurious",
        "mobile": "centered, full-bleed gold accents",
        "tailwind_config": "dark mode, amber/yellow palette, serif CDN fonts",
    },
    {
        "name": "immersive-gradient-studio",
        "label": "Immersive Gradient Studio",
        "palette": {
            "background": "#0f0f23",
            "surface": "#1a1a3e",
            "border": "#3a3a6e",
            "accent": "#ff6b6b",
            "text_primary": "#ffffff",
            "text_secondary": "#a0a0cc",
            "cta_bg": "linear-gradient(135deg, #ff6b6b, #feca57)",
            "cta_text": "#000000",
        },
        "typography": {
            "heading": "'Syne', system-ui, sans-serif",
            "body": "'DM Sans', system-ui, sans-serif",
            "weight_heading": "800",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=syne:400,700,800|dm-sans:400,500&display=swap",
            "css_vars": "--font-heading: 'Syne', system-ui, sans-serif; --font-body: 'DM Sans', system-ui, sans-serif;",
        },
        "spacing": "generous",
        "layout_rhythm": "full_bleed_sections",
        "visual_motifs": "bold gradient sections, color-shifting backgrounds, neon accents",
        "media_direction": "colorful abstract art, vibrant product photography",
        "motion": "gradient animation, smooth 500ms transitions",
        "mobile": "full-screen sections, swipe-like feel",
        "tailwind_config": "dark mode, rose/yellow gradient, large section breaks",
    },
    {
        "name": "premium-startup-minimal",
        "label": "Premium Startup Minimal",
        "palette": {
            "background": "#fafafa",
            "surface": "#ffffff",
            "border": "#e5e7eb",
            "accent": "#4f46e5",
            "text_primary": "#111827",
            "text_secondary": "#6b7280",
            "cta_bg": "#4f46e5",
            "cta_text": "#ffffff",
        },
        "typography": {
            "heading": "'Inter', system-ui, sans-serif",
            "body": "'Inter', system-ui, sans-serif",
            "weight_heading": "700",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=inter:400,500,600,700&display=swap",
            "css_vars": "--font-heading: 'Inter', system-ui, sans-serif; --font-body: 'Inter', system-ui, sans-serif;",
        },
        "spacing": "spacious",
        "layout_rhythm": "centered_minimal",
        "visual_motifs": "clean white cards, subtle shadows, indigo accent, generous whitespace",
        "media_direction": "clean product screenshots, team photos, simple illustrations",
        "motion": "150ms ease hover states",
        "mobile": "single column, card stack",
        "tailwind_config": "light mode, indigo/purple palette, shadow-sm cards",
    },
    {
        "name": "industrial-command",
        "label": "Industrial Command Center",
        "palette": {
            "background": "#111111",
            "surface": "#1c1c1c",
            "border": "#333333",
            "accent": "#f97316",
            "text_primary": "#e5e5e5",
            "text_secondary": "#888888",
            "cta_bg": "#f97316",
            "cta_text": "#000000",
        },
        "typography": {
            "heading": "'Barlow Condensed', Impact, Arial, sans-serif",
            "body": "'Barlow', system-ui, sans-serif",
            "weight_heading": "700",
            "weight_body": "400",
        },
        "font_import": {
            "link_href": "https://fonts.bunny.net/css?family=barlow-condensed:400,700|barlow:400,500&display=swap",
            "css_vars": "--font-heading: 'Barlow Condensed', Impact, Arial, sans-serif; --font-body: 'Barlow', system-ui, sans-serif;",
        },
        "spacing": "compact",
        "layout_rhythm": "dense_grid",
        "visual_motifs": "dark metal texture, orange warning accents, bold condensed typography",
        "media_direction": "industrial machinery, heavy equipment, high-contrast dark photos",
        "motion": "fast 100ms hover, no decorative animation",
        "mobile": "compact cards, dense information",
        "tailwind_config": "dark mode, orange/stone palette, condensed font via CDN",
    },
]

# ── Industry-specific media briefs ────────────────────────────────────────────

# Maps industry keyword → (style_name, media_brief)
# media_brief describes what image subjects to use and fallback strategy
_INDUSTRY_MEDIA_BRIEFS: list[tuple[list[str], str, str]] = [
    (
        ["bmw", "mercedes", "audi", "lexus", "porsche", "automotive", "dealership",
         "car dealer", "used car", "luxury car", "vehicle", "automobile"],
        "premium-monochrome",
        "BMW vehicles, luxury cars, automotive photography, showroom shots, cinematic wide shots "
        "of vehicles. Dark dramatic lighting. Use CSS gradient fallbacks (black/charcoal backgrounds "
        "with white text) if specific car images unavailable. Never use non-automotive images.",
    ),
    (
        ["lingerie", "underwear", "intimate", "bra", "nightwear", "sleepwear"],
        "editorial-luxury",
        "Tasteful fashion editorial photography, abstract fabric textures, soft neutral backgrounds, "
        "studio product shots. Use subtle CSS gradient and texture fallbacks. "
        "Keep imagery safe, professional, and brand-appropriate.",
    ),
    (
        ["fashion", "clothing", "boutique", "apparel", "dress", "style", "couture"],
        "editorial-luxury",
        "Fashion editorial photography, model shots, product flatlay, studio imagery. "
        "Clean white/neutral backgrounds. Use CSS fade gradients as fallback.",
    ),
    (
        ["restaurant", "cafe", "food", "cuisine", "dining", "menu", "chef", "bakery"],
        "immersive-gradient-studio",
        "Food photography, restaurant ambiance, dish close-ups, kitchen shots. "
        "Warm color tones. Use CSS warm gradient fallbacks (amber/gold tones) if images unavailable.",
    ),
    (
        ["hotel", "resort", "hospitality", "spa", "retreat", "accommodation"],
        "luxury-black-gold",
        "Luxury hotel rooms, resort landscapes, spa environments, architectural photography. "
        "Use CSS dark/gold gradient fallbacks for premium feel.",
    ),
    (
        ["gym", "fitness", "sport", "workout", "training", "health", "wellness"],
        "industrial-command",
        "Fitness/gym photography, athletes in action, sports equipment. "
        "High-energy, high-contrast imagery. Use dark CSS gradient fallbacks.",
    ),
    (
        ["real estate", "property", "homes", "apartment", "architect", "interior"],
        "premium-startup-minimal",
        "Real estate photography, interior shots, architectural exteriors, modern living spaces. "
        "Clean, bright imagery. Use neutral CSS gradient fallbacks.",
    ),
    (
        ["tech", "software", "saas", "startup", "product", "app launch"],
        "premium-startup-minimal",
        "Product UI screenshots, dashboard mockups, device frames, abstract tech illustrations. "
        "Clean isometric graphics or CSS gradient backgrounds with UI card overlays.",
    ),
    (
        ["nature", "eco", "organic", "plant", "garden", "farm", "green", "sustainable"],
        "organic-nature",
        "Nature photography, green landscapes, organic product shots, plant close-ups. "
        "Use earth-tone CSS gradient fallbacks (green/sage tones).",
    ),
    (
        ["finance", "fintech", "bank", "payment", "trading", "crypto", "invest"],
        "fintech-dashboard",
        "Abstract data visualizations, blue circuit patterns, financial dashboards. "
        "Use CSS blue/dark gradient fallbacks with grid overlays.",
    ),
]

# ── Audience/context matchers ─────────────────────────────────────────────────

_STYLE_HINTS: list[tuple[list[str], str]] = [
    (["bmw", "mercedes", "audi", "lexus", "porsche", "automotive", "dealership",
      "car dealer", "used car", "luxury car", "automobile"], "premium-monochrome"),
    (["lingerie", "underwear", "intimate", "bra", "nightwear", "sleepwear"], "editorial-luxury"),
    (["fashion", "clothing", "boutique", "apparel", "dress", "couture"], "editorial-luxury"),
    (["finance", "fintech", "bank", "payment", "trading", "crypto", "invest"], "fintech-dashboard"),
    (["luxury", "premium", "high-end", "exclusive", "jewel", "gold"], "luxury-black-gold"),
    (["nature", "eco", "organic", "plant", "garden", "farm", "green", "sustainable"], "organic-nature"),
    (["horse", "equestrian", "stable"], "organic-nature"),
    (["restaurant", "cafe", "food", "cuisine", "dining", "menu", "chef", "bakery"], "immersive-gradient-studio"),
    (["hotel", "resort", "hospitality", "spa", "retreat"], "luxury-black-gold"),
    (["gym", "fitness", "sport", "workout", "training"], "industrial-command"),
    (["saas", "startup", "product", "app launch", "launch"], "premium-startup-minimal"),
    (["dashboard", "admin", "analytics", "data", "reporting", "metrics"], "fintech-dashboard"),
    (["api", "backend", "developer", "technical", "engineering", "code"], "blueprint-lab"),
    (["bot", "automation", "monitor"], "industrial-command"),
    (["cinema", "film", "movie", "media", "streaming", "video"], "cinematic-dark-glass"),
    (["art", "design", "creative", "portfolio", "studio", "agency"], "immersive-gradient-studio"),
    (["magazine", "news", "editorial", "blog", "publishing"], "editorial-luxury"),
    (["minimal", "clean", "simple", "white", "professional"], "premium-monochrome"),
]


def _select_style_name(
    prompt: str,
    project_type: str,
    audience: str,
    tier: str,
    recent_signatures: list[dict] | None = None,
) -> str:
    """Select a design style name based on project context.

    Uses a deterministic hash so the same prompt always gets the same style,
    but the style varies meaningfully across different prompts.

    Applies a design diversity penalty: if the candidate style was used in any
    of the recent_signatures, it falls back to the next-best alternative.
    """
    combined = f"{prompt} {project_type} {audience}".lower()

    # Collect recently used style names to penalize
    recent_style_names: set[str] = set()
    if recent_signatures:
        for sig in recent_signatures:
            sn = sig.get("styleName", "")
            if sn:
                recent_style_names.add(sn)

    # Build candidate from keyword hints
    keyword_candidate: str | None = None
    for keywords, style_name in _STYLE_HINTS:
        if any(kw in combined for kw in keywords):
            keyword_candidate = style_name
            break

    # If keyword candidate not recently used, use it
    if keyword_candidate and keyword_candidate not in recent_style_names:
        return keyword_candidate

    # Deterministic hash-based selection with diversity fallback
    h = int(hashlib.sha256(combined.encode()).hexdigest(), 16)
    n = len(_DESIGN_STYLES)

    # Try up to n alternatives to find one not recently used
    for offset in range(n):
        style = _DESIGN_STYLES[(h + offset) % n]
        if style["name"] not in recent_style_names:
            return style["name"]

    # All styles recently used (very unlikely) — just use hash fallback
    return _DESIGN_STYLES[h % n]["name"]


def make_design_signature(style: dict) -> dict:
    """Create a compact design signature for diversity tracking."""
    palette = style.get("palette", {})
    # Create a stable hash of the palette
    palette_str = "|".join(
        f"{k}={v}" for k, v in sorted(palette.items())
    )
    palette_hash = hashlib.sha256(palette_str.encode()).hexdigest()[:8]
    typo = style.get("typography", {})
    font_pair = f"{typo.get('heading', '')}|{typo.get('body', '')}"

    return {
        "styleName": style.get("name", ""),
        "paletteHash": palette_hash,
        "fontPair": font_pair,
        "layoutArchetype": style.get("layout_rhythm", ""),
    }


def create_design_direction(
    prompt: str,
    project_type: str = "static-site",
    audience: str = "",
    tier: str = "balanced",
    recent_signatures: list[dict] | None = None,
) -> dict[str, Any]:
    """Generate a unique design direction for the given project context.

    Returns a design direction dict suitable for inclusion in the Coder's
    shared context. The Coder agent uses this to apply a consistent,
    unique visual style across all generated files.

    Args:
        prompt: The user's build prompt.
        project_type: Amarktai project type string.
        audience: Audience description from Scout (if available).
        tier: Quality tier ("cheap" | "balanced" | "premium").
        recent_signatures: Optional list of recent design signatures for
            diversity penalty (from project memory or user history).

    Returns:
        dict with: name, label, palette, typography, spacing, layout_rhythm,
        visual_motifs, media_direction, motion, mobile, tailwind_config,
        coder_instructions (a human-readable directive for the Coder agent),
        design_signature (compact signature for diversity tracking),
        industry_media_brief (subject-specific image guidance for Coder).
    """
    style_name = _select_style_name(prompt, project_type, audience, tier, recent_signatures)
    style = next(
        (s for s in _DESIGN_STYLES if s["name"] == style_name),
        _DESIGN_STYLES[0],
    )

    # Determine industry-specific media brief from prompt
    combined_lower = f"{prompt} {audience}".lower()
    industry_media_brief: str = ""
    for keywords, _, brief in _INDUSTRY_MEDIA_BRIEFS:
        if any(kw in combined_lower for kw in keywords):
            industry_media_brief = brief
            break
    if not industry_media_brief:
        industry_media_brief = style.get("media_direction", "")

    coder_instructions = (
        f"Apply the '{style['label']}' design style consistently across all files. "
        f"Palette: background={style['palette']['background']}, "
        f"accent={style['palette']['accent']}, "
        f"text={style['palette']['text_primary']}. "
        f"Typography: heading font = {style['typography']['heading']}, "
        f"body font = {style['typography']['body']}. "
        f"IMPORTANT — Load the web fonts using this <link> tag in every HTML <head>: "
        f'<link rel="stylesheet" href="{style["font_import"]["link_href"]}">. '
        f"Declare CSS custom properties in styles.css :root {{ "
        f"--font-heading: {style['typography']['heading']}; "
        f"--font-body: {style['typography']['body']}; "
        f"--color-bg: {style['palette']['background']}; "
        f"--color-primary: {style['palette']['accent']}; "
        f"--color-text: {style['palette']['text_primary']}; "
        f"--color-muted: {style['palette']['text_secondary']}; "
        f"}} "
        f"Use font-family: var(--font-heading) for all headings and var(--font-body) for body text. "
        f"Body font-size must be at least 16px; heading font-size at least 2rem. "
        f"Visual motifs: {style['visual_motifs']}. "
        f"Layout rhythm: {style['layout_rhythm']}. "
        f"Media/image direction: {industry_media_brief}. "
        f"Motion: {style['motion']}. "
        f"Mobile: {style['mobile']}. "
        f"Do NOT use generic purple/teal AI gradients or plain white Tailwind defaults. "
        f"Make the site feel custom and distinctive."
    )

    signature = make_design_signature(style)

    return {
        **style,
        "coder_instructions": coder_instructions,
        "tier": tier,
        "project_type": project_type,
        "design_signature": signature,
        "industry_media_brief": industry_media_brief,
    }


def get_available_styles() -> list[dict[str, str]]:
    """Return the list of available design styles (name + label only)."""
    return [{"name": s["name"], "label": s["label"]} for s in _DESIGN_STYLES]

