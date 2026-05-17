"""
Media Director Agent — Phase 2B Full Activation.

Responsibilities:
- Choose AI images when capability available, stock fallback otherwise
- Validate media relevance to subject/industry
- Enforce aspect ratios and quality standards
- Coordinate logo, motion, icons, SVG, animations
- Detect and reject duplicate images
- Score media quality and relevance
- Report honestly when AI media is unavailable
- Never fake AI-generated media

Input:
    {
        "industry": str,
        "style": str,
        "media_source": "auto|ai|pixabay|css_svg|uploaded",
        "design_tokens": dict,
        "build_mode": str,
        "page_context": [{"section": str, "subject": str}],
        "capability_registry": dict | None,
    }

Output:
    {
        "media_strategy": {"mode": str, "source": str, "honest_report": str},
        "assets": [{"section": str, "url": str, "type": str, "score": int}],
        "warnings": [],
        "media_score": int,
        "duplicate_count": int,
        "rejected_count": int,
    }
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger("amarktai.media_director")

# ── Relevance scoring ──────────────────────────────────────────────────────────

# Industry → subject relevance keywords
_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "tech": ["technology", "software", "code", "computer", "digital", "developer", "startup"],
    "saas": ["dashboard", "software", "app", "interface", "cloud", "analytics"],
    "finance": ["finance", "money", "investment", "bank", "chart", "growth", "trading"],
    "healthcare": ["health", "medical", "doctor", "patient", "wellness", "care"],
    "ecommerce": ["shopping", "product", "store", "retail", "delivery", "cart"],
    "education": ["education", "learning", "student", "course", "book", "study"],
    "fitness": ["fitness", "gym", "exercise", "health", "workout", "sport"],
    "food": ["food", "restaurant", "cooking", "chef", "cuisine", "meal"],
    "travel": ["travel", "destination", "hotel", "flight", "adventure", "explore"],
    "real_estate": ["property", "house", "building", "real estate", "home", "rent"],
    "creative": ["design", "art", "creative", "portfolio", "brand", "visual"],
    "marketing": ["marketing", "advertising", "brand", "campaign", "social", "growth"],
}

# Style → visual tone keywords
_STYLE_VISUAL_TONES: dict[str, list[str]] = {
    "luxury": ["premium", "elegant", "gold", "high-end", "exclusive", "sophisticated"],
    "minimal": ["clean", "simple", "white", "minimal", "modern", "flat"],
    "bold": ["vibrant", "colorful", "dynamic", "energetic", "strong"],
    "corporate": ["professional", "business", "formal", "office", "team"],
    "tech": ["futuristic", "dark", "neon", "grid", "abstract", "digital"],
    "playful": ["fun", "bright", "cartoon", "colorful", "happy"],
}

# Aspect ratio categories
ASPECT_RATIOS = {
    "hero": (16, 9),
    "gallery": (4, 3),
    "portrait": (3, 4),
    "square": (1, 1),
    "banner": (21, 9),
    "thumbnail": (16, 9),
}

# Minimum quality scores for approval
MIN_RELEVANCE_SCORE = 40
MIN_QUALITY_SCORE = 50


# ── Quality scoring ────────────────────────────────────────────────────────────

def score_media_relevance(subject: str, context: str, industry: str = "", style: str = "") -> int:
    """
    Score how relevant a piece of media is to the subject/context (0-100).
    
    Uses keyword matching across subject, industry, and style dimensions.
    """
    subject_lower = (subject or "").lower()
    context_lower = (context or "").lower()
    industry_lower = (industry or "").lower()
    style_lower = (style or "").lower()

    score = 30  # Base score

    # Subject-context alignment
    if subject_lower and context_lower:
        subject_words = set(subject_lower.split())
        context_words = set(context_lower.split())
        overlap = len(subject_words & context_words)
        if overlap > 0:
            score += min(30, overlap * 10)

    # Industry keyword alignment
    for ind, keywords in _INDUSTRY_KEYWORDS.items():
        if ind in industry_lower or any(k in context_lower for k in keywords):
            if any(k in subject_lower for k in keywords):
                score += 20
                break

    # Style tone alignment
    for sty, tones in _STYLE_VISUAL_TONES.items():
        if sty in style_lower:
            if any(t in subject_lower for t in tones):
                score += 20
                break

    # Reject completely unrelated content
    _BAD_SUBJECTS = {"random", "placeholder", "stock photo", "generic", "sample"}
    if any(bad in subject_lower for bad in _BAD_SUBJECTS):
        score -= 30

    return max(0, min(100, score))


def score_media_quality(asset: dict[str, Any]) -> int:
    """
    Score intrinsic media quality (0-100).
    
    Checks dimensions, resolution, format suitability.
    """
    score = 50  # Base

    width = asset.get("width", 0)
    height = asset.get("height", 0)
    media_type = asset.get("type", asset.get("media_type", "")).lower()
    url = asset.get("url", asset.get("public_url", ""))

    # Resolution checks
    if width >= 1920 and height >= 1080:
        score += 30
    elif width >= 1280 and height >= 720:
        score += 20
    elif width >= 800 and height >= 600:
        score += 10
    elif width > 0 and height > 0:
        score -= 10  # Too small
    else:
        score -= 5  # Unknown dimensions

    # Format preference
    if media_type in ("image/webp", "webp"):
        score += 10
    elif media_type in ("image/png", "png"):
        score += 5
    elif media_type in ("image/jpeg", "jpg", "jpeg"):
        score += 5
    elif media_type in ("image/svg+xml", "svg"):
        score += 15  # SVG is scalable = always high quality

    # Valid URL
    if url and (url.startswith("http") or url.startswith("data:")):
        score += 5
    elif not url:
        score -= 20

    # AI-generated bonus (already scored by provider)
    if asset.get("ai_generated"):
        score += 15

    return max(0, min(100, score))


def detect_duplicates(asset_list: list[dict[str, Any]]) -> list[str]:
    """
    Detect duplicate assets by URL fingerprint or content hash.
    
    Returns list of duplicate asset IDs/URLs.
    """
    seen_urls: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    duplicates: list[str] = []

    for asset in asset_list:
        url = asset.get("url", asset.get("public_url", ""))
        asset_id = asset.get("id", asset.get("asset_id", url))

        if url:
            url_key = _normalize_url(url)
            if url_key in seen_urls:
                duplicates.append(asset_id)
                logger.warning("Duplicate media detected: %s (same URL as %s)", asset_id, seen_urls[url_key])
            else:
                seen_urls[url_key] = asset_id

        content = asset.get("svg_content", asset.get("content", ""))
        if content:
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            if content_hash in seen_hashes:
                if asset_id not in duplicates:
                    duplicates.append(asset_id)
                    logger.warning("Duplicate media detected: %s (same content hash)", asset_id)
            else:
                seen_hashes[content_hash] = asset_id

    return duplicates


def _normalize_url(url: str) -> str:
    """Normalize a URL for dedup comparison (remove query strings, lowercase)."""
    url = url.lower().strip()
    if "?" in url:
        url = url.split("?")[0]
    return url


# ── Media strategy selection ───────────────────────────────────────────────────

def select_media_strategy(
    media_source: str,
    capability_registry: dict[str, Any] | None,
    build_mode: str = "",
) -> dict[str, Any]:
    """
    Determine the honest media strategy based on what is actually available.
    
    Never claims AI generation is available when it's not.
    Returns a strategy dict with mode, honest_report, and fallback chain.
    """
    cap = capability_registry or {}
    ai_image_available = bool(
        cap.get("supports_image_generation")
        or cap.get("image_generation")
        or cap.get("ai_image_available")
        or cap.get("genx_image_generation")
    )
    stock_media_available = bool(
        cap.get("supports_stock_media")
        or cap.get("stock_media")
        or cap.get("pixabay")
        or cap.get("pixabay_available")
    )
    uploaded_media_available = bool(
        cap.get("supports_media_library")
        or cap.get("media_library")
        or cap.get("uploaded_media")
    )
    requested_source = (media_source or "auto").strip().lower()
    is_premium = (build_mode or "").strip().lower() in {
        "premium",
        "landing_page",
        "landing-page",
        "website",
        "media_page",
        "cinematic",
    }

    if requested_source == "ai":
        if ai_image_available:
            return {
                "mode": "ai",
                "source": "ai_generated",
                "honest_report": "AI image generation is available and will be used.",
                "fallback": "pixabay",
                "stock_media_available": stock_media_available,
                "uploaded_media_available": uploaded_media_available,
            }
        else:
            return {
                "mode": "stock" if stock_media_available else "media_required_unavailable",
                "source": "pixabay" if stock_media_available else "none",
                "honest_report": (
                    "AI image generation is NOT available in this environment. "
                    + ("Using persisted Pixabay stock assets as the premium fallback. " if stock_media_available else "No persisted media provider is available. ")
                    + "No fake AI images will be used."
                ),
                "fallback": "pixabay" if stock_media_available else None,
                "ai_unavailable": True,
                "stock_media_available": stock_media_available,
                "uploaded_media_available": uploaded_media_available,
            }

    elif requested_source == "pixabay":
        return {
            "mode": "stock" if stock_media_available else "media_required_unavailable",
            "source": "pixabay" if stock_media_available else "none",
            "honest_report": "Stock images from Pixabay will be used with relevance filtering." if stock_media_available else "Pixabay was requested but is not configured or not live-tested.",
            "fallback": "local_runtime_fallback" if is_premium else "css_svg",
            "stock_media_available": stock_media_available,
            "uploaded_media_available": uploaded_media_available,
        }

    elif requested_source == "css_svg":
        return {
            "mode": "css_svg",
            "source": "css_svg",
            "honest_report": "CSS gradients and SVG-only mode selected. No external images.",
            "fallback": None,
            "stock_media_available": stock_media_available,
            "uploaded_media_available": uploaded_media_available,
        }

    elif requested_source == "uploaded":
        return {
            "mode": "uploaded" if uploaded_media_available else "media_required_unavailable",
            "source": "media_library" if uploaded_media_available else "none",
            "honest_report": "Using uploaded media from the media library." if uploaded_media_available else "Uploaded media was requested but no media library assets are available.",
            "fallback": "pixabay" if stock_media_available else ("local_runtime_fallback" if is_premium else "css_svg"),
            "stock_media_available": stock_media_available,
            "uploaded_media_available": uploaded_media_available,
        }

    else:
        # Auto mode: pick best available
        if ai_image_available:
            return {
                "mode": "ai",
                "source": "ai_generated",
                "honest_report": "Auto mode: AI image generation selected (available).",
                "fallback": "pixabay",
                "stock_media_available": stock_media_available,
                "uploaded_media_available": uploaded_media_available,
            }
        elif uploaded_media_available:
            return {
                "mode": "uploaded",
                "source": "media_library",
                "honest_report": "Auto mode: uploaded media library selected.",
                "fallback": "pixabay" if stock_media_available else ("local_runtime_fallback" if is_premium else "css_svg"),
                "stock_media_available": stock_media_available,
                "uploaded_media_available": uploaded_media_available,
            }
        else:
            return {
                "mode": "stock" if stock_media_available else "media_required_unavailable",
                "source": "pixabay" if stock_media_available else "none",
                "honest_report": (
                    "Auto mode: AI image generation unavailable. "
                    + ("Pixabay stock assets selected." if stock_media_available else "No persisted media provider is available.")
                ),
                "fallback": "pixabay" if stock_media_available else ("local_runtime_fallback" if is_premium else None),
                "ai_unavailable": True,
                "stock_media_available": stock_media_available,
                "uploaded_media_available": uploaded_media_available,
            }


# ── Section → media subject mapping ───────────────────────────────────────────

_SECTION_SUBJECTS: dict[str, str] = {
    "hero": "cinematic hero background, abstract professional",
    "features": "product features illustration, icons, interface",
    "testimonials": "people, professionals, smiling team",
    "pricing": "business pricing, plan comparison",
    "about": "team, office, company culture",
    "gallery": "product showcase, portfolio, work examples",
    "contact": "communication, support, connection",
    "cta": "action, momentum, call to action",
    "workflow": "process, steps, workflow illustration",
    "metrics": "data, analytics, growth chart",
    "integrations": "technology, api, connectivity",
    "trust": "brand logos, partners, trust signals",
}


def suggest_section_media(
    section: str,
    industry: str,
    style: str,
    strategy: dict[str, Any],
) -> dict[str, Any]:
    """
    Suggest appropriate media for a specific page section.
    
    Returns guidance for the coder on what visual to use.
    """
    section_lower = (section or "hero").lower()
    subject = _SECTION_SUBJECTS.get(section_lower, f"{industry} {section_lower}")

    if strategy["mode"] == "css_svg":
        return {
            "section": section,
            "type": "css_gradient",
            "subject": subject,
            "implementation": f"Use CSS gradient background in {section} section. "
                              f"Industry: {industry}. Style: {style}. "
                              f"No external image URLs.",
            "score": 80,
        }
    elif strategy["mode"] == "ai":
        return {
            "section": section,
            "type": "ai_image",
            "subject": subject,
            "query": f"{industry} {subject} {style}",
            "aspect_ratio": _get_section_aspect_ratio(section_lower),
            "score": 90,
        }
    elif strategy["mode"] == "stock":
        return {
            "section": section,
            "type": "stock_image",
            "subject": subject,
            "query": f"{industry} {subject}",
            "aspect_ratio": _get_section_aspect_ratio(section_lower),
            "fallback_css": f"linear-gradient to bottom right matching {style} palette",
            "score": 70,
        }
    else:
        return {
            "section": section,
            "type": "css_gradient",
            "subject": subject,
            "implementation": "CSS gradient fallback.",
            "score": 60,
        }


def _get_section_aspect_ratio(section: str) -> str:
    ratio_map = {
        "hero": "16:9",
        "gallery": "4:3",
        "portrait": "3:4",
        "about": "16:9",
        "features": "1:1",
        "testimonials": "1:1",
        "trust": "16:9",
    }
    return ratio_map.get(section, "16:9")


def build_cinematic_scene_plan(
    *,
    industry: str = "",
    style: str = "",
    build_mode: str = "landing_page",
    page_context: list[dict[str, Any]] | None = None,
    strategy: dict[str, Any] | None = None,
    design_tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an ordered cinematic scene plan for premium media orchestration.

    The plan is deterministic and additive: callers can ignore it safely, while
    Coder/Creative Director consumers can use it to enforce a narrative arc.
    """
    page_context = page_context or []
    strategy = strategy or {}
    design_tokens = design_tokens or {}
    section_names = [str(ctx.get("section") or "").strip() for ctx in page_context if ctx.get("section")]
    if not section_names:
        section_names = [
            "hero",
            "transformation",
            "capabilities",
            "proof",
            "immersive_media",
            "conversion",
        ]

    archetypes = [
        ("hero", "opening_shot", "Create tension and immediate aspiration", "wide cinematic establishing shot with oversized headline and controlled line width", "slow parallax reveal, soft glow sweep, no busy card grid", "one dominant focal plane, 16:9 or 21:9 media, CTA visible above fold"),
        ("transformation", "vision", "Move from current pain to better future", "editorial split layout contrasting before and after states", "crossfade or vertical reveal as the user scrolls", "left narrative column, right evidence visual, generous negative space"),
        ("capabilities", "capability_showcase", "Reveal concrete builder capabilities", "spotlight panels, rails, and metrics strips instead of repetitive cards", "staggered reveal tied to meaningful capability groups", "alternate split, rail, spotlight, and metrics layouts"),
        ("proof", "runtime_proof", "Build trust with visible evidence", "screenshots, manifest excerpts, QA report cards, PR workflow proof", "subtle counter and timeline motion", "show artifacts, statuses, and verification paths"),
        ("immersive_media", "media_sequence", "Make media feel real and integrated", "local image/video/audio assets embedded as product evidence", "media pans, masked reveals, reduced-motion fallback", "persisted media paths only; CSS/SVG decoration cannot count as media proof"),
        ("conversion", "conversion_climax", "Turn confidence into action", "premium CTA band with compact form and strong outcome copy", "focus ring, button lift, background light movement", "single conversion goal, no competing CTAs"),
    ]

    scenes: list[dict[str, Any]] = []
    for index, section in enumerate(section_names[:8]):
        match = next((item for item in archetypes if item[0] in section.lower()), archetypes[min(index, len(archetypes) - 1)])
        scenes.append({
            "order": index + 1,
            "section": section,
            "role": match[1],
            "emotional_goal": match[2],
            "visual_direction": f"{match[3]}; industry={industry or 'software'}; style={style or 'cinematic premium'}",
            "motion_direction": match[4],
            "composition_rules": match[5],
        })

    return {
        "narrative_flow": [
            "tension",
            "vision",
            "capability_reveal",
            "proof",
            "outcome",
            "conversion",
        ],
        "build_mode": build_mode,
        "media_strategy": strategy.get("mode", "auto"),
        "typography_rules": {
            "headline_scale": "oversized H1 with controlled max-width",
            "line_width": "body copy max 68-76 characters",
            "layout_variety": "alternate split, spotlight, editorial, rail, metrics strip, and CTA band",
        },
        "color_notes": {
            "accent": design_tokens.get("accent") or design_tokens.get("color_accent") or "",
            "background": design_tokens.get("background") or design_tokens.get("color_bg") or "",
        },
        "scenes": scenes,
    }


# ── Main orchestration entry-point ─────────────────────────────────────────────

def run_media_director(
    industry: str = "",
    style: str = "",
    media_source: str = "auto",
    design_tokens: dict[str, Any] | None = None,
    build_mode: str = "landing_page",
    page_context: list[dict[str, Any]] | None = None,
    capability_registry: dict[str, Any] | None = None,
    existing_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Main Media Director entry-point.
    
    Orchestrates media selection, scoring, deduplication, and honest reporting.
    """
    design_tokens = design_tokens or {}
    page_context = page_context or []
    existing_assets = existing_assets or []

    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []

    # 1. Determine honest media strategy
    strategy = select_media_strategy(media_source, capability_registry, build_mode)
    cinematic_scene_plan = build_cinematic_scene_plan(
        industry=industry,
        style=style,
        build_mode=build_mode,
        page_context=page_context,
        strategy=strategy,
        design_tokens=design_tokens,
    )
    if strategy.get("ai_unavailable"):
        warnings.append(strategy["honest_report"])

    # 2. Score and filter existing assets
    duplicates = detect_duplicates(existing_assets) if existing_assets else []
    if duplicates:
        warnings.append(f"Detected {len(duplicates)} duplicate asset(s). They will be excluded.")

    for asset in existing_assets:
        asset_id = asset.get("id", asset.get("asset_id", ""))
        if asset_id in duplicates:
            continue

        relevance = score_media_relevance(
            subject=asset.get("description", asset.get("title", "")),
            context=f"{industry} {style}",
            industry=industry,
            style=style,
        )
        quality = score_media_quality(asset)
        combined = int(relevance * 0.4 + quality * 0.6)

        if relevance < MIN_RELEVANCE_SCORE:
            rejected.append({**asset, "rejection_reason": "low relevance", "relevance_score": relevance})
            warnings.append(
                f"Asset '{asset.get('title', asset_id)}' rejected: relevance score {relevance} < {MIN_RELEVANCE_SCORE}"
            )
        elif quality < MIN_QUALITY_SCORE:
            rejected.append({**asset, "rejection_reason": "low quality", "quality_score": quality})
            warnings.append(
                f"Asset '{asset.get('title', asset_id)}' rejected: quality score {quality} < {MIN_QUALITY_SCORE}"
            )
        else:
            approved.append({**asset, "relevance_score": relevance, "quality_score": quality, "combined_score": combined})

    # 3. Generate section media suggestions
    sections = [ctx.get("section", "hero") for ctx in page_context] or ["hero", "features", "cta"]
    section_media: list[dict[str, Any]] = []
    for section in sections:
        suggestion = suggest_section_media(section, industry, style, strategy)
        section_media.append(suggestion)

    # 4. Compute overall media score
    if approved:
        avg_score = int(sum(a.get("combined_score", 60) for a in approved) / len(approved))
    elif section_media:
        avg_score = int(sum(s.get("score", 60) for s in section_media) / len(section_media))
    else:
        avg_score = 50

    # 5. Report
    logger.info(
        "Media Director complete: strategy=%s assets_approved=%d rejected=%d score=%d",
        strategy["mode"], len(approved), len(rejected), avg_score,
    )

    return {
        "media_strategy": strategy,
        "approved_assets": approved,
        "rejected_assets": rejected,
        "section_media": section_media,
        "warnings": warnings,
        "media_score": avg_score,
        "duplicate_count": len(duplicates),
        "rejected_count": len(rejected),
        "honest_report": strategy["honest_report"],
        "ai_image_available": not strategy.get("ai_unavailable", False),
        "cinematic_scene_plan": cinematic_scene_plan,
    }
