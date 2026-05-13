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

    # ── New agents added in Phase 3 agent audit ─────────────────────────────

    "manager": {
        "name": "Manager Agent",
        "responsibility": (
            "Owns the complete build lifecycle. Breaks user prompt into tasks, assigns "
            "workers, tracks task completion, and blocks final success if any required "
            "task is skipped, tools are unavailable, or visual QA fails."
        ),
        "task_type": "orchestration",
        "input_schema": {
            "prompt": "str",
            "mode": "str",
            "stack_decision": "dict",
        },
        "output_schema": {
            "build_plan": "dict — complexity, phases, pages, files, risks",
            "task_checklist": "list[str]",
            "worker_assignments": "dict[agent → task]",
        },
        "validation": "all tasks completed; no worker skipped; no fake success",
        "failure_behavior": "block finalization; emit manager_blocked event with reason",
    },

    "motion_3d": {
        "name": "Motion / 3D Agent",
        "responsibility": (
            "Implements particles, Three.js, Framer Motion, GSAP, CSS animations, "
            "video backgrounds, animated hero sections, and interactive 3D scenes. "
            "Always respects prefers-reduced-motion. Never breaks layout."
        ),
        "task_type": "implementation",
        "input_schema": {
            "animation_requirements": "str — what was requested",
            "design_direction": "dict — design tokens from Creative Director",
            "files": "list[{path, content}] — current project files",
        },
        "output_schema": {
            "files": "list[{path, content}] — amended/new files",
            "summary": "str",
            "techniques_used": "list[str]",
        },
        "validation": "prefers-reduced-motion respected; no layout breakage; fallback present",
        "failure_behavior": "skip motion enhancements and note in summary; never break build",
    },

    "visual_qa": {
        "name": "Visual QA Agent",
        "responsibility": (
            "Reviews layout quality, typography, contrast, spacing, and mobile responsiveness. "
            "Checks premium feel — must not look like a generic AI template. "
            "Blocks completion if design_score < 70."
        ),
        "task_type": "review",
        "input_schema": {
            "files": "list[{path, content}]",
            "design_direction": "dict",
            "mode": "str",
        },
        "output_schema": {
            "passed": "bool",
            "design_score": "int 0-100",
            "issues": "list[{severity, file, description, fix}]",
            "strengths": "list[str]",
            "summary": "str",
        },
        "validation": "design_score >= 70 for passed=true; no critical issues",
        "failure_behavior": "return passed=false with actionable issue list; trigger repair",
    },

    "backend_coder": {
        "name": "Backend Coder Agent",
        "responsibility": (
            "Implements backend APIs, auth, database scaffolding, and services for "
            "full-stack builds. Never hardcodes secrets. Always generates .env.example. "
            "Produces complete, runnable code."
        ),
        "task_type": "implementation",
        "input_schema": {
            "requirements": "dict",
            "arch_plan": "dict",
            "auth_required": "bool",
            "database": "str — postgres|mongodb|mariadb|sqlite|none",
        },
        "output_schema": {
            "files": "list[{path, content}]",
            "summary": "str",
            "env_vars": "list[str]",
        },
        "validation": "no hardcoded secrets; .env.example present; auth uses bcrypt",
        "failure_behavior": "emit error; never generate code with hardcoded credentials",
    },

    "security": {
        "name": "Security Agent",
        "responsibility": (
            "Reviews generated code for hardcoded secrets, weak auth patterns, "
            "SQL injection, XSS, and insecure configurations. "
            "Blocks completion on critical/high violations."
        ),
        "task_type": "review",
        "input_schema": {
            "files": "list[{path, content}]",
            "mode": "str",
            "auth_required": "bool",
        },
        "output_schema": {
            "passed": "bool",
            "risk_level": "str — low|medium|high|critical",
            "violations": "list[{severity, file, category, description, fix}]",
            "summary": "str",
        },
        "validation": "passed=false when any critical or high violation found",
        "failure_behavior": "block finalization; list all violations with fixes",
        "tools": [
            "repo_file_read", "secret_scanner", "insecure_pattern_scanner",
            "diff_generator", "capability_registry",
        ],
    },

    "repo_engineer": {
        "name": "Repo Engineer Agent",
        "responsibility": (
            "Manages git operations safely: clone, branch, commit, push, PR. "
            "Detects dirty state before pull. Never overwrites uncommitted changes without confirmation. "
            "Uses safe subprocess calls only (never shell=True)."
        ),
        "task_type": "implementation",
        "input_schema": {
            "repo_url": "str — GitHub HTTPS URL",
            "branch": "str",
            "changes": "list[{path, content, action}]",
            "commit_message": "str",
            "github_pat": "str|null",
        },
        "output_schema": {
            "ok": "bool",
            "local_path": "str",
            "commit_sha": "str|null",
            "pr_url": "str|null",
            "logs": "list[str]",
            "error": "str|null",
        },
        "validation": "owner/repo/branch must be sanitised; no path traversal; tokens masked in logs",
        "failure_behavior": "return ok=false with masked error; never expose token in logs",
        "tools": [
            "git_clone", "git_pull", "git_status", "git_commit", "git_push",
            "git_open_pr", "repo_file_read", "repo_file_write", "diff_generator",
            "capability_registry",
        ],
    },

    "visual_qa": {
        "name": "Visual QA Agent",
        "responsibility": (
            "Inspects the preview output for visual completeness: "
            "no blank sections, no broken layout, no placeholder-only pages, "
            "no missing images. Reports exact issues with page/section references."
        ),
        "task_type": "review",
        "input_schema": {
            "files": "list[{path, content}]",
            "preview_url": "str|null",
            "screenshot_data": "str|null — base64 PNG if available",
        },
        "output_schema": {
            "passed": "bool",
            "score": "int — 0-100",
            "issues": "list[{severity, page, section, description, fix}]",
            "summary": "str",
        },
        "validation": "score >= 70 for passing; all sections reviewed",
        "failure_behavior": "block finalization on score < 50; list all issues",
        "tools": [
            "repo_file_read", "screenshot_visual_qa_hook", "preview_runner",
            "accessibility_checker", "capability_registry",
        ],
    },

    "accessibility": {
        "name": "Accessibility Agent",
        "responsibility": (
            "Reviews UI code for WCAG 2.1 AA compliance: contrast ratios, "
            "aria-labels, keyboard navigation, focus management, alt text, "
            "semantic HTML, form labels."
        ),
        "task_type": "review",
        "input_schema": {
            "files": "list[{path, content}]",
            "design_tokens": "dict|null",
        },
        "output_schema": {
            "passed": "bool",
            "wcag_level": "str — A|AA|AAA",
            "violations": "list[{rule, severity, element, description, fix}]",
            "score": "int — 0-100",
        },
        "validation": "passed=true only at AA or higher",
        "failure_behavior": "return violations with exact fix instructions; never silently pass",
        "tools": [
            "repo_file_read", "accessibility_checker", "diff_generator",
            "capability_registry",
        ],
    },

    "deployment": {
        "name": "Deployment Agent",
        "responsibility": (
            "Verifies build and deploy steps are complete and correct. "
            "Checks Dockerfile, CI config, environment vars, build scripts. "
            "Generates deployment notes. Never deploys without a passing QA gate."
        ),
        "task_type": "deployment",
        "input_schema": {
            "workspace_path": "str",
            "stack": "str",
            "build_result": "dict|null",
            "qa_result": "dict|null",
        },
        "output_schema": {
            "ready": "bool",
            "blockers": "list[str]",
            "deployment_notes": "str",
            "env_vars_required": "list[str]",
            "docker_ready": "bool",
        },
        "validation": "ready=false when build or QA failed or env vars missing",
        "failure_behavior": "list exact blockers; never mark ready=true without evidence",
        "tools": [
            "build_runner", "test_runner", "repo_file_read", "deployment_planner",
            "env_var_detector", "stack_detector", "log_analyzer", "capability_registry",
        ],
    },

    "monitoring": {
        "name": "Monitoring Agent",
        "responsibility": (
            "Reports real runtime status: active previews, stale processes, "
            "disk usage, failed builds, provider probe results. "
            "Never claims healthy when issues exist."
        ),
        "task_type": "monitoring",
        "input_schema": {
            "runtime_context": "dict",
        },
        "output_schema": {
            "status": "str — healthy|degraded|unhealthy",
            "active_previews": "int",
            "stale_processes": "int",
            "disk_free_mb": "float",
            "failed_builds_last_hour": "int",
            "provider_status": "dict",
        },
        "validation": "status=healthy only when all gates pass",
        "failure_behavior": "always report true status; never suppress warnings",
        "tools": [
            "log_analyzer", "capability_registry", "build_runner", "preview_runner",
        ],
    },

    "capability_truth": {
        "name": "Capability Truth Agent",
        "responsibility": (
            "Blocks fake capability claims. Validates that provider live probes "
            "are run before reporting 'live_ok'. Distinguishes between "
            "key_present_not_tested and key_present_live_ok. "
            "Refuses to let dashboard show 'working' when only a key is configured."
        ),
        "task_type": "validation",
        "input_schema": {
            "capability_summary": "dict",
            "probe_results": "dict",
        },
        "output_schema": {
            "validated": "bool",
            "fake_claims": "list[str]",
            "corrected_summary": "dict",
        },
        "validation": "no provider shown as live_ok without a passing probe",
        "failure_behavior": "downgrade claim to key_present_not_tested; log warning",
        "tools": ["capability_registry", "live_probe_runner"],
    },

    "memory_curator": {
        "name": "Memory Curator Agent",
        "responsibility": (
            "Persists reusable project lessons: design decisions, tech stack choices, "
            "common errors and fixes, component patterns. "
            "Surfaces relevant lessons to agents at the start of each build."
        ),
        "task_type": "memory",
        "input_schema": {
            "project_id": "str",
            "build_result": "dict",
            "agent_outputs": "dict",
        },
        "output_schema": {
            "lessons": "list[{key, value, relevance}]",
            "persisted": "bool",
        },
        "validation": "no duplicate lessons; lessons have clear keys and values",
        "failure_behavior": "log warning; do not block build on memory failure",
        "tools": ["project_memory", "capability_registry"],
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
