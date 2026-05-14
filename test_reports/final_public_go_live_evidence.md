# Final Public Go-Live Evidence

Date: 2026-05-14

## Local Verification

- `python -m py_compile backend/config.py backend/agents/orchestrator.py backend/agents/build_contract.py`
  - Passed.
- `python -m pytest backend/tests/test_go_live_fixes.py backend/tests/backend_test.py::test_build_pipeline_missing_audience_reaches_architect_and_coder backend/tests/backend_test.py::test_build_pipeline_malformed_coder_output_uses_fallback_preview backend/tests/backend_test.py::test_run_agent_blocks_non_coder_uses_new_error_and_sanitized_snippet backend/tests/backend_test.py::test_create_branch_pr_body_includes_scores backend/tests/backend_test.py::test_finalize_allows_full_coverage_for_full_app_completion -q`
  - Passed: 14 passed, 1 warning.
- `python -m pytest -q`
  - Passed: 774 passed, 2 skipped, 1 warning.
- `npm.cmd test -- --watchAll=false src/lib/readiness.test.js`
  - Passed: 2 tests.
- `npm.cmd run build`
  - Passed: frontend production build compiled successfully.

## Docker Verification

- `docker --version`
  - Not available in this local Windows Codex environment: Docker command not found.
  - Required follow-up on VPS: `docker compose build backend frontend && docker compose up -d`.

## Live Public Endpoint Verification

Checked against `https://builder.amarktai.com` before deploying this branch:

- `GET /api/health`
  - 200
  - Response status: `ok`
- `GET /api/readiness`
  - 200
  - Overall: `WARN`
  - Blockers: `[]`
  - Providers: GenX, GitHub, Brave, Pixabay, and Qwen `live_ok`
  - Remaining warning: live environment still reports development mode.
- `GET /api/capabilities/status`
  - 200
  - Capabilities available, providers live_ok.
- `GET /api/builds` without bearer token
  - 401 `Missing bearer token`
  - Expected auth-gated behavior, not 404.

## Regression Evidence

Covered by automated tests:

- malformed Coder output falls back to generated files;
- markdown file fences without paths are extracted;
- markdown heading paths before fences are extracted;
- single/fenced JSON remains valid JSON;
- fallback writes previewable files plus `README.md` and `quality_report.md`;
- normal pipeline writes `quality_report.md`;
- missing audience/target_audience still reaches Architect and Coder;
- production static config permits settings-backed GenX and does not fatal before readiness;
- frontend readiness WARN with no blockers allows builds;
- mocked GitHub PR body includes quality and coverage evidence.

## Honest Live Limitation

Authenticated dashboard build, VPS Docker deploy, and live Finalize & Push could not be executed from this environment because no dashboard bearer token, VPS SSH key, or local Docker runtime is available here. Those steps are documented for post-merge VPS verification.
