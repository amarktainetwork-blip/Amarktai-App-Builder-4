"""
Logo Agent for Amarktai App Builder.

Capabilities:
  - Use uploaded logo if selected (highest priority)
  - Generate deterministic SVG logo if no upload
  - Generate AI logo via GenX image model if configured and selected
  - Save generated logo to media library
  - Generate favicon data-URI and PWA icon notes
  - Apply logo consistently: nav/header, footer, favicon, PWA manifest

Input:
    {
        "businessName": str,
        "industry": str,
        "style": str,
        "designTokens": dict,
        "mediaSource": "auto|ai|pixabay|css_svg|uploaded",
        "uploadedLogoAssetId": str | None,
    }

Output:
    {
        "logoType": "uploaded|svg|ai_generated|fallback",
        "assetId": str | None,
        "files": [],
        "htmlSnippet": str,
        "cssSnippet": str,
        "faviconDataUri": str,
        "usageNotes": str,
        "fallbackUsed": bool,
        "warnings": [],
    }
"""
from __future__ import annotations

import hashlib
import html
import logging
import math
import re
import uuid
from typing import Any

logger = logging.getLogger("amarktai.logo_agent")

# ── SVG generation helpers ───────────────────────────────────────────────────

_SHAPE_PALETTE: list[tuple[str, str]] = [
    ("#00d4ff", "#080a10"),
    ("#c8a96e", "#1a1610"),
    ("#3b82f6", "#0a0e1a"),
    ("#ff3e00", "#ffffff"),
    ("#7c3aed", "#0d0d1a"),
    ("#ffffff", "#000000"),
    ("#00aaff", "#001233"),
    ("#2ecc71", "#0a1a0a"),
    ("#f59e0b", "#1a1200"),
]


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def _pick_colors(name: str, design_tokens: dict) -> tuple[str, str]:
    """Pick foreground and background colors from design tokens or palette."""
    bg = design_tokens.get("palette", {}).get("accent", "")
    fg = design_tokens.get("palette", {}).get("background", "")
    if bg and fg:
        return bg, fg
    h = _stable_hash(name)
    pair = _SHAPE_PALETTE[h % len(_SHAPE_PALETTE)]
    return pair


def _initials(name: str, max_chars: int = 2) -> str:
    """Extract initials from a business name."""
    words = re.sub(r"[^a-zA-Z0-9\s]", "", name).split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:max_chars].upper()
    return "".join(w[0] for w in words[:max_chars]).upper()


def _icon_shape(style: str, cx: float, cy: float, r: float, fg: str) -> str:
    """Return SVG shape markup for the logo icon."""
    s = style.lower()
    if "luxury" in s or "gold" in s or "editorial" in s:
        # Diamond shape
        pts = f"{cx},{cy - r} {cx + r},{cy} {cx},{cy + r} {cx - r},{cy}"
        return f'<polygon points="{pts}" fill="{fg}" opacity="0.9"/>'
    if "tech" in s or "blueprint" in s or "fintech" in s:
        # Hexagon
        pts = " ".join(
            f"{cx + r * math.cos(math.radians(60 * i - 90)):.1f},{cy + r * math.sin(math.radians(60 * i - 90)):.1f}"
            for i in range(6)
        )
        return f'<polygon points="{pts}" fill="{fg}" opacity="0.9"/>'
    if "brutalist" in s or "neo" in s:
        # Square rotated 45°
        pts = f"{cx},{cy - r} {cx + r},{cy} {cx},{cy + r} {cx - r},{cy}"
        return f'<rect x="{cx - r * 0.7:.1f}" y="{cy - r * 0.7:.1f}" width="{r * 1.4:.1f}" height="{r * 1.4:.1f}" fill="{fg}" opacity="0.9"/>'
    # Default: circle
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fg}" opacity="0.9"/>'


def generate_svg_logo(
    business_name: str,
    industry: str = "",
    style: str = "",
    design_tokens: dict | None = None,
    width: int = 200,
    height: int = 60,
) -> str:
    """Generate a deterministic SVG logo for the given business."""
    tokens = design_tokens or {}
    accent, bg = _pick_colors(business_name, tokens)
    initials = _initials(business_name)
    safe_name = html.escape(business_name[:30] or "Brand")

    # Font from design tokens or fallback
    font_family = (tokens.get("typography", {}).get("heading") or "'Space Grotesk', system-ui, sans-serif")

    icon_size = height * 0.65
    icon_cx = icon_size / 2 + 4
    icon_cy = height / 2
    icon_r = icon_size / 2

    icon_shape = _icon_shape(style, icon_cx, icon_cy, icon_r, "rgba(255,255,255,0.15)")
    text_x = icon_size + 12

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{safe_name} logo">
  <title>{safe_name}</title>
  <rect width="{width}" height="{height}" fill="{bg}" rx="6"/>
  {icon_shape}
  <text x="{icon_cx:.1f}" y="{icon_cy + 5:.1f}" text-anchor="middle" fill="{accent}"
    font-family="{font_family}" font-size="{icon_size * 0.45:.1f}" font-weight="700">{initials}</text>
  <text x="{text_x:.1f}" y="{height / 2 + 5:.1f}" fill="{accent}"
    font-family="{font_family}" font-size="{height * 0.32:.1f}" font-weight="700" letter-spacing="-0.5">{safe_name}</text>
</svg>"""
    return svg


def generate_favicon_svg(
    business_name: str,
    design_tokens: dict | None = None,
    size: int = 32,
) -> str:
    """Generate a small square SVG favicon."""
    tokens = design_tokens or {}
    accent, bg = _pick_colors(business_name, tokens)
    initials = _initials(business_name, max_chars=1)
    font_family = (tokens.get("typography", {}).get("heading") or "system-ui, sans-serif")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <rect width="{size}" height="{size}" fill="{bg}" rx="4"/>
  <text x="{size / 2:.1f}" y="{size * 0.68:.1f}" text-anchor="middle" fill="{accent}"
    font-family="{font_family}" font-size="{size * 0.52:.1f}" font-weight="700">{initials}</text>
</svg>"""
    return svg


# ── Brand color extraction ────────────────────────────────────────────────────

def extract_brand_colors(svg_content: str) -> dict[str, str]:
    """
    Extract brand colors from an SVG logo.
    
    Returns a dict with 'primary', 'accent', and 'background' color values.
    """
    colors: list[str] = re.findall(
        r'(?:fill|stroke|stop-color)\s*=\s*["\']?(#[0-9a-fA-F]{3,6}|rgb\([^)]+\))["\']?',
        svg_content,
    )
    unique_colors = list(dict.fromkeys(c for c in colors if c not in ("#fff", "#ffffff", "white", "none", "transparent")))

    result = {}
    if unique_colors:
        result["primary"] = unique_colors[0]
    if len(unique_colors) > 1:
        result["accent"] = unique_colors[1]
    if len(unique_colors) > 2:
        result["background"] = unique_colors[2]
    return result


def should_reuse_logo(memory: dict[str, Any], business_name: str) -> bool:
    """
    Check if a previously generated logo should be reused for this project.
    
    Returns True if memory contains a logo matching the business name.
    """
    if not memory:
        return False
    logo_mem = memory.get("logo", {})
    if not logo_mem:
        return False
    stored_name = logo_mem.get("businessName", logo_mem.get("business_name", ""))
    return bool(stored_name and stored_name.lower() == business_name.lower())


# ── Logo Agent main function ─────────────────────────────────────────────────

async def run_logo_agent(
    input_data: dict[str, Any],
    media_library_fn: Any | None = None,
    project_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the logo agent pipeline.

    Args:
        input_data: Logo agent input dict (see module docstring).
        media_library_fn: Optional async callable(asset_id) -> dict to look up
            uploaded asset metadata from the media library.
        project_memory: Optional project memory dict for logo persistence/reuse.

    Returns:
        Logo agent output dict (see module docstring).
    """
    business_name = input_data.get("businessName", "Brand")
    industry = input_data.get("industry", "")
    style = input_data.get("style", "")
    design_tokens = input_data.get("designTokens") or {}
    media_source = (input_data.get("mediaSource") or "auto").lower()
    uploaded_asset_id = input_data.get("uploadedLogoAssetId", "")

    warnings: list[str] = []
    files: list[dict] = []

    # ── Logo reuse from memory (brand consistency across iterations) ──────────
    if project_memory and should_reuse_logo(project_memory, business_name):
        logo_mem = project_memory.get("logo", {})
        cached_svg = logo_mem.get("svgContent", logo_mem.get("svg_content", ""))
        cached_asset_id = logo_mem.get("assetId", logo_mem.get("asset_id", ""))
        if cached_svg:
            logger.info("Reusing existing logo from project memory for '%s'", business_name)
            favicon_svg = generate_favicon_svg(business_name, design_tokens)
            return {
                "logoType": logo_mem.get("logoType", "svg"),
                "assetId": cached_asset_id,
                "files": [
                    {"filename": "logo.svg", "content": cached_svg, "media_type": "svg", "mime_type": "image/svg+xml"},
                    {"filename": "favicon.svg", "content": favicon_svg, "media_type": "svg", "mime_type": "image/svg+xml"},
                ],
                "htmlSnippet": logo_mem.get("htmlSnippet", _logo_html_snippet_svg(cached_svg, business_name)),
                "cssSnippet": logo_mem.get("cssSnippet", _logo_css_snippet_svg()),
                "faviconDataUri": _svg_data_uri(favicon_svg),
                "usageNotes": "Logo reused from project memory for brand consistency.",
                "fallbackUsed": False,
                "warnings": ["Logo reused from previous iteration to maintain brand consistency."],
                "svgContent": cached_svg,
                "faviconSvg": favicon_svg,
                "reusedFromMemory": True,
                "logoVersion": logo_mem.get("logoVersion", 1),
                "brandColors": logo_mem.get("brandColors", {}),
            }

    # ── Case 1: Use uploaded logo ─────────────────────────────────────────────
    if uploaded_asset_id and media_source in ("uploaded", "auto"):
        asset = None
        if media_library_fn:
            try:
                asset = await media_library_fn(uploaded_asset_id)
            except Exception as e:
                logger.warning("Could not look up uploaded logo asset %s: %s", uploaded_asset_id, e)

        if asset and asset.get("public_url"):
            url = asset["public_url"]
            mime = asset.get("mime_type", "image/png")
            html_snippet = _logo_html_snippet(url, business_name, is_img=True, mime=mime)
            css_snippet = _logo_css_snippet(url, is_img=True)
            favicon_svg = generate_favicon_svg(business_name, design_tokens)
            return {
                "logoType": "uploaded",
                "assetId": uploaded_asset_id,
                "files": files,
                "htmlSnippet": html_snippet,
                "cssSnippet": css_snippet,
                "faviconDataUri": _svg_data_uri(favicon_svg),
                "usageNotes": f"Using uploaded logo from media library (asset: {uploaded_asset_id}).",
                "fallbackUsed": False,
                "warnings": warnings,
            }
        else:
            warnings.append(
                f"Uploaded logo asset '{uploaded_asset_id}' not found in media library. "
                "Falling back to generated SVG logo."
            )

    # ── Case 2: AI logo generation ────────────────────────────────────────────
    if media_source == "ai":
        # We don't fake AI generation — if no media model available, use SVG
        warnings.append(
            "AI logo generation is not available in this build. "
            "A deterministic SVG logo has been created as a fallback."
        )
        # Fall through to SVG generation

    # ── Case 3: Generate deterministic SVG logo ───────────────────────────────
    svg_content = generate_svg_logo(
        business_name=business_name,
        industry=industry,
        style=style,
        design_tokens=design_tokens,
    )
    favicon_svg = generate_favicon_svg(business_name, design_tokens)
    asset_id = str(uuid.uuid4())

    files.append({
        "filename": "logo.svg",
        "content": svg_content,
        "media_type": "svg",
        "mime_type": "image/svg+xml",
    })
    files.append({
        "filename": "favicon.svg",
        "content": favicon_svg,
        "media_type": "svg",
        "mime_type": "image/svg+xml",
    })

    html_snippet = _logo_html_snippet_svg(svg_content, business_name)
    css_snippet = _logo_css_snippet_svg()
    favicon_data_uri = _svg_data_uri(favicon_svg)

    logo_type = "fallback" if (media_source == "ai" and warnings) else "svg"

    # Extract brand colors for memory persistence
    brand_colors = extract_brand_colors(svg_content)

    return {
        "logoType": logo_type,
        "assetId": asset_id,
        "files": files,
        "htmlSnippet": html_snippet,
        "cssSnippet": css_snippet,
        "faviconDataUri": favicon_data_uri,
        "usageNotes": (
            "A custom SVG logo has been generated based on your business name and design style. "
            "You can replace it by uploading your own logo in the Media Library."
        ),
        "fallbackUsed": media_source == "ai",
        "warnings": warnings,
        "svgContent": svg_content,
        "faviconSvg": favicon_svg,
        "reusedFromMemory": False,
        "logoVersion": 1,
        "brandColors": brand_colors,
    }


def _logo_html_snippet(url: str, name: str, is_img: bool = True, mime: str = "") -> str:
    safe = html.escape(name)
    if is_img and mime != "image/svg+xml":
        return f'<img src="{url}" alt="{safe} logo" class="site-logo" width="160" height="48" loading="eager">'
    # SVG embed via img tag works for most SVG files
    return f'<img src="{url}" alt="{safe} logo" class="site-logo" width="160" height="48" loading="eager">'


def _logo_css_snippet(url: str, is_img: bool = True) -> str:
    return """.site-logo {
  display: inline-block;
  max-height: 48px;
  width: auto;
  object-fit: contain;
}"""


def _logo_html_snippet_svg(svg_content: str, name: str) -> str:
    safe = html.escape(name)
    # Inline the SVG directly for best compatibility
    inline = svg_content.strip()
    return f'<a href="/" class="site-logo-link" aria-label="{safe} home">\n{inline}\n</a>'


def _logo_css_snippet_svg() -> str:
    return """.site-logo-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}
.site-logo-link svg {
  max-height: 48px;
  width: auto;
}"""


def _svg_data_uri(svg: str) -> str:
    import base64
    encoded = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def logo_agent_prompt_block(logo_result: dict) -> str:
    """Return a prompt block for the Coder agent with logo instructions."""
    if not logo_result:
        return ""

    logo_type = logo_result.get("logoType", "svg")
    html_snippet = logo_result.get("htmlSnippet", "")
    css_snippet = logo_result.get("cssSnippet", "")
    favicon_uri = logo_result.get("faviconDataUri", "")
    warnings = logo_result.get("warnings", [])

    parts = [
        "=== LOGO AGENT INSTRUCTIONS ===",
        f"Logo type: {logo_type}",
        "",
        "HTML: Use this logo HTML snippet in every page header/nav:",
        html_snippet,
        "",
        "CSS: Add this CSS for the logo:",
        css_snippet,
        "",
    ]
    if favicon_uri:
        parts += [
            "Favicon: Add this <link> tag in every HTML <head>:",
            f'<link rel="icon" type="image/svg+xml" href="{favicon_uri}">',
            "",
        ]
    if warnings:
        parts += ["Warnings:"] + [f"  - {w}" for w in warnings] + [""]

    parts.append(
        "Apply the logo consistently in: page header nav, footer, and <head> favicon. "
        "Do not omit the logo from any page."
    )
    return "\n".join(parts)
