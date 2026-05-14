# Final Quality Gate Evidence

Implemented gate behavior:
- Premium builds require runtime QA, media manifest, motion manifest, preview manifest, entry point, README, no hardcoded secrets, and no broken local media references.
- Strict gates promote placeholder copy, dead CTAs, missing viewport/alt basics, missing preview manifest, broken assets, and template contamination to blockers.
- Reviewer failures are fail-closed for premium builds: malformed JSON, oversized output, unsupported verdicts, and `needs_regeneration` prevent ready/finalize states.
- Fallback-only Coder output remains previewable recovery work but cannot be marked ready.

Template contamination:
- `finance.html`, `inventory.html`, and `vehicle-detail.html` are blocked in non-automotive prompts and allowed only for automotive/dealership intent.

Tests:
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_strict_gate_blocks_placeholder_dead_cta_and_broken_asset`
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_template_contamination_only_allowed_for_automotive_prompts`
- `backend/tests/backend_test.py::test_premium_reviewer_invalid_json_blocks_ready_state`
- Existing fallback-readiness tests verify fallback output cannot become ready.
