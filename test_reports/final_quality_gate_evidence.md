# Final Quality Gate Evidence

Implemented gate behavior:
- Premium builds require runtime QA, media manifest, motion manifest, preview manifest, entry point, README, no hardcoded secrets, and no broken local media references.
- Strict gates promote placeholder copy, dead CTAs, missing viewport/alt basics, missing preview manifest, broken assets, and template contamination to blockers.
- Premium/media gates require at least 3 persisted local media assets in `media_manifest.json`.
- Static landing gates forbid React scaffold files and detect truncated HTML, fewer than 8 sections, stub CSS, missing responsive rules, and missing motion hooks.
- Reviewer failures are fail-closed for premium builds: malformed JSON, oversized output, unsupported verdicts, and `needs_regeneration` prevent ready/finalize states.
- Fallback-only Coder output remains previewable recovery work but cannot be marked ready.

Template contamination:
- `finance.html`, `inventory.html`, and `vehicle-detail.html` are blocked in non-automotive prompts and allowed only for automotive/dealership intent.

Tests:
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_strict_gate_blocks_placeholder_dead_cta_and_broken_asset`
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_template_contamination_only_allowed_for_automotive_prompts`
- `backend/tests/test_go_live_fixes.py::test_exact_premium_static_prompt_enforces_no_react_and_complete_artifacts`
- `backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_pixabay_mock_response_persists_manifest_and_injects_assets`
- `backend/tests/backend_test.py::test_premium_reviewer_invalid_json_blocks_ready_state`
- Existing fallback-readiness tests verify fallback output cannot become ready.

## 2026-05-15 Core Runtime Completion Addendum

- Shared final gate blockers are available through `backend/app/services/build_contract_service.py` and are used by generated-workspace persistence plus finalize/push endpoints.
- Static premium builds are blocked by forbidden React scaffold files, missing media/motion/runtime artifacts, placeholder copy, broken links/assets, and missing runtime proof.
- Idea Builder finalization control-character handling is covered by regression test.
