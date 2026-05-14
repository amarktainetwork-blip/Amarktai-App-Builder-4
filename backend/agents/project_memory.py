"""
Amarktai Product Brain — Project Memory Engine.

Provides a canonical persistent memory schema for each project.
Memory is stored inside the MongoDB project document under the
``project_memory`` field and is updated after every major pipeline
phase so that later agents (iteration, repair, validation) can read
and honour prior decisions.

Usage::

    from agents.project_memory import (
        make_empty_memory,
        load_memory,
        save_memory,
        update_memory_brand,
        update_memory_design,
        update_memory_product,
        update_memory_pages,
        update_memory_iteration,
        update_memory_agent_decision,
        get_design_tokens,
        get_font_pair,
    )

The memory dict is a plain Python dict — no external dependencies.
All merge helpers accept the current memory dict and return the
updated version; callers must persist it with ``save_memory``.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

# Maximum iteration history entries to retain in memory
_MAX_ITERATION_HISTORY = 20
# Maximum agent decision records to retain
_MAX_AGENT_DECISIONS = 50
# Maximum design signatures to retain for diversity tracking
_MAX_DESIGN_SIGNATURES = 20


# ── Schema ───────────────────────────────────────────────────────────────────


def make_empty_memory() -> dict:
    """Return a blank project memory matching the canonical schema."""
    return {
        "brand": {
            "name": "",
            "industry": "",
            "tone": "",
            "audience": "",
            "positioning": "",
        },
        "design": {
            "visualDirection": "",
            "palette": {},
            "fonts": {},
            "spacing": "",
            "layoutStyle": "",
            "animationStyle": "",
            "componentStyle": "",
        },
        "media": {
            "preferredStyle": "",
            "heroStyle": "",
            "logoStyle": "",
            "imageSubjects": [],
            "aspectRatios": [],
            "generatedAssets": [],
        },
        # Phase 3: logo stored in memory for reuse across iterations
        "logo": {
            "logoType": "",       # "svg" | "uploaded" | "ai_generated" | "fallback"
            "assetId": "",
            "htmlSnippet": "",
            "cssSnippet": "",
            "faviconDataUri": "",
            "svgContent": "",
            "faviconSvg": "",
            "businessName": "",
            "generatedAt": "",
        },
        "product": {
            "buildMode": "",
            "stack": "",
            "database": "",
            "authStrategy": "",
            "deploymentStrategy": "",
        },
        "pages": [],
        "features": [],
        "requirements": [],
        "resolvedIssues": [],
        "unresolvedIssues": [],
        "iterationHistory": [],
        "agentDecisions": [],
        # Design diversity — compact signatures for the penalty engine
        "designSignatures": [],
        # Preserved design tokens — source of truth across iterations
        "designTokens": {},
        "fontPair": {},
        # Phase 1B: task history (accepted = keep, rejected = never do again)
        "acceptedTasks": [],
        "rejectedTasks": [],
        # Phase 1B: named design archetype (e.g. 'editorial-luxury')
        "designArchetype": "",
    }


def _merge_schema_defaults(current: Any, default: Any) -> Any:
    """Recursively fill missing schema keys while preserving stored values."""
    if isinstance(default, dict) and not isinstance(current, dict):
        return deepcopy(default)
    if isinstance(current, dict) and isinstance(default, dict):
        for key, default_val in default.items():
            if key not in current:
                current[key] = deepcopy(default_val)
            else:
                current[key] = _merge_schema_defaults(current[key], default_val)
    return current


def _ensure_schema(memory: dict) -> dict:
    """Fill missing nested keys so older memory docs are safe."""
    default = make_empty_memory()
    if not isinstance(memory, dict):
        return default
    return _merge_schema_defaults(memory, default)


# ── Persistence helpers ──────────────────────────────────────────────────────


async def load_memory(db: Any, project_id: str) -> dict:
    """Load project memory from MongoDB, returning an empty schema if absent."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "project_memory": 1})
    if not doc:
        return make_empty_memory()
    raw = doc.get("project_memory") or {}
    if not isinstance(raw, dict):
        return make_empty_memory()
    return _ensure_schema(raw)


async def save_memory(db: Any, project_id: str, memory: dict) -> None:
    """Persist the full memory dict into the project document."""
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {
            "project_memory": memory,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


# ── Merge helpers ────────────────────────────────────────────────────────────


def update_memory_brand(memory: dict, scout_data: dict, mode: str = "") -> dict:
    """Merge Scout output into the brand section of memory.

    Extracts brand name, industry, audience, and tone from the scout's
    summary and requirements. Does not overwrite existing non-empty values
    unless scout explicitly provides them.
    """
    memory = _ensure_schema(memory)
    brand = memory["brand"]

    audience = scout_data.get("audience", "")
    summary = scout_data.get("summary", "")
    ui_inspiration = scout_data.get("ui_inspiration", "")

    if audience and not brand["audience"]:
        brand["audience"] = audience
    if summary and not brand["positioning"]:
        brand["positioning"] = summary
    if ui_inspiration and not brand["tone"]:
        brand["tone"] = ui_inspiration

    # Try to infer industry from prompt/summary
    if not brand["industry"] and summary:
        brand["industry"] = _infer_industry(summary)

    # Persist mode in product section
    if mode and not memory["product"]["buildMode"]:
        memory["product"]["buildMode"] = mode

    memory["brand"] = brand
    return memory


def update_memory_design(memory: dict, design_direction: dict) -> dict:
    """Merge design direction into the design section of memory.

    Design decisions are sticky — they are NOT overwritten by subsequent
    calls unless the design_direction explicitly supplies new values. This
    preserves the creative identity across iterations.
    """
    memory = _ensure_schema(memory)
    design = memory["design"]

    palette = design_direction.get("palette", {})
    typography = design_direction.get("typography", {})
    font_import = design_direction.get("font_import", {})

    # Only set these on first write (or if they are empty)
    if palette and not design["palette"]:
        design["palette"] = dict(palette)
        # Also cache in top-level designTokens for quick access
        memory["designTokens"] = dict(palette)

    if typography and not design["fonts"]:
        design["fonts"] = dict(typography)
        memory["fontPair"] = dict(typography)

    if not design["visualDirection"]:
        design["visualDirection"] = design_direction.get("name", "")

    if not design["layoutStyle"]:
        design["layoutStyle"] = design_direction.get("layout_rhythm", "")

    if not design["animationStyle"]:
        design["animationStyle"] = design_direction.get("motion", "")

    if not design["spacing"]:
        design["spacing"] = design_direction.get("spacing", "")

    if not design["componentStyle"]:
        design["componentStyle"] = design_direction.get("visual_motifs", "")

    # Media section
    media = memory["media"]
    if not media["preferredStyle"]:
        media["preferredStyle"] = design_direction.get("media_direction", "")
    if not media["heroStyle"]:
        media["heroStyle"] = design_direction.get("layout_rhythm", "")

    # Track design signature for diversity penalty
    sig = design_direction.get("design_signature", {})
    if sig:
        existing_sigs = memory.get("designSignatures", [])
        # Avoid duplicate entries for the same style
        existing_style_names = {s.get("styleName") for s in existing_sigs}
        if sig.get("styleName") not in existing_style_names:
            existing_sigs.append(sig)
        memory["designSignatures"] = existing_sigs[-_MAX_DESIGN_SIGNATURES:]  # keep last N

    memory["design"] = design
    memory["media"] = media
    return memory


def update_memory_product(memory: dict, mode: str, stack_decision: dict) -> dict:
    """Merge stack/product decisions into the product section of memory."""
    memory = _ensure_schema(memory)
    product = memory["product"]

    if mode and not product["buildMode"]:
        product["buildMode"] = mode

    stack = stack_decision.get("stack", {})
    if stack:
        if not product["stack"]:
            frontend = stack.get("frontend", "")
            backend = stack.get("backend", "none")
            product["stack"] = f"{frontend} / {backend}" if backend != "none" else frontend

        if not product["database"]:
            product["database"] = stack.get("database", "")

    if not product["deploymentStrategy"]:
        preview = stack_decision.get("preview_strategy", "")
        product["deploymentStrategy"] = preview

    memory["product"] = product
    return memory


def update_memory_pages(memory: dict, files: list[dict]) -> dict:
    """Extract page names from generated HTML files and record them in memory."""
    memory = _ensure_schema(memory)
    pages = memory.get("pages", [])
    existing_page_paths = {p.get("path") for p in pages if isinstance(p, dict)}

    for f in files:
        path = f.get("path", "")
        if path.endswith((".html", ".htm")) and path not in existing_page_paths:
            pages.append({"path": path, "title": path.replace(".html", "").replace("-", " ").title()})
            existing_page_paths.add(path)

    memory["pages"] = pages
    return memory


def update_memory_features(memory: dict, scout_data: dict) -> dict:
    """Record core features from Scout output into memory."""
    memory = _ensure_schema(memory)
    features = memory.get("features", [])
    existing = set(features)
    for feat in scout_data.get("core_features", []):
        if feat and feat not in existing:
            features.append(feat)
            existing.add(feat)
    memory["features"] = features
    return memory


def update_memory_iteration(memory: dict, iteration_entry: dict) -> dict:
    """Append an iteration record to iterationHistory (capped at _MAX_ITERATION_HISTORY)."""
    memory = _ensure_schema(memory)
    history = memory.get("iterationHistory", [])
    history.append(iteration_entry)
    if len(history) > _MAX_ITERATION_HISTORY:
        history = history[-_MAX_ITERATION_HISTORY:]
    memory["iterationHistory"] = history
    return memory


def update_memory_agent_decision(memory: dict, agent: str, decision: str, detail: dict | None = None) -> dict:
    """Record a key agent decision for auditability and consistency enforcement."""
    memory = _ensure_schema(memory)
    decisions = memory.get("agentDecisions", [])
    decisions.append({
        "agent": agent,
        "decision": decision,
        "detail": detail or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(decisions) > _MAX_AGENT_DECISIONS:
        decisions = decisions[-_MAX_AGENT_DECISIONS:]
    memory["agentDecisions"] = decisions
    return memory


def update_memory_logo(memory: dict, logo_result: dict) -> dict:
    """Store logo agent output in memory for reuse across iterations.

    The logo is persisted so that:
    - Iteration agents can reuse the same logo without regenerating it.
    - The Coder agent receives logo HTML/CSS snippets for consistent placement.
    - The favicon is available for every page.
    - Brand colors are extracted and stored for design consistency.
    - Logo version is tracked and incremented on changes.

    Args:
        memory: Current project memory dict.
        logo_result: Output from run_logo_agent().

    Returns:
        Updated memory dict.
    """
    memory = _ensure_schema(memory)
    from datetime import datetime, timezone as _tz

    # Increment version if logo already exists and is not being reused
    existing = memory.get("logo", {})
    current_version = existing.get("logoVersion", 0)
    is_reused = logo_result.get("reusedFromMemory", False)
    new_version = current_version if is_reused else current_version + 1

    memory["logo"] = {
        "logoType": logo_result.get("logoType", ""),
        "assetId": logo_result.get("assetId", ""),
        "htmlSnippet": logo_result.get("htmlSnippet", ""),
        "cssSnippet": logo_result.get("cssSnippet", ""),
        "faviconDataUri": logo_result.get("faviconDataUri", ""),
        "svgContent": logo_result.get("svgContent", ""),
        "faviconSvg": logo_result.get("faviconSvg", ""),
        "businessName": logo_result.get("businessName", ""),
        "brandColors": logo_result.get("brandColors", {}),
        "logoVersion": new_version,
        "generatedAt": datetime.now(_tz.utc).isoformat(),
    }
    return memory


def get_logo_from_memory(memory: dict) -> dict | None:
    """Return the stored logo result from memory, or None if not set."""
    memory = _ensure_schema(memory)
    logo = memory.get("logo", {})
    if logo.get("logoType"):
        return logo
    return None


def mark_issue_resolved(memory: dict, issue: str) -> dict:
    """Move an issue from unresolvedIssues to resolvedIssues."""
    memory = _ensure_schema(memory)
    unresolved = memory.get("unresolvedIssues", [])
    resolved = memory.get("resolvedIssues", [])
    if issue in unresolved:
        unresolved.remove(issue)
        resolved.append(issue)
    memory["unresolvedIssues"] = unresolved
    memory["resolvedIssues"] = resolved
    return memory


def add_unresolved_issue(memory: dict, issue: str) -> dict:
    """Record a new unresolved issue in memory."""
    memory = _ensure_schema(memory)
    unresolved = memory.get("unresolvedIssues", [])
    if issue not in unresolved:
        unresolved.append(issue)
    memory["unresolvedIssues"] = unresolved
    return memory


# ── Read helpers ─────────────────────────────────────────────────────────────


def get_design_tokens(memory: dict) -> dict:
    """Return the persisted design palette tokens, or an empty dict."""
    memory = _ensure_schema(memory)
    tokens = memory.get("designTokens")
    if tokens and isinstance(tokens, dict):
        return tokens
    # Fallback: read from nested design.palette
    return memory.get("design", {}).get("palette", {})


def get_font_pair(memory: dict) -> dict:
    """Return the persisted font pair, or an empty dict."""
    memory = _ensure_schema(memory)
    pair = memory.get("fontPair")
    if pair and isinstance(pair, dict):
        return pair
    return memory.get("design", {}).get("fonts", {})


def get_design_direction_summary(memory: dict) -> str:
    """Return a human-readable summary of the locked design identity for use in iteration prompts."""
    memory = _ensure_schema(memory)
    design = memory.get("design", {})
    fonts = get_font_pair(memory)
    palette = get_design_tokens(memory)

    parts = []
    if design.get("visualDirection"):
        parts.append(f"Visual style: {design['visualDirection']}")
    if fonts.get("heading"):
        parts.append(f"Heading font: {fonts['heading']}")
    if fonts.get("body"):
        parts.append(f"Body font: {fonts['body']}")
    if palette.get("background"):
        parts.append(f"Background: {palette['background']}")
    if palette.get("accent"):
        parts.append(f"Accent: {palette['accent']}")
    if design.get("spacing"):
        parts.append(f"Spacing: {design['spacing']}")
    if design.get("animationStyle"):
        parts.append(f"Animation: {design['animationStyle']}")
    if design.get("layoutStyle"):
        parts.append(f"Layout: {design['layoutStyle']}")

    return "\n".join(parts) if parts else ""


def get_design_lock_prompt(memory: dict) -> str:
    """Build the DESIGN IDENTITY LOCK block injected into iteration prompts.

    This block tells the iteration agent exactly what must NOT change,
    preventing random redesigns on each iteration.
    """
    summary = get_design_direction_summary(memory)
    if not summary:
        return ""

    fonts = get_font_pair(memory)
    palette = get_design_tokens(memory)
    design = memory.get("design", {})

    lines = [
        "DESIGN IDENTITY LOCK (DO NOT CHANGE — preserved from original build):",
        "The following are LOCKED design decisions. You MUST NOT change them unless the user",
        "explicitly requests a redesign. Preserve all of these in every file you touch:",
        "",
        summary,
    ]

    if palette:
        lines.append("")
        lines.append("Locked palette (use these exact values for CSS custom properties):")
        for k, v in palette.items():
            lines.append(f"  --color-{k.replace('_', '-')}: {v}")

    if fonts.get("heading"):
        lines.append("")
        lines.append(f"Locked heading font: {fonts['heading']}")
        lines.append(f"  Use: font-family: var(--font-heading) in all heading selectors")
    if fonts.get("body"):
        lines.append(f"Locked body font: {fonts['body']}")
        lines.append(f"  Use: font-family: var(--font-body) in body/p selectors")

    nav_structure = [p.get("path") for p in memory.get("pages", []) if isinstance(p, dict)]
    if nav_structure:
        lines.append("")
        lines.append(f"Locked navigation pages: {', '.join(nav_structure)}")
        lines.append("  Keep ALL nav links pointing to these pages.")

    lines.append("")
    lines.append("VIOLATION = design regression. Output files must honour every item above.")

    return "\n".join(lines)


# ── Internal helpers ─────────────────────────────────────────────────────────


_INDUSTRY_KEYWORDS: list[tuple[list[str], str]] = [
    (["saas", "software", "app", "platform", "tool"], "SaaS / Software"),
    (["restaurant", "cafe", "food", "bakery", "dining", "menu", "chef"], "Food & Beverage"),
    (["hotel", "resort", "spa", "hospitality", "accommodation"], "Hospitality"),
    (["fashion", "clothing", "boutique", "apparel", "couture"], "Fashion"),
    (["finance", "fintech", "bank", "trading", "crypto", "invest"], "Finance"),
    (["health", "wellness", "fitness", "gym", "sport"], "Health & Wellness"),
    (["real estate", "property", "homes", "apartment"], "Real Estate"),
    (["car", "auto", "vehicle", "dealership", "bmw", "mercedes"], "Automotive"),
    (["education", "course", "learning", "school", "academy"], "Education"),
    (["nature", "eco", "organic", "sustainable", "green"], "Sustainability"),
    (["agency", "creative", "design", "studio", "portfolio"], "Creative Agency"),
    (["e-commerce", "ecommerce", "store", "shop", "marketplace"], "E-commerce"),
]


def _infer_industry(text: str) -> str:
    """Heuristically infer industry from a short text blob."""
    lower = text.lower()
    for keywords, label in _INDUSTRY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return label
    return ""
