"""
Amarktai Product Brain — Design DNA Engine.

Tracks previously used design choices across a project's build history
and applies a penalty system to force originality:

  - Repeated hero layouts are penalised.
  - Repeated palettes (by hash) are penalised.
  - Repeated card/section structures are penalised.
  - Repeated SaaS section types are penalised.

The engine reads from and writes to the project memory
(``memory["designSignatures"]`` and ``memory["design"]``), which is
persisted by the Project Memory Engine.

Usage::

    from agents.design_dna import (
        compute_repetition_score,
        get_originality_report,
        record_design_choice,
        build_diversity_context,
    )

    # Before selecting a design direction:
    ctx = build_diversity_context(memory)
    # Pass ctx["recent_signatures"] to create_design_direction()

    # After design is selected:
    memory = record_design_choice(memory, design_direction)
"""
from __future__ import annotations

import hashlib
from typing import Any

# Maximum design signatures to retain per project (matches project_memory._MAX_DESIGN_SIGNATURES)
_MAX_DESIGN_SIGNATURES = 20

# ── Layout archetype catalogue ────────────────────────────────────────────────

# Canonical set of layout archetypes (mirrors design_engine._DESIGN_STYLES layout_rhythm values)
_LAYOUT_ARCHETYPES: list[str] = [
    "asymmetric_hero_left",
    "magazine_columns",
    "dashboard_grid",
    "chunky_blocks",
    "centered_hero_gradient",
    "minimal_centered",
    "technical_grid",
    "flowing_sections",
    "centered_luxury",
    "full_bleed_sections",
    "centered_minimal",
    "dense_grid",
]

# Section archetypes that can be tracked for repetition
_SECTION_ARCHETYPES: list[str] = [
    "cinematic_hero",
    "luxury_showcase",
    "product_spotlight",
    "dashboard_preview",
    "workflow_timeline",
    "trust_bar",
    "comparison_grid",
    "pricing",
    "cta",
    "testimonials",
    "feature_cards",
    "gallery",
    "faq",
    "metrics",
    "integrations",
]

# Penalty weights — how much to discount a repeated element
_PALETTE_REPEAT_PENALTY = 0.6       # 60% penalty for same palette
_LAYOUT_REPEAT_PENALTY = 0.4        # 40% penalty for same layout
_FONT_PAIR_REPEAT_PENALTY = 0.3     # 30% penalty for same font pair
_SECTION_REPEAT_PENALTY = 0.2       # 20% per repeated section type


# ── Core penalty functions ────────────────────────────────────────────────────


def compute_repetition_score(
    candidate_signature: dict,
    recent_signatures: list[dict],
    window: int = 10,
) -> float:
    """Compute a 0-1 repetition score for a candidate design signature.

    0.0 = completely unique (no penalty)
    1.0 = completely repeated (maximum penalty)

    Only considers the most recent ``window`` entries for recency weighting.

    Args:
        candidate_signature: A design signature dict from make_design_signature().
        recent_signatures: List of past signatures (oldest first).
        window: How many recent entries to consider.

    Returns:
        float in [0.0, 1.0]
    """
    if not recent_signatures:
        return 0.0

    recent = recent_signatures[-window:]
    penalty = 0.0

    cand_style = candidate_signature.get("styleName", "")
    cand_palette = candidate_signature.get("paletteHash", "")
    cand_font = candidate_signature.get("fontPair", "")
    cand_layout = candidate_signature.get("layoutArchetype", "")

    for i, sig in enumerate(recent):
        # Recency weight: most recent entries penalised more
        recency_weight = (i + 1) / len(recent)  # 0..1, higher = more recent

        if sig.get("styleName") == cand_style:
            penalty += recency_weight * _PALETTE_REPEAT_PENALTY
        if sig.get("paletteHash") and sig["paletteHash"] == cand_palette:
            penalty += recency_weight * _PALETTE_REPEAT_PENALTY
        if sig.get("fontPair") and sig["fontPair"] == cand_font:
            penalty += recency_weight * _FONT_PAIR_REPEAT_PENALTY
        if sig.get("layoutArchetype") and sig["layoutArchetype"] == cand_layout:
            penalty += recency_weight * _LAYOUT_REPEAT_PENALTY

    # Normalise to [0, 1]
    return min(penalty, 1.0)


def get_overused_elements(recent_signatures: list[dict], window: int = 10) -> dict:
    """Return counts of overused design elements in recent history.

    Returns a dict with:
    - ``styles``: {style_name: count}
    - ``palettes``: {palette_hash: count}
    - ``fonts``: {font_pair: count}
    - ``layouts``: {layout_archetype: count}
    """
    recent = recent_signatures[-window:]
    styles: dict[str, int] = {}
    palettes: dict[str, int] = {}
    fonts: dict[str, int] = {}
    layouts: dict[str, int] = {}

    for sig in recent:
        s = sig.get("styleName", "")
        if s:
            styles[s] = styles.get(s, 0) + 1
        p = sig.get("paletteHash", "")
        if p:
            palettes[p] = palettes.get(p, 0) + 1
        f = sig.get("fontPair", "")
        if f:
            fonts[f] = fonts.get(f, 0) + 1
        la = sig.get("layoutArchetype", "")
        if la:
            layouts[la] = layouts.get(la, 0) + 1

    return {"styles": styles, "palettes": palettes, "fonts": fonts, "layouts": layouts}


def get_originality_report(memory: dict) -> dict:
    """Produce an originality analysis of the project's design history.

    Returns:
        dict with:
        - ``repetition_risk``: "low" | "medium" | "high"
        - ``overused``: dict of overused elements and counts
        - ``unique_styles_used``: int
        - ``total_builds``: int
        - ``recommendation``: str
    """
    sigs = memory.get("designSignatures", [])
    total = len(sigs)
    if total == 0:
        return {
            "repetition_risk": "low",
            "overused": {},
            "unique_styles_used": 0,
            "total_builds": 0,
            "recommendation": "No history yet — any style is fresh.",
        }

    overused = get_overused_elements(sigs)
    unique_styles = len(set(s.get("styleName", "") for s in sigs if s.get("styleName")))

    # Risk heuristic
    max_style_repeat = max(overused["styles"].values(), default=0)
    max_palette_repeat = max(overused["palettes"].values(), default=0)
    if max_style_repeat >= 3 or max_palette_repeat >= 3:
        risk = "high"
    elif max_style_repeat >= 2 or max_palette_repeat >= 2:
        risk = "medium"
    else:
        risk = "low"

    # Build a recommendation
    overused_styles = [s for s, c in overused["styles"].items() if c >= 2]
    if overused_styles:
        rec = f"Avoid: {', '.join(overused_styles)}. Pick from untried styles."
    else:
        rec = "Good variety — continue exploring new styles."

    return {
        "repetition_risk": risk,
        "overused": overused,
        "unique_styles_used": unique_styles,
        "total_builds": total,
        "recommendation": rec,
    }


# ── Memory integration ────────────────────────────────────────────────────────


def record_design_choice(memory: dict, design_direction: dict) -> dict:
    """Append a design choice to the memory's designSignatures list.

    Idempotent: will not add a duplicate entry for the same styleName
    in the same call sequence.
    """
    sig = design_direction.get("design_signature")
    if not sig or not isinstance(sig, dict):
        return memory

    existing_sigs = memory.get("designSignatures", [])
    # Check for duplicate (same styleName already at the tail)
    if existing_sigs and existing_sigs[-1].get("styleName") == sig.get("styleName"):
        return memory

    existing_sigs = list(existing_sigs)
    existing_sigs.append(sig)
    memory["designSignatures"] = existing_sigs[-_MAX_DESIGN_SIGNATURES:]
    return memory


def build_diversity_context(memory: dict) -> dict:
    """Build the diversity context dict to pass to ``create_design_direction``.

    Returns:
        dict with:
        - ``recent_signatures``: list of recent design signatures for penalty
        - ``originality_report``: originality analysis
        - ``avoid_styles``: list of style names to avoid
        - ``avoid_layouts``: list of layout archetypes to avoid
    """
    sigs = memory.get("designSignatures", [])
    report = get_originality_report(memory)
    overused = get_overused_elements(sigs)

    # Styles used 2+ times in recent history should be avoided
    avoid_styles = [s for s, c in overused["styles"].items() if c >= 2]
    avoid_layouts = [la for la, c in overused["layouts"].items() if c >= 2]

    return {
        "recent_signatures": sigs,
        "originality_report": report,
        "avoid_styles": avoid_styles,
        "avoid_layouts": avoid_layouts,
    }


# ── Section archetype tracking ────────────────────────────────────────────────


def extract_section_archetypes(html_content: str) -> list[str]:
    """Heuristically detect which section archetypes appear in generated HTML.

    Used to track section repetition across iterations.
    """
    lower = html_content.lower()
    found: list[str] = []

    _SECTION_MARKERS: list[tuple[str, list[str]]] = [
        ("cinematic_hero", ["hero", "hero-section", "hero-banner"]),
        ("luxury_showcase", ["showcase", "luxury", "spotlight"]),
        ("product_spotlight", ["product-spotlight", "product-feature", "highlight"]),
        ("dashboard_preview", ["dashboard-preview", "app-preview", "screenshot"]),
        ("workflow_timeline", ["timeline", "workflow", "how-it-works", "steps"]),
        ("trust_bar", ["trust-bar", "logos", "partners", "trusted-by", "clients"]),
        ("comparison_grid", ["comparison", "versus", "vs-table"]),
        ("pricing", ["pricing", "plans", "subscription"]),
        ("cta", ["cta", "call-to-action", "get-started", "sign-up-section"]),
        ("testimonials", ["testimonials", "reviews", "social-proof"]),
        ("feature_cards", ["features", "feature-cards", "benefit"]),
        ("gallery", ["gallery", "portfolio-grid", "photo-grid"]),
        ("faq", ["faq", "frequently-asked"]),
        ("metrics", ["metrics", "stats", "numbers", "counter"]),
        ("integrations", ["integrations", "ecosystem", "connect"]),
    ]

    for archetype, markers in _SECTION_MARKERS:
        if any(m in lower for m in markers):
            found.append(archetype)

    return found


def compute_section_penalty(
    proposed_sections: list[str],
    memory: dict,
) -> float:
    """Compute a 0-1 penalty for a proposed set of section archetypes based on history.

    Args:
        proposed_sections: Section archetypes planned for the new build.
        memory: Project memory containing iterationHistory.

    Returns:
        float in [0.0, 1.0] — 0 = unique, 1 = all repeated.
    """
    if not proposed_sections:
        return 0.0

    # Gather all sections used in iteration history
    past_sections: list[str] = []
    for entry in memory.get("iterationHistory", []):
        past_sections.extend(entry.get("sections", []))

    if not past_sections:
        return 0.0

    overlap = sum(1 for s in proposed_sections if s in past_sections)
    return overlap / len(proposed_sections)


# ── Palette uniqueness ────────────────────────────────────────────────────────


def palette_hash(palette: dict) -> str:
    """Produce an 8-char hash of a palette dict for deduplication."""
    palette_str = "|".join(f"{k}={v}" for k, v in sorted(palette.items()))
    return hashlib.sha256(palette_str.encode()).hexdigest()[:8]


def is_palette_overused(palette: dict, memory: dict, threshold: int = 2) -> bool:
    """Return True if this palette hash has appeared >= threshold times in memory."""
    ph = palette_hash(palette)
    sigs = memory.get("designSignatures", [])
    count = sum(1 for s in sigs if s.get("paletteHash") == ph)
    return count >= threshold
