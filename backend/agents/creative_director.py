"""
Amarktai App Builder — Creative Director Agent (Phase 1D).

The Creative Director runs before the Coder and produces a mandatory design
blueprint that all downstream agents must honour.  Its purpose is to prevent
repetitive, generic designs by making an explicit, opinionated creative choice
for every project.

The blueprint is intentionally deterministic for a given prompt so that two
builds of the same project will receive the same creative direction (unless
diversity logic forces a style rotation).

Usage::

    from agents.creative_director import run_creative_director, DesignBlueprint

    blueprint = run_creative_director(
        prompt="A luxury property listings platform",
        mode="landing_page",
        audience="high-net-worth buyers",
        industry="Real Estate",
        tier="premium",
        design_direction={"name": "editorial-luxury", ...},
        previous_signatures=[],
    )
    # blueprint is a DesignBlueprint dataclass — use blueprint.to_dict() for JSON
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .design_engine import create_design_direction


# ── Section archetypes ────────────────────────────────────────────────────────

_SECTION_ARCHETYPES: dict[str, list[str]] = {
    "landing_page": [
        "cinematic_hero",          # Tension + vision above the fold
        "transformation_proof",    # Before/after or pain-to-outcome proof
        "capability_reveal_rail",  # Horizontal/vertical capability rail
        "immersive_media_scene",   # Local media assets/video/visual proof
        "runtime_evidence_strip",  # QA/media/PR metrics and artifacts
        "outcome_spotlight",       # Business outcome and trust
        "premium_cta_band",        # Focused conversion moment
        "conversion_climax",       # Final decisive CTA/form
        "footer_rich",            # Rich footer with links
    ],
    "website": [
        "split_hero",
        "about_story",
        "services_grid",
        "portfolio_masonry",
        "team_profiles",
        "contact_split",
        "footer_minimal",
    ],
    "pwa": [
        "app_hero",
        "feature_highlights",
        "install_prompt",
        "screenshots_carousel",
        "rating_badge",
        "download_cta",
        "footer_minimal",
    ],
    "dashboard": [
        "kpi_cards_row",
        "primary_chart",
        "data_table",
        "secondary_metrics",
        "activity_feed",
        "quick_actions_panel",
    ],
    "ecommerce": [
        "hero_promo_banner",
        "category_grid",
        "featured_products",
        "deal_countdown",
        "testimonials_strip",
        "newsletter_signup",
        "footer_rich",
    ],
    "portfolio": [
        "personal_hero",
        "work_grid",
        "about_split",
        "skills_list",
        "contact_minimal",
        "footer_minimal",
    ],
    "saas_dashboard": [
        "sidebar_nav",
        "stats_overview",
        "main_data_view",
        "notifications_panel",
        "settings_access",
    ],
    "default": [
        "hero_section",
        "features_section",
        "cta_section",
        "footer_section",
    ],
}


# ── Animation tone catalog ────────────────────────────────────────────────────

_ANIMATION_TONES: dict[str, dict] = {
    "editorial-luxury": {
        "tone": "elegant",
        "description": "Slow, deliberate transitions — 400–600ms ease-in-out. "
                       "Elements reveal with subtle opacity + upward translate.",
        "keyframes": "fade-up 0.5s ease forwards",
        "hover": "transform: translateY(-3px); box-shadow: 0 12px 40px rgba(0,0,0,0.08)",
    },
    "cinematic-dark-glass": {
        "tone": "cinematic",
        "description": "Smooth 300ms transitions with parallax hints. "
                       "Glassmorphism panels slide in from below.",
        "keyframes": "slide-up 0.35s cubic-bezier(0.22,0.61,0.36,1) forwards",
        "hover": "backdrop-filter: blur(12px) saturate(1.2)",
    },
    "bold-tech": {
        "tone": "snappy",
        "description": "Fast 200ms micro-interactions. Elements pop into place. "
                       "CTAs scale slightly on hover.",
        "keyframes": "pop-in 0.2s cubic-bezier(0.34,1.56,0.64,1) forwards",
        "hover": "transform: scale(1.03)",
    },
    "default": {
        "tone": "neutral",
        "description": "Standard 250ms ease transitions.",
        "keyframes": "fade-in 0.25s ease forwards",
        "hover": "opacity: 0.9",
    },
}


# ── Blueprint data class ──────────────────────────────────────────────────────

@dataclass
class DesignBlueprint:
    """The full creative direction for a project build.

    Attributes
    ----------
    style_name:
        Identifier for the chosen design style (e.g. ``"cinematic-dark-glass"``).
    style_label:
        Human-readable label for UI display.
    layout_direction:
        High-level layout strategy (e.g. ``"asymmetric_hero_left"``).
    typography_system:
        Dict with ``heading``, ``body``, ``weight_heading``, ``weight_body`` keys.
    spacing_rhythm:
        ``"generous"`` | ``"compact"`` | ``"balanced"``
    color_palette:
        Dict with semantic color keys (``background``, ``accent``, etc.)
    section_archetypes:
        Ordered list of section type identifiers for the Coder to implement.
    animation_tone:
        Dict describing animation philosophy and keyframe recipe.
    image_direction:
        Text description of image style for Pixabay search queries.
    component_consistency:
        Visual motifs that all components must share.
    font_import:
        Dict with ``link_href`` and ``css_vars`` for font loading.
    """
    style_name: str
    style_label: str
    layout_direction: str
    typography_system: dict = field(default_factory=dict)
    spacing_rhythm: str = "balanced"
    color_palette: dict = field(default_factory=dict)
    section_archetypes: list[str] = field(default_factory=list)
    animation_tone: dict = field(default_factory=dict)
    image_direction: str = ""
    component_consistency: str = ""
    font_import: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_block(self) -> str:
        """Render the blueprint as a structured text block for injection into agent prompts."""
        palette_lines = "\n".join(
            f"  --color-{k.replace('_', '-')}: {v};" for k, v in self.color_palette.items()
        )
        font_vars = self.font_import.get("css_vars", "")
        sections = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(self.section_archetypes))

        return f"""CREATIVE DIRECTOR BLUEPRINT (MANDATORY — follow exactly):

Design Style: {self.style_label} ({self.style_name})
Layout Direction: {self.layout_direction}
Spacing Rhythm: {self.spacing_rhythm}

Color Palette (use as CSS custom properties):
{palette_lines}

Typography:
  Heading: {self.typography_system.get('heading', '')}
  Body: {self.typography_system.get('body', '')}
  Font CSS vars: {font_vars}

Section Order (implement ALL of these in sequence):
{sections}

Animation Tone: {self.animation_tone.get('description', '')}
  Keyframe recipe: {self.animation_tone.get('keyframes', '')}
  Hover effect: {self.animation_tone.get('hover', '')}

Image Direction: {self.image_direction}
Component Consistency: {self.component_consistency}

Cinematic Narrative:
  Flow: tension -> vision -> capability reveal -> proof -> outcome -> conversion
  Layout variety: alternate split, spotlight, editorial, rail, metrics strip, immersive media, and CTA band sections.
  Typography: oversized headlines, controlled line widths, strong contrast, and intentional whitespace.
  Required premium beats: cinematic hero, transformation/proof section, immersive media section, premium CTA band, conversion climax.

This blueprint is NON-NEGOTIABLE. Every file you write must honour these decisions.
"""


# ── Factory ───────────────────────────────────────────────────────────────────


def run_creative_director(
    prompt: str,
    mode: str = "landing_page",
    audience: str = "",
    industry: str = "",
    tier: str = "balanced",
    design_direction: dict | None = None,
    previous_signatures: list[dict] | None = None,
) -> DesignBlueprint:
    """Run the Creative Director and return a DesignBlueprint.

    Parameters
    ----------
    prompt:
        The original user build prompt.
    mode:
        Build mode (``"landing_page"``, ``"website"``, ``"dashboard"`` …).
    audience:
        Optional audience description for context.
    industry:
        Optional industry label for context.
    tier:
        Quality tier (``"cheap"`` | ``"balanced"`` | ``"premium"``).
    design_direction:
        Pre-computed design direction dict from ``design_engine``.
        If omitted, one is generated from the prompt.
    previous_signatures:
        List of previous design signature dicts (for diversity enforcement).

    Returns
    -------
    DesignBlueprint
        The creative blueprint for this project.
    """
    # Resolve design direction if not provided
    if not design_direction:
        project_type = _mode_to_project_type(mode)
        design_direction = create_design_direction(
            prompt=prompt,
            project_type=project_type,
            audience=audience,
            tier=tier,
            recent_signatures=previous_signatures or [],
        )

    style_name = design_direction.get("name", "default")
    style_label = design_direction.get("label", style_name.replace("-", " ").title())

    # Section archetypes — pick based on mode
    mode_key = _normalise_mode_key(mode)
    archetypes = _SECTION_ARCHETYPES.get(mode_key, _SECTION_ARCHETYPES["default"])

    # Animation tone — matched to style
    anim = _ANIMATION_TONES.get(style_name, _ANIMATION_TONES["default"])

    return DesignBlueprint(
        style_name=style_name,
        style_label=style_label,
        layout_direction=design_direction.get("layout_rhythm", "standard"),
        typography_system=design_direction.get("typography", {}),
        spacing_rhythm=design_direction.get("spacing", "balanced"),
        color_palette=design_direction.get("palette", {}),
        section_archetypes=archetypes,
        animation_tone=anim,
        image_direction=design_direction.get("media_direction", ""),
        component_consistency=design_direction.get("visual_motifs", ""),
        font_import=design_direction.get("font_import", {}),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mode_to_project_type(mode: str) -> str:
    """Convert build mode to project_type for design engine."""
    mapping = {
        "landing_page": "static-site",
        "website": "multi-page-site",
        "pwa": "pwa",
        "saas_dashboard": "dashboard",
        "dashboard": "dashboard",
        "api_backend": "api-service",
        "repo_upgrade": "repo-upgrade",
        "ecommerce": "static-site",
        "portfolio": "static-site",
        "admin_system": "dashboard",
        "full_stack": "fullstack-app",
        "web_app": "react-app",
    }
    return mapping.get(mode, "static-site")


def _normalise_mode_key(mode: str) -> str:
    """Normalise mode string to an archetype key."""
    normalised = mode.lower().replace("-", "_")
    if normalised in ("website", "multi_page_website", "multi_page_site"):
        return "website"
    if normalised in ("saas_dashboard", "dashboard", "admin_panel", "admin_system"):
        return "dashboard"
    if normalised == "full_stack":
        return "dashboard"
    if normalised in ("web_app", "react_app", "next_app"):
        return "landing_page"
    return normalised if normalised in _SECTION_ARCHETYPES else "landing_page"
