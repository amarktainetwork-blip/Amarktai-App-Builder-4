"""
Agent Registry for Amarktai App Builder.

This module provides the complete inventory of all agents, their roles, tools,
current implementation status, and wiring to the orchestrator.

The registry is the single source of truth for:
- Which agents exist
- What role each agent plays
- Which tools each agent has access to
- Whether each agent is implemented (active) or needs wiring
- Which agents are called for which build modes

Required agent team (18 agents):
  1.  Manager Agent         → Orchestrator._run_build_pipeline (build planner + completion guard)
  2.  Product Strategist    → scout (SCOUT_PROMPT)
  3.  Creative Director     → run_creative_director() (deterministic)
  4.  UX Architect          → architect (ARCHITECT_PROMPT)
  5.  UI Designer           → design_engine.create_design_direction() (deterministic)
  6.  Frontend Coder        → coder (CODER_PROMPT)
  7.  Backend Coder         → coder in full-stack mode (BACKEND_CODER_PROMPT)
  8.  Repo Engineer         → repo_fix (REPO_FIX_PROMPT) + RepairEngine
  9.  Media Director        → pixabay.py + media_storage.py + GenX media hooks
  10. Logo Agent            → logo_agent.py (SVG + media library)
  11. Motion / 3D Agent     → motion_agent (MOTION_3D_PROMPT) — NEW
  12. QA Agent              → reviewer (REVIEWER_PROMPT) + quality_validator
  13. Visual QA Agent       → visual_qa (VISUAL_QA_PROMPT) — NEW
  14. Accessibility Agent   → quality_validator._score_accessibility() + reviewer
  15. SEO / Performance     → quality_validator._score_seo() + reviewer
  16. Security Agent        → security (SECURITY_PROMPT) — NEW
  17. Deployment Agent      → build_contract + sandbox_manager
  18. Worker Agents         → any specialist called by Manager
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ── Agent status constants ────────────────────────────────────────────────────
ACTIVE = "active"           # LLM agent with prompt, called in orchestrator
DETERMINISTIC = "deterministic"  # Rule/template-based, no LLM
PARTIAL = "partial"         # Exists but not fully wired to orchestrator
PLANNED = "planned"         # New agent added in this phase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Full Agent Registry ───────────────────────────────────────────────────────

AGENT_REGISTRY: dict[str, dict[str, Any]] = {

    # ── 1. Manager Agent ───────────────────────────────────────────────────────
    "manager": {
        "name": "Manager Agent",
        "role": "Owns the complete build lifecycle. Breaks the user prompt into tasks, "
                "assigns workers, tracks task completion, prevents partial delivery, "
                "and blocks final success if any required task is incomplete.",
        "status": ACTIVE,
        "implementation": "Orchestrator._run_build_pipeline + BUILD_PLANNER_PROMPT",
        "prompt_key": "BUILD_PLANNER_PROMPT",
        "tools": [
            "project_memory", "capability_registry", "task_checklist",
            "worker_assignment", "completion_guard",
        ],
        "model_tier": "research",
        "inputs": ["user_prompt", "mode", "stack_decision"],
        "outputs": ["build_plan", "task_list", "complexity", "pages", "files"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": True,
        "notes": "Acts as the orchestration manager. Blocks completion if required agents fail.",
    },

    # ── 2. Product Strategist ──────────────────────────────────────────────────
    "product_strategist": {
        "name": "Product Strategist Agent",
        "role": "Understands user intent, defines product structure, selects pages/features, "
                "detects build mode, and produces a requirements brief.",
        "status": ACTIVE,
        "implementation": "SCOUT_PROMPT",
        "prompt_key": "SCOUT_PROMPT",
        "tools": [
            "web_search", "project_memory", "requirements_extraction",
            "feature_planning", "audience_detection",
        ],
        "model_tier": "research",
        "inputs": ["user_prompt", "mode", "stack_decision"],
        "outputs": ["requirements_md", "core_features", "audience", "summary", "pain_points"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Maps to 'scout' agent in the orchestrator.",
    },

    # ── 3. Creative Director ───────────────────────────────────────────────────
    "creative_director": {
        "name": "Creative Director Agent",
        "role": "Owns premium visual direction. Prevents generic outputs. "
                "Defines brand, layout, tone, typography, color palette, and animation style. "
                "Enforces section archetype library, premium layout registry, and typography pairs.",
        "status": ACTIVE,
        "implementation": "creative_director.run_creative_director() — deterministic blueprint "
                          "engine with diversity checking, brand palette selection, "
                          "section archetype enforcement, and typography pair system",
        "prompt_key": None,
        "tools": [
            "design_engine", "design_dna", "brand_palette",
            "typography_system", "layout_archetypes", "diversity_checker",
            "section_archetype_library", "premium_layout_registry",
            "typography_pair_registry", "responsive_spacing_system",
        ],
        "model_tier": None,
        "inputs": ["user_prompt", "mode", "project_type", "audience", "quality_tier"],
        "outputs": ["design_blueprint", "design_tokens", "coder_instructions", "font_pair",
                    "section_plan", "animation_tone"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Deterministic blueprint engine. Enforces premium section archetypes and "
                 "typography hierarchy. Prevents purple/teal AI gradient defaults.",
    },

    # ── 4. UX Architect ────────────────────────────────────────────────────────
    "ux_architect": {
        "name": "UX Architect Agent",
        "role": "Designs user flows, page structure, navigation, and workspace/dashboard logic. "
                "Produces the technical file plan.",
        "status": ACTIVE,
        "implementation": "ARCHITECT_PROMPT",
        "prompt_key": "ARCHITECT_PROMPT",
        "tools": [
            "stack_engine", "file_plan", "route_design",
            "component_inventory", "tech_stack_selection",
        ],
        "model_tier": "research",
        "inputs": ["requirements", "mode", "stack_decision"],
        "outputs": ["tech_stack", "file_plan", "component_list"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Maps to 'architect' agent.",
    },

    # ── 5. UI Designer ─────────────────────────────────────────────────────────
    "ui_designer": {
        "name": "UI Designer Agent",
        "role": "Turns creative direction into components, design tokens, spacing, "
                "responsive layouts, and premium section templates. "
                "Enforces section archetype library and responsive spacing system.",
        "status": ACTIVE,
        "implementation": "design_engine.create_design_direction() + PREMIUM_SECTION_LIBRARY + "
                          "VISUAL_COMPOSITION_RULES — generates design tokens, section templates, "
                          "typography scale, responsive spacing, and layout constraints",
        "prompt_key": "PREMIUM_SECTION_LIBRARY",
        "tools": [
            "design_tokens", "responsive_breakpoints", "component_library",
            "section_templates", "spacing_system", "typography_scale",
            "premium_layout_registry", "visual_composition_rules",
        ],
        "model_tier": None,
        "inputs": ["design_blueprint", "project_type", "audience"],
        "outputs": ["design_direction", "design_tokens", "section_templates",
                    "typography_scale", "spacing_system", "responsive_rules"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Deterministic. PREMIUM_SECTION_LIBRARY and VISUAL_COMPOSITION_RULES "
                 "injected into CODER_PROMPT via shared_context.",
    },

    # ── 6. Frontend Coder ─────────────────────────────────────────────────────
    "frontend_coder": {
        "name": "Frontend Coder Agent",
        "role": "Implements React/Vite/Next.js/static frontend code. Handles animations, "
                "responsive UI, accessibility, and premium sections.",
        "status": ACTIVE,
        "implementation": "CODER_PROMPT",
        "prompt_key": "CODER_PROMPT",
        "tools": [
            "react", "vite", "nextjs", "tailwind", "framer_motion",
            "lucide_icons", "responsive_css", "accessibility", "web_fonts",
        ],
        "model_tier": "reasoning",
        "inputs": ["requirements", "arch_plan", "design_direction", "media_manifest"],
        "outputs": ["html_files", "css_files", "js_files", "react_components"],
        "called_from": ["_run_build_pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Premium output enforced via PREMIUM_SECTION_LIBRARY and VISUAL_COMPOSITION_RULES.",
    },

    # ── 7. Backend Coder ──────────────────────────────────────────────────────
    "backend_coder": {
        "name": "Backend Coder Agent",
        "role": "Implements backend APIs, database and auth scaffolding, env handling, "
                "and backend services. Separate from frontend in full-stack builds.",
        "status": ACTIVE,
        "implementation": "BACKEND_CODER_PROMPT (via coder in full-stack mode)",
        "prompt_key": "BACKEND_CODER_PROMPT",
        "tools": [
            "fastapi", "express", "jwt", "bcrypt", "prisma",
            "postgres", "mongodb", "docker", "env_templates",
        ],
        "model_tier": "reasoning",
        "inputs": ["requirements", "arch_plan", "auth_required", "database_preference"],
        "outputs": ["api_files", "auth_files", "db_models", "env_example", "docker_compose"],
        "called_from": ["_run_build_pipeline (full_stack/api_service mode)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Called when mode is full_stack, api_service, or dashboard with auth.",
    },

    # ── 8. Repo Engineer ──────────────────────────────────────────────────────
    "repo_engineer": {
        "name": "Repo Engineer Agent",
        "role": "Imports repos, detects stack, repairs broken builds, creates diffs/PRs.",
        "status": ACTIVE,
        "implementation": "REPO_FIX_PROMPT + RepairEngine",
        "prompt_key": "REPO_FIX_PROMPT",
        "tools": [
            "github_pat", "repo_clone", "stack_detection", "diff_generation",
            "pr_creation", "repair_engine", "checkpoint",
        ],
        "model_tier": "reasoning",
        "inputs": ["repo_url", "files", "repo_profile", "repair_plan"],
        "outputs": ["fixed_files", "diff_summary", "pr_url", "repair_log"],
        "called_from": ["_run_repo_fix", "repo_repair endpoint"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Also backed by deterministic RepairEngine for targeted fixes.",
    },

    # ── 9. Media Director ─────────────────────────────────────────────────────
    "media_director": {
        "name": "Media Director Agent",
        "role": "Decides when to use AI images, stock media, icons, SVG, video, and animation. "
                "Ensures media relevance and quality. Never fakes AI generation. "
                "Scores relevance, detects duplicates, enforces quality thresholds.",
        "status": ACTIVE,
        "implementation": "media_director.run_media_director() — full orchestration with "
                          "relevance scoring, quality scoring, duplicate detection, honest AI reporting",
        "prompt_key": None,
        "tools": [
            "pixabay_images", "pixabay_videos", "genx_image_generation",
            "qwen_image_generation", "svg_generation", "media_library",
            "capability_registry", "media_scoring", "duplicate_detector",
        ],
        "model_tier": None,
        "inputs": ["industry", "style", "media_source", "design_tokens", "page_context",
                   "capability_registry"],
        "outputs": ["media_manifest", "section_media", "media_strategy", "media_score",
                    "honest_report", "rejected_assets", "warnings"],
        "called_from": ["_run_build_pipeline (media_manifest in shared_context)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Fully activated in Phase 2B. Honest reporting when AI unavailable. "
                 "Scores relevance (0-100), quality (0-100), rejects poor media.",
    },

    # ── 10. Logo Agent ────────────────────────────────────────────────────────
    "logo_agent": {
        "name": "Logo Agent",
        "role": "Creates AI-generated or SVG logos, stores them in the media library, "
                "reuses them across iterations, places them in nav/footer/favicon.",
        "status": ACTIVE,
        "implementation": "logo_agent.py (SVG) + run_logo_agent() + media library storage",
        "prompt_key": None,
        "tools": [
            "svg_generation", "genx_image_generation", "media_library",
            "favicon_generation", "brand_colors",
        ],
        "model_tier": None,
        "inputs": ["businessName", "industry", "style", "designTokens", "mediaSource"],
        "outputs": ["logo_svg", "favicon", "html_snippet", "css_snippet", "asset_id"],
        "called_from": ["POST /api/logo", "shared_context in build pipeline"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "AI image generation is capability-gated. Falls back to SVG if unavailable.",
    },

    # ── 11. Motion / 3D Agent ─────────────────────────────────────────────────
    "motion_3d": {
        "name": "Motion / 3D Agent",
        "role": "Handles particles, Three.js, Framer Motion, GSAP, animated backgrounds, "
                "interactive hero sections, and video backgrounds.",
        "status": ACTIVE,
        "implementation": "MOTION_3D_PROMPT (called by orchestrator when animation detected)",
        "prompt_key": "MOTION_3D_PROMPT",
        "tools": [
            "three_js", "framer_motion", "gsap", "particle_systems",
            "css_animations", "video_backgrounds", "webgl",
        ],
        "model_tier": "reasoning",
        "inputs": ["design_direction", "animation_requirements", "files"],
        "outputs": ["animated_files", "motion_enhancements", "3d_scene"],
        "called_from": ["_run_build_pipeline (when 3D/animation detected in prompt)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Activated when prompt contains: 3D, particles, animations, video bg, GSAP, Three.js.",
    },

    # ── 12. QA Agent ──────────────────────────────────────────────────────────
    "qa_agent": {
        "name": "QA Agent",
        "role": "Checks build completeness, file integrity, routes, links, and runtime errors.",
        "status": ACTIVE,
        "implementation": "REVIEWER_PROMPT + quality_validator + coverage_score",
        "prompt_key": "REVIEWER_PROMPT",
        "tools": [
            "html_validator", "css_validator", "link_checker",
            "coverage_score", "build_contract_validator",
        ],
        "model_tier": "research",
        "inputs": ["files", "prompt", "mode", "validation_rules"],
        "outputs": ["review_report", "missing_files", "repair_tasks", "scores"],
        "called_from": ["_run_build_pipeline", "run_retry"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Maps to 'reviewer' agent.",
    },

    # ── 13. Visual QA Agent ───────────────────────────────────────────────────
    "visual_qa": {
        "name": "Visual QA Agent",
        "role": "Checks layout quality, typography, contrast, spacing, mobile responsiveness, "
                "and screenshot-based quality.",
        "status": ACTIVE,
        "implementation": "VISUAL_QA_PROMPT + quality_validator scoring",
        "prompt_key": "VISUAL_QA_PROMPT",
        "tools": [
            "layout_checker", "typography_validator", "contrast_checker",
            "responsive_tester", "quality_scorer",
        ],
        "model_tier": "research",
        "inputs": ["files", "design_direction", "mode"],
        "outputs": ["visual_qa_result", "design_score", "layout_issues", "suggestions"],
        "called_from": ["_run_build_pipeline (post-build gate)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Runs deterministic quality_validator + LLM visual review for premium builds.",
    },

    # ── 14. Accessibility Agent ───────────────────────────────────────────────
    "accessibility": {
        "name": "Accessibility Agent",
        "role": "Checks WCAG basics: keyboard nav, ARIA labels, contrast, semantic HTML. "
                "Produces real accessibility score (0-100) and actionable violation list.",
        "status": ACTIVE,
        "implementation": "quality_validator._score_accessibility() — enhanced axe-core-like "
                          "static analysis: lang attr, headings, alt text, ARIA, focus states, "
                          "skip links, landmarks, form labels, contrast indicators",
        "prompt_key": None,
        "tools": [
            "axe_core_static", "aria_checker", "contrast_validator",
            "keyboard_nav_checker", "semantic_html_validator", "label_checker",
            "reduced_motion_checker",
        ],
        "model_tier": None,
        "inputs": ["html_files", "css_files"],
        "outputs": ["accessibility_score", "violations", "suggestions", "wcag_aa_pass"],
        "called_from": ["_validate_contract (via quality_validator._score_accessibility())"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Fully activated in Phase 2B with enhanced static checks. "
                 "Full Playwright/axe-core integration requires runtime container (Phase 2C).",
    },

    # ── 15. SEO / Performance Agent ───────────────────────────────────────────
    "seo_performance": {
        "name": "SEO / Performance Agent",
        "role": "Checks metadata, OG tags, heading structure, Lighthouse basics, "
                "loading performance, image optimization, and CLS/LCP awareness. "
                "Produces real SEO score (0-100) and performance score (0-100).",
        "status": ACTIVE,
        "implementation": "quality_validator._score_seo() + _score_performance() — enhanced "
                          "with Twitter Card, structured data, image alt, canonical, "
                          "lazy loading, defer/async, font preloading checks",
        "prompt_key": None,
        "tools": [
            "meta_tag_checker", "og_tag_validator", "twitter_card_validator",
            "heading_hierarchy_checker", "image_optimization_checker",
            "lazy_loading_checker", "lighthouse_static_proxy", "structured_data_validator",
        ],
        "model_tier": None,
        "inputs": ["html_files", "css_files"],
        "outputs": ["seo_score", "performance_score", "recommendations", "heading_structure"],
        "called_from": ["_validate_contract (via quality_validator._score_seo() + _score_performance())"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Fully activated in Phase 2B. Lighthouse requires headless browser (Phase 2C).",
    },

    # ── 16. Security Agent ────────────────────────────────────────────────────
    "security": {
        "name": "Security Agent",
        "role": "Checks for hardcoded secrets, unsafe auth patterns, dangerous generated code, "
                "and dependency risks.",
        "status": ACTIVE,
        "implementation": "SECURITY_PROMPT (called post-coder in auth/full-stack builds)",
        "prompt_key": "SECURITY_PROMPT",
        "tools": [
            "secret_scanner", "auth_pattern_checker",
            "dependency_audit", "xss_detector", "injection_checker",
        ],
        "model_tier": "research",
        "inputs": ["files", "mode", "auth_required"],
        "outputs": ["security_report", "risks", "violations", "suggestions"],
        "called_from": ["_run_build_pipeline (when auth_required or full_stack)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Activated for full_stack, api_service, dashboard builds with auth.",
    },

    # ── 17. Deployment Agent ──────────────────────────────────────────────────
    "deployment": {
        "name": "Deployment Agent",
        "role": "Validates deploy scripts, env templates, Docker config, and runtime preview. "
                "Generates deployment instructions and rollback guidance. "
                "Never marks a broken runtime as successful.",
        "status": ACTIVE,
        "implementation": "deployment_agent.run_deployment_validation() — full validation: "
                          "Dockerfile, docker-compose, .env.example, build scripts, "
                          "preview readiness, health checks, deployment instructions",
        "prompt_key": None,
        "tools": [
            "docker_validator", "env_template_checker", "build_script_validator",
            "sandbox_preview", "build_log_streaming", "deploy_instruction_generator",
            "health_check_verifier", "rollback_coordinator",
        ],
        "model_tier": None,
        "inputs": ["files", "mode", "stack_decision"],
        "outputs": ["passed", "deploy_checklist", "warnings", "errors",
                    "deployment_instructions", "rollback_guidance", "preview_readiness"],
        "called_from": ["_run_build_pipeline (final step)", "POST /api/deploy/validate"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": True,
        "notes": "Fully activated in Phase 2B. Docker/sandbox preview is Phase 2C runtime.",
    },

    # ── 18. Worker Agents ─────────────────────────────────────────────────────
    "worker": {
        "name": "Worker Agents",
        "role": "Specialist execution agents called by the Manager for targeted tasks. "
                "Must not operate without context from the Manager.",
        "status": ACTIVE,
        "implementation": "All specialist LLM agents (coder, reviewer, repo_fix, motion_3d, security)",
        "prompt_key": None,
        "tools": ["all_agent_tools"],
        "model_tier": "varies",
        "inputs": ["task", "context", "files"],
        "outputs": ["task_result", "files", "status"],
        "called_from": ["Orchestrator via _run_agent()"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "notes": "Workers are all agents that receive tasks from the Manager/Orchestrator.",
    },

    # ── Phase 2B: 10 New Required Agents ─────────────────────────────────────

    # ── 19. Runtime Engineer Agent ────────────────────────────────────────────
    "runtime_engineer": {
        "name": "Runtime Engineer Agent",
        "role": "Preview, runtime, and container specialist. Verifies that the generated "
                "project actually runs. Analyzes build logs, validates entry points, "
                "confirms preview URLs, and blocks fake runtime success.",
        "status": ACTIVE,
        "implementation": "extended_agents.check_runtime_health() + RUNTIME_ENGINEER_PROMPT",
        "prompt_key": "RUNTIME_ENGINEER_PROMPT",
        "tools": [
            "build_log_analyzer", "entry_point_validator", "preview_url_checker",
            "container_health_check", "runtime_error_detector",
        ],
        "model_tier": "research",
        "inputs": ["files", "build_logs", "mode", "preview_url"],
        "outputs": ["runtime_ok", "can_preview", "issues", "checklist", "entry_point"],
        "called_from": ["POST /api/runtime/health", "_run_build_pipeline (post-coder)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": True,
        "notes": "Added in Phase 2B. Never marks a build as runtime_ok if build logs have errors.",
    },

    # ── 20. Tool Integration Agent ────────────────────────────────────────────
    "tool_integration": {
        "name": "Tool Integration Agent",
        "role": "Manages external API connections, third-party tools, and service connectors. "
                "Verifies env vars are documented for every detected tool.",
        "status": ACTIVE,
        "implementation": "extended_agents.verify_tool_integration()",
        "prompt_key": None,
        "tools": [
            "env_var_checker", "api_key_validator", "tool_detector",
            "integration_registry", "connector_library",
        ],
        "model_tier": None,
        "inputs": ["files", "requested_tools"],
        "outputs": ["detected_tools", "connected_tools", "missing_env_vars",
                    "warnings", "integration_score"],
        "called_from": ["_run_build_pipeline (tool audit pass)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Detects tool usage and validates env configuration.",
    },

    # ── 21. Data Architect Agent ──────────────────────────────────────────────
    "data_architect": {
        "name": "Data Architect Agent",
        "role": "Designs database schemas, data models, auth relationships, and API contracts "
                "for full-stack builds. Produces schema files and migration strategy.",
        "status": ACTIVE,
        "implementation": "extended_agents.analyze_data_architecture() + DATA_ARCHITECT_PROMPT",
        "prompt_key": "DATA_ARCHITECT_PROMPT",
        "tools": [
            "prisma_schema_generator", "sqlalchemy_model_generator",
            "mongoose_schema_generator", "auth_schema_generator",
            "api_contract_generator", "migration_planner",
        ],
        "model_tier": "reasoning",
        "inputs": ["requirements", "mode", "tech_stack", "auth_required", "database_preference"],
        "outputs": ["database", "orm", "models", "auth_strategy", "api_contracts",
                    "schema_files", "env_vars_needed"],
        "called_from": ["_run_build_pipeline (full_stack/api_service/dashboard modes)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Called for full_stack, api_service, dashboard builds.",
    },

    # ── 22. Component Librarian Agent ─────────────────────────────────────────
    "component_librarian": {
        "name": "Component Librarian Agent",
        "role": "Registers and tracks reusable UI components across the build. "
                "Prevents duplication, enforces naming consistency, and maintains "
                "a component inventory.",
        "status": ACTIVE,
        "implementation": "extended_agents.register_components()",
        "prompt_key": None,
        "tools": [
            "react_component_scanner", "html_section_scanner",
            "css_component_scanner", "component_registry",
        ],
        "model_tier": None,
        "inputs": ["files"],
        "outputs": ["component_count", "components", "react_components",
                    "html_sections", "css_components"],
        "called_from": ["_run_build_pipeline (post-coder component audit)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Builds a reusable component registry per project.",
    },

    # ── 23. Prompt Optimizer Agent ────────────────────────────────────────────
    "prompt_optimizer": {
        "name": "Prompt Optimizer Agent",
        "role": "Analyzes user prompts for quality and completeness. Detects vague "
                "requirements, suggests improvements, and can produce optimized "
                "prompt variants for better agent output.",
        "status": ACTIVE,
        "implementation": "extended_agents.analyze_prompt_quality()",
        "prompt_key": None,
        "tools": [
            "prompt_quality_analyzer", "vague_phrase_detector",
            "requirement_extractor", "context_enricher",
        ],
        "model_tier": None,
        "inputs": ["user_prompt"],
        "outputs": ["prompt_quality_score", "issues", "strengths",
                    "suggestions", "optimized_prompt"],
        "called_from": ["Pre-build prompt analysis (non-blocking)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Non-blocking analysis that improves downstream quality.",
    },

    # ── 24. Documentation Agent ───────────────────────────────────────────────
    "documentation": {
        "name": "Documentation Agent",
        "role": "Generates README.md, SETUP.md, and API documentation for every build. "
                "Ensures no build ships without proper documentation.",
        "status": ACTIVE,
        "implementation": "extended_agents.generate_readme() + DOCUMENTATION_PROMPT",
        "prompt_key": "DOCUMENTATION_PROMPT",
        "tools": [
            "readme_generator", "api_doc_generator",
            "setup_guide_generator", "env_var_documenter",
        ],
        "model_tier": "research",
        "inputs": ["files", "project_name", "mode", "tech_stack", "features"],
        "outputs": ["readme_md", "setup_md", "api_docs"],
        "called_from": ["_run_build_pipeline (post-coder, always)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Ensures every build has a README.",
    },

    # ── 25. Export Agent ──────────────────────────────────────────────────────
    "export_agent": {
        "name": "Export Agent",
        "role": "Packages and prepares the build for download/export. "
                "Creates export manifest, excludes unwanted files, and provides "
                "deploy target recommendations.",
        "status": ACTIVE,
        "implementation": "extended_agents.prepare_export_manifest() + EXPORT_PROMPT",
        "prompt_key": "EXPORT_PROMPT",
        "tools": [
            "file_packager", "zip_generator", "manifest_builder",
            "deploy_target_advisor",
        ],
        "model_tier": None,
        "inputs": ["files", "project_name", "version", "mode"],
        "outputs": ["export_ready", "package_name", "file_manifest",
                    "deploy_targets", "recommended_deploy"],
        "called_from": ["POST /api/export", "POST /api/projects/{id}/download"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Used by download/export endpoints.",
    },

    # ── 26. Monitoring Agent ──────────────────────────────────────────────────
    "monitoring": {
        "name": "Monitoring Agent",
        "role": "Analyzes runtime monitoring readiness. Checks for health endpoints, "
                "structured logging, rate limiting, and CORS configuration.",
        "status": ACTIVE,
        "implementation": "extended_agents.analyze_monitoring_readiness()",
        "prompt_key": None,
        "tools": [
            "health_endpoint_checker", "logging_detector",
            "rate_limit_checker", "cors_validator", "error_telemetry_checker",
        ],
        "model_tier": None,
        "inputs": ["files"],
        "outputs": ["has_health_endpoint", "has_logging", "monitoring_score",
                    "issues", "checklist"],
        "called_from": ["_run_build_pipeline (post-coder, backend builds)"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Non-blocking — issues are warnings, not failures.",
    },

    # ── 27. Memory Curator Agent ──────────────────────────────────────────────
    "memory_curator": {
        "name": "Memory Curator Agent",
        "role": "Cleans, compresses, and summarizes project memory state. "
                "Removes stale entries, deduplicates decisions, and caps history "
                "to prevent memory bloat across iterations.",
        "status": ACTIVE,
        "implementation": "extended_agents.curate_memory() + MEMORY_CURATOR_PROMPT",
        "prompt_key": "MEMORY_CURATOR_PROMPT",
        "tools": [
            "memory_cleaner", "memory_compressor",
            "decision_deduplicator", "history_summarizer",
        ],
        "model_tier": "research",
        "inputs": ["project_id", "memory", "iteration_count"],
        "outputs": ["curated_memory", "removed_keys", "summary"],
        "called_from": ["Background memory curation after each iteration"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Runs as background task to keep memory lean.",
    },

    # ── 28. Capability Truth Agent ────────────────────────────────────────────
    "capability_truth": {
        "name": "Capability Truth Agent",
        "role": "Verifies that frontend UI claims about available features "
                "match actual backend capability registry values. "
                "Prevents fake feature advertising.",
        "status": ACTIVE,
        "implementation": "extended_agents.verify_capability_claims() + CAPABILITY_TRUTH_PROMPT",
        "prompt_key": "CAPABILITY_TRUTH_PROMPT",
        "tools": [
            "capability_registry_reader", "frontend_claim_auditor",
            "mismatch_reporter", "ui_action_generator",
        ],
        "model_tier": None,
        "inputs": ["frontend_claims", "capability_registry", "build_mode"],
        "outputs": ["all_claims_truthful", "verified_claims", "false_claims",
                    "capability_snapshot"],
        "called_from": ["Pre-build truth check", "GET /api/capabilities/status"],
        "connected_to_memory": True,
        "connected_to_capability_registry": True,
        "blocks_on_failure": False,
        "notes": "Added in Phase 2B. Critical for honest platform operation.",
    },
}


# ── Mode → Agent Routing Map ──────────────────────────────────────────────────

MODE_AGENT_ROUTING: dict[str, list[str]] = {
    "landing_page": [
        "manager", "product_strategist", "creative_director", "ui_designer",
        "frontend_coder", "logo_agent", "media_director", "qa_agent", "visual_qa",
        "accessibility", "seo_performance", "deployment",
    ],
    "website": [
        "manager", "product_strategist", "creative_director", "ux_architect",
        "ui_designer", "frontend_coder", "logo_agent", "media_director",
        "qa_agent", "visual_qa", "seo_performance", "accessibility", "deployment",
    ],
    "pwa": [
        "manager", "product_strategist", "creative_director", "ux_architect",
        "ui_designer", "frontend_coder", "logo_agent", "qa_agent",
        "accessibility", "deployment",
    ],
    "full_stack": [
        "manager", "product_strategist", "creative_director", "ux_architect",
        "ui_designer", "frontend_coder", "backend_coder", "data_architect",
        "logo_agent", "security", "qa_agent", "visual_qa", "deployment",
        "documentation", "monitoring",
    ],
    "dashboard": [
        "manager", "product_strategist", "ux_architect", "ui_designer",
        "frontend_coder", "backend_coder", "data_architect", "security",
        "qa_agent", "deployment", "monitoring",
    ],
    "api_service": [
        "manager", "product_strategist", "ux_architect",
        "backend_coder", "data_architect", "security", "qa_agent",
        "deployment", "monitoring", "documentation",
    ],
    "3d_website": [
        "manager", "product_strategist", "creative_director",
        "frontend_coder", "motion_3d", "qa_agent", "visual_qa",
        "accessibility", "deployment",
    ],
    "animated_site": [
        "manager", "product_strategist", "creative_director", "ui_designer",
        "frontend_coder", "motion_3d", "logo_agent", "qa_agent", "visual_qa",
        "accessibility", "deployment",
    ],
    "repo_fix": [
        "manager", "repo_engineer", "qa_agent", "security", "deployment",
    ],
    "media_page": [
        "manager", "product_strategist", "creative_director", "ui_designer",
        "frontend_coder", "media_director", "motion_3d", "qa_agent", "visual_qa",
        "accessibility", "seo_performance", "deployment",
    ],
}


# ── Prompt detection for motion/3D activation ────────────────────────────────

MOTION_TRIGGER_KEYWORDS: set[str] = {
    "3d", "three.js", "threejs", "react three", "three fiber",
    "particles", "particle", "animation", "animated", "framer",
    "gsap", "motion", "interactive", "parallax", "scroll animation",
    "video background", "video bg", "webgl", "canvas animation",
    "cinematic", "immersive", "floating",
}

BACKEND_TRIGGER_MODES: set[str] = {
    "full_stack", "api_service", "automation_bot",
    "trading_bot_scaffold", "dashboard", "admin_panel",
}

SECURITY_TRIGGER_MODES: set[str] = {
    "full_stack", "api_service", "dashboard", "admin_panel",
}


def needs_motion_agent(prompt: str, mode: str) -> bool:
    """Return True if the build prompt requires the Motion/3D agent."""
    p = prompt.lower()
    return any(kw in p for kw in MOTION_TRIGGER_KEYWORDS) or mode in ("3d_website", "animated_site")


def needs_backend_coder(mode: str, auth_required: bool = False) -> bool:
    """Return True if the build requires the Backend Coder agent."""
    return mode in BACKEND_TRIGGER_MODES or auth_required


def needs_security_agent(mode: str, auth_required: bool = False) -> bool:
    """Return True if the build requires the Security agent."""
    return mode in SECURITY_TRIGGER_MODES or auth_required


def get_agent_routing(mode: str, prompt: str = "", auth_required: bool = False) -> list[str]:
    """Return the ordered list of agent roles for a given build mode.

    Handles dynamic additions (motion, backend, security) based on prompt analysis.
    """
    # Normalize mode
    m = mode.lower().strip()
    # Map 3D/animation mode variants
    if any(kw in (prompt or "").lower() for kw in ("3d", "three.js", "threejs", "react three")):
        m = "3d_website"
    elif any(kw in (prompt or "").lower() for kw in ("particle", "animation", "animated", "framer", "gsap")):
        m = "animated_site"

    route = list(MODE_AGENT_ROUTING.get(m, MODE_AGENT_ROUTING.get("website", [])))

    # Inject dynamic agents
    if needs_motion_agent(prompt or "", m) and "motion_3d" not in route:
        try:
            idx = route.index("frontend_coder") + 1
        except ValueError:
            idx = len(route)
        route.insert(idx, "motion_3d")

    if needs_backend_coder(m, auth_required) and "backend_coder" not in route:
        try:
            idx = route.index("frontend_coder") + 1
        except ValueError:
            idx = len(route)
        route.insert(idx, "backend_coder")

    if needs_security_agent(m, auth_required) and "security" not in route:
        route.append("security")

    return route


# ── Registry queries ──────────────────────────────────────────────────────────

def get_agent(agent_id: str) -> dict[str, Any] | None:
    """Return the registry entry for an agent by ID."""
    return AGENT_REGISTRY.get(agent_id)


def get_all_agents() -> dict[str, dict[str, Any]]:
    """Return the complete agent registry."""
    return dict(AGENT_REGISTRY)


def get_agents_by_status(status: str) -> dict[str, dict[str, Any]]:
    """Return all agents with the given status."""
    return {k: v for k, v in AGENT_REGISTRY.items() if v["status"] == status}


def get_agent_status_summary() -> dict[str, Any]:
    """Return a summary of agent status counts and missing wiring."""
    active = [k for k, v in AGENT_REGISTRY.items() if v["status"] == ACTIVE]
    deterministic = [k for k, v in AGENT_REGISTRY.items() if v["status"] == DETERMINISTIC]
    partial = [k for k, v in AGENT_REGISTRY.items() if v["status"] == PARTIAL]
    planned = [k for k, v in AGENT_REGISTRY.items() if v["status"] == PLANNED]

    not_memory = [k for k, v in AGENT_REGISTRY.items() if not v.get("connected_to_memory")]
    not_registry = [k for k, v in AGENT_REGISTRY.items() if not v.get("connected_to_capability_registry")]

    return {
        "total": len(AGENT_REGISTRY),
        "active": len(active),
        "deterministic": len(deterministic),
        "partial": len(partial),
        "planned": len(planned),
        "active_agents": active,
        "deterministic_agents": deterministic,
        "partial_agents": partial,
        "planned_agents": planned,
        "not_connected_to_memory": not_memory,
        "not_connected_to_capability_registry": not_registry,
        "all_required_present": len(planned) == 0,
        # Phase 2B acceptance checks
        "phase_2b_complete": (
            len(partial) == 0
            and AGENT_REGISTRY.get("media_director", {}).get("status") == ACTIVE
            and AGENT_REGISTRY.get("deployment", {}).get("status") == ACTIVE
            and AGENT_REGISTRY.get("accessibility", {}).get("status") == ACTIVE
            and AGENT_REGISTRY.get("seo_performance", {}).get("status") == ACTIVE
            and "runtime_engineer" in AGENT_REGISTRY
            and "capability_truth" in AGENT_REGISTRY
        ),
        "checked_at": _now(),
    }
