"""
Specialist Agent Contracts for Amarktai App Builder.

Defines the contract (responsibility, I/O schema, routing, failure behavior)
for each specialist agent. Used in model routing and prompt construction.
"""
from __future__ import annotations

from typing import Any

# ── Agent contract registry ──────────────────────────────────────────────────

AGENT_CONTRACTS: dict[str, dict[str, Any]] = {

    "clarifier": {
        "name": "Clarifier Agent",
        "responsibility": (
            "Ask targeted clarifying questions before build when the prompt is too vague. "
            "Questions are build-type-specific. Max 5 questions. "
            "Offer 'Use recommended defaults' to skip clarification."
        ),
        "task_type": "planning",
        "input_schema": {
            "prompt": "str — user's raw build prompt",
            "mode": "str — detected build mode (landing_page|website|pwa|full_stack|repo_fix|...)",
        },
        "output_schema": {
            "needs_clarification": "bool",
            "questions": "list[{id, question, type, options?}]",
            "can_skip": "bool — offer defaults path",
            "mode_hint": "str — detected mode",
        },
        "validation": "questions.length <= 5; only ask what's needed for the build type",
        "failure_behavior": "return needs_clarification=False, proceed with best-effort defaults",
    },

    "brand_design_director": {
        "name": "Brand / Design Director Agent",
        "responsibility": (
            "Select design style, palette, typography, layout archetype. "
            "Apply design diversity penalty to avoid repeating recent styles. "
            "Return design tokens and coder instructions."
        ),
        "task_type": "planning",
        "input_schema": {
            "prompt": "str",
            "project_type": "str",
            "audience": "str",
            "tier": "str",
            "recent_design_signatures": "list[dict] — last N design signatures for diversity",
        },
        "output_schema": {
            "design_direction": "dict — full design direction including palette/typography/motifs",
            "design_signature": "dict — {styleName, paletteHash, fontPair, layoutArchetype}",
            "coder_instructions": "str",
        },
        "validation": "design must differ from recent_design_signatures; contrast must pass",
        "failure_behavior": "use deterministic fallback style from catalog",
    },

    "logo_agent": {
        "name": "Logo Agent",
        "responsibility": (
            "Produce a logo for the project. Use uploaded logo if selected, "
            "else generate deterministic SVG. Save result to media library. "
            "Generate favicon. Apply logo to nav/footer/head consistently."
        ),
        "task_type": "media_generation",
        "input_schema": {
            "businessName": "str",
            "industry": "str",
            "style": "str",
            "designTokens": "dict",
            "mediaSource": "str — auto|ai|pixabay|css_svg|uploaded",
            "uploadedLogoAssetId": "str|null",
        },
        "output_schema": {
            "logoType": "str — uploaded|svg|ai_generated|fallback",
            "assetId": "str|null",
            "files": "list[{filename, content, media_type, mime_type}]",
            "htmlSnippet": "str",
            "cssSnippet": "str",
            "faviconDataUri": "str",
            "usageNotes": "str",
            "fallbackUsed": "bool",
            "warnings": "list[str]",
        },
        "validation": "uploaded logo must be used when uploadedLogoAssetId is set; no fake AI",
        "failure_behavior": "generate SVG fallback and set fallbackUsed=True with warning",
    },

    "media_agent": {
        "name": "Media Agent",
        "responsibility": (
            "Source, validate, and provide media for the project. "
            "Respects mediaSource selection: uploaded|pixabay|genx|qwen|css_svg|auto. "
            "Saves all used media to the media library. Never fakes generation."
        ),
        "task_type": "media_generation",
        "input_schema": {
            "project_id": "str",
            "media_source": "str",
            "prompt": "str",
            "design_direction": "dict",
            "uploaded_asset_ids": "list[str]",
        },
        "output_schema": {
            "media_items": "list[{assetId, url, type, attribution?, prompt?}]",
            "css_svg_fallbacks": "list[str]",
            "warnings": "list[str]",
        },
        "validation": "Pixabay items must include attribution; no broken URLs",
        "failure_behavior": "return CSS/SVG fallbacks with warning; never block build",
    },

    "ux_architect": {
        "name": "UX Architect Agent",
        "responsibility": (
            "Define the page/component structure, nav, user flows, and information architecture. "
            "Collaborates with Stack Architect. Output fed to Frontend Agent."
        ),
        "task_type": "planning",
        "input_schema": {
            "prompt": "str",
            "mode": "str",
            "clarification_answers": "dict",
            "design_direction": "dict",
        },
        "output_schema": {
            "pages": "list[{name, route, purpose, sections}]",
            "nav_structure": "dict",
            "user_flows": "list[str]",
            "component_map": "dict",
        },
        "validation": "all routes must resolve; nav must include all pages",
        "failure_behavior": "fall back to minimal page set appropriate for mode",
    },

    "stack_architect": {
        "name": "Stack Architect Agent",
        "responsibility": (
            "Choose frontend/backend/database/auth stack. "
            "Uses stack decision engine. Respects user preferences. "
            "Outputs tech_stack.json and requirements.md."
        ),
        "task_type": "architecture",
        "input_schema": {
            "prompt": "str",
            "mode": "str",
            "quality_tier": "str",
            "stack_preference": "str|null",
            "database_preference": "str|null",
            "auth_required": "bool",
        },
        "output_schema": {
            "stack": "dict — {frontend, backend, database, auth, deployment}",
            "tech_stack_json": "str",
            "requirements_md": "str",
            "env_requirements": "list[str]",
        },
        "validation": "stack must be consistent; env vars must be documented",
        "failure_behavior": "use default safe stack for the mode",
    },

    "frontend_agent": {
        "name": "Frontend Agent",
        "responsibility": (
            "Generate all frontend files: HTML, CSS, JS/JSX. "
            "Apply design direction, logo, media, fonts. "
            "Produce responsive, accessible, production-ready code."
        ),
        "task_type": "frontend_coding",
        "input_schema": {
            "prompt": "str",
            "design_direction": "dict",
            "logo_result": "dict",
            "media_items": "list",
            "page_structure": "dict",
            "stack": "dict",
        },
        "output_schema": {
            "files": "list[{path, content, language}]",
        },
        "validation": (
            "index.html required; font link in head; logo used; "
            "responsive CSS; no empty sections; no broken paths"
        ),
        "failure_behavior": "emit partial files with error comment; repair agent takes over",
    },

    "backend_agent": {
        "name": "Backend Agent",
        "responsibility": (
            "Generate backend server code, API routes, auth middleware, database models. "
            "Uses stack from Stack Architect. Follows security best practices."
        ),
        "task_type": "backend_coding",
        "input_schema": {
            "prompt": "str",
            "stack": "dict",
            "auth_required": "bool",
            "database_preference": "str",
            "env_requirements": "list[str]",
        },
        "output_schema": {
            "files": "list[{path, content, language}]",
            "env_example": "str",
        },
        "validation": "no hardcoded secrets; .env.example provided; API routes documented",
        "failure_behavior": "emit minimal viable backend with error comment",
    },

    "repo_agent": {
        "name": "Repo Agent",
        "responsibility": (
            "Import, analyze, and modify existing GitHub repos. "
            "Detect intent, preserve working code, apply targeted fixes."
        ),
        "task_type": "backend_coding",
        "input_schema": {
            "repo_url": "str",
            "branch": "str",
            "intent": "str",
            "files": "list[{path, content}]",
        },
        "output_schema": {
            "files": "list[{path, content, language}]",
            "changed_files": "list[str]",
            "pr_summary": "str",
        },
        "validation": "no regressions on working features; tests must still pass",
        "failure_behavior": "return original files with targeted changes only",
    },

    "preview_runtime_agent": {
        "name": "Preview Runtime Agent",
        "responsibility": (
            "Serve the preview iframe for generated projects. "
            "Inline assets, resolve relative paths, handle CSP. "
            "Return canPreview=True for static sites, fallback plan for others."
        ),
        "task_type": "validation",
        "input_schema": {
            "files": "list[{path, content}]",
            "mode": "str",
        },
        "output_schema": {
            "canPreview": "bool",
            "html": "str|null",
            "fallback": "dict|null",
        },
        "validation": "preview HTML must be safe and renderable in iframe",
        "failure_behavior": "return canPreview=False with fallback plan",
    },

    "security_agent": {
        "name": "Security Agent",
        "responsibility": (
            "Review generated code for security issues: secrets exposure, "
            "injection risks, missing auth guards, insecure defaults."
        ),
        "task_type": "validation",
        "input_schema": {
            "files": "list[{path, content}]",
            "mode": "str",
            "auth_required": "bool",
        },
        "output_schema": {
            "securityScore": "int 0-100",
            "issues": "list[{severity, file, detail, fix}]",
            "passed": "bool",
        },
        "validation": "no plaintext secrets; no hardcoded JWT secrets in code",
        "failure_behavior": "block finalize if critical issues; warn for medium/low",
    },

    "qa_validation_agent": {
        "name": "QA / Validation Agent",
        "responsibility": (
            "Validate generated project: quality, design, HTML structure, CSS readability, "
            "media attribution, logo presence, responsive layout. "
            "Score quality/design/security. Block finalize if below thresholds."
        ),
        "task_type": "validation",
        "input_schema": {
            "files": "list[{path, content}]",
            "mode": "str",
            "design_direction": "dict",
            "logo_result": "dict",
            "media_items": "list",
        },
        "output_schema": {
            "qualityScore": "int 0-100",
            "designScore": "int 0-100",
            "securityScore": "int 0-100",
            "canFinalize": "bool",
            "issues": "list[str]",
            "warnings": "list[str]",
        },
        "validation": "canFinalize requires quality>=75, design>=70, security>=75 (if auth)",
        "failure_behavior": "return scores and issues list; repair agent triggered if needed",
    },

    "pr_release_agent": {
        "name": "PR / Release Agent",
        "responsibility": (
            "Finalize the project: create GitHub repo or branch PR. "
            "Summarize changes, include scores, stack, and preview note. "
            "Verify no secrets in committed files."
        ),
        "task_type": "review",
        "input_schema": {
            "project_id": "str",
            "files": "list[{path, content}]",
            "validation_scores": "dict",
            "repo_name": "str",
            "private": "bool",
        },
        "output_schema": {
            "repo_url": "str|null",
            "pr_url": "str|null",
            "pr_summary": "str",
        },
        "validation": "no .env files committed; no secrets in code",
        "failure_behavior": "raise HTTPException with clear error message",
    },
}


def get_contract(agent_name: str) -> dict[str, Any] | None:
    """Return the contract for a named agent, or None if not found."""
    return AGENT_CONTRACTS.get(agent_name)


def get_all_contracts() -> dict[str, dict[str, Any]]:
    """Return all agent contracts."""
    return dict(AGENT_CONTRACTS)


def contracts_prompt_block() -> str:
    """Return a brief summary of all agent roles for use in prompts."""
    lines = ["=== SPECIALIST AGENTS ==="]
    for key, contract in AGENT_CONTRACTS.items():
        lines.append(f"[{contract['name']}] {contract['responsibility'][:100]}...")
    return "\n".join(lines)
