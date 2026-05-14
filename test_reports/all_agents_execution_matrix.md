# All Agents Execution Matrix
Generated: 2026-05-14

## Implemented in this PR
- GitHub repo listing endpoint using dashboard-managed GITHUB_PAT.
- GitHub branch listing endpoint with owner/repo validation.
- Repo Workbench dashboard browse/search/select/branch clone flow.
- Build-storage PR creation guard requiring a verified branch diff.
- GitHub PR URL persistence to project and build workspace metadata.
- Safe command runner allowlist extended for git status/diff/log/branch and env-gated docker compose config/build.
- Frontend package dependencies for GSAP, Three.js, React Three Fiber, axe-core, Playwright test, and Lighthouse.
- Backend Playwright dependency and Docker Chromium install step.

## Hard Blockers Still Present
- `accessibility`: registry still describes static or future runtime behavior; full Playwright/axe/Lighthouse wiring must replace that implementation before claiming complete runtime QA.
- `visual_qa`: registry still describes static or future runtime behavior; full Playwright/axe/Lighthouse wiring must replace that implementation before claiming complete runtime QA.

## Agent Table
| Agent | Status | Prompt | Called From | Tools | Hard Blocker |
| --- | --- | --- | --- | --- | --- |
| `accessibility` | active | - | _validate_contract (via quality_validator._score_accessibility()) | axe_core_static, aria_checker, contrast_validator, keyboard_nav_checker, semantic_html_validator, label_checker | YES |
| `backend_coder` | active | BACKEND_CODER_PROMPT | _run_build_pipeline (full_stack/api_service mode) | fastapi, express, jwt, bcrypt, prisma, postgres | no |
| `capability_truth` | active | CAPABILITY_TRUTH_PROMPT | Pre-build truth check, GET /api/capabilities/status | capability_registry_reader, frontend_claim_auditor, mismatch_reporter, ui_action_generator | no |
| `component_librarian` | active | - | _run_build_pipeline (post-coder component audit) | react_component_scanner, html_section_scanner, css_component_scanner, component_registry | no |
| `creative_director` | active | - | _run_build_pipeline | design_engine, design_dna, brand_palette, typography_system, layout_archetypes, diversity_checker | no |
| `data_architect` | active | DATA_ARCHITECT_PROMPT | _run_build_pipeline (full_stack/api_service/dashboard modes) | prisma_schema_generator, sqlalchemy_model_generator, mongoose_schema_generator, auth_schema_generator, api_contract_generator, migration_planner | no |
| `deployment` | active | - | _run_build_pipeline (final step), POST /api/deploy/validate | docker_validator, env_template_checker, build_script_validator, sandbox_preview, build_log_streaming, deploy_instruction_generator | no |
| `documentation` | active | DOCUMENTATION_PROMPT | _run_build_pipeline (post-coder, always) | readme_generator, api_doc_generator, setup_guide_generator, env_var_documenter | no |
| `export_agent` | active | EXPORT_PROMPT | POST /api/export, POST /api/projects/{id}/download | file_packager, zip_generator, manifest_builder, deploy_target_advisor | no |
| `frontend_coder` | active | CODER_PROMPT | _run_build_pipeline | react, vite, nextjs, tailwind, framer_motion, lucide_icons | no |
| `logo_agent` | active | - | POST /api/logo, shared_context in build pipeline | svg_generation, genx_image_generation, media_library, favicon_generation, brand_colors | no |
| `manager` | active | BUILD_PLANNER_PROMPT | _run_build_pipeline | project_memory, capability_registry, task_checklist, worker_assignment, completion_guard | no |
| `media_director` | active | - | _run_build_pipeline (media_manifest in shared_context) | pixabay_images, pixabay_videos, genx_image_generation, qwen_image_generation, svg_generation, media_library | no |
| `memory_curator` | active | MEMORY_CURATOR_PROMPT | Background memory curation after each iteration | memory_cleaner, memory_compressor, decision_deduplicator, history_summarizer | no |
| `monitoring` | active | - | _run_build_pipeline (post-coder, backend builds) | health_endpoint_checker, logging_detector, rate_limit_checker, cors_validator, error_telemetry_checker | no |
| `motion_3d` | active | MOTION_3D_PROMPT | _run_build_pipeline (when 3D/animation detected in prompt) | three_js, framer_motion, gsap, particle_systems, css_animations, video_backgrounds | no |
| `product_strategist` | active | SCOUT_PROMPT | _run_build_pipeline | web_search, project_memory, requirements_extraction, feature_planning, audience_detection | no |
| `prompt_optimizer` | active | - | Pre-build prompt analysis (non-blocking) | prompt_quality_analyzer, vague_phrase_detector, requirement_extractor, context_enricher | no |
| `qa_agent` | active | REVIEWER_PROMPT | _run_build_pipeline, run_retry | html_validator, css_validator, link_checker, coverage_score, build_contract_validator | no |
| `repo_engineer` | active | REPO_FIX_PROMPT | _run_repo_fix, repo_repair endpoint | github_pat, repo_clone, stack_detection, diff_generation, pr_creation, repair_engine | no |
| `runtime_engineer` | active | RUNTIME_ENGINEER_PROMPT | POST /api/runtime/health, _run_build_pipeline (post-coder) | build_log_analyzer, entry_point_validator, preview_url_checker, container_health_check, runtime_error_detector | no |
| `security` | active | SECURITY_PROMPT | _run_build_pipeline (when auth_required or full_stack) | secret_scanner, auth_pattern_checker, dependency_audit, xss_detector, injection_checker | no |
| `seo_performance` | active | - | _validate_contract (via quality_validator._score_seo() + _score_performance()) | meta_tag_checker, og_tag_validator, twitter_card_validator, heading_hierarchy_checker, image_optimization_checker, lazy_loading_checker | no |
| `tool_integration` | active | - | _run_build_pipeline (tool audit pass) | env_var_checker, api_key_validator, tool_detector, integration_registry, connector_library | no |
| `ui_designer` | active | PREMIUM_SECTION_LIBRARY | _run_build_pipeline | design_tokens, responsive_breakpoints, component_library, section_templates, spacing_system, typography_scale | no |
| `ux_architect` | active | ARCHITECT_PROMPT | _run_build_pipeline | stack_engine, file_plan, route_design, component_inventory, tech_stack_selection | no |
| `visual_qa` | active | VISUAL_QA_PROMPT | _run_build_pipeline (post-build gate) | layout_checker, typography_validator, contrast_checker, responsive_tester, quality_scorer | YES |
| `worker` | active | - | Orchestrator via _run_agent() | all_agent_tools | no |
