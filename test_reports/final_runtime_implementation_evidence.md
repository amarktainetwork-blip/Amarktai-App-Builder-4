# Final Runtime Implementation Evidence

Generated: 2026-05-15

## Implemented Runtime Paths
- Runtime QA: backend Playwright Chromium render checks, axe-core browser accessibility scan, screenshot capture, console capture, broken link/media checks, Lighthouse/browser performance evidence, persisted runtime reports, dashboard evidence panel, and strict premium blocking.
- Media: GenX/Qwen image generation adapters, Pixabay image/video fallback, upload validation, workspace asset persistence, `media_manifest.json`, generated-page media injection, Mongo persistence, dashboard evidence, and strict premium media blocking.
- Motion/3D: deterministic file patching, CSS/JS/canvas runtime hooks, reduced-motion support, `motion_manifest.json`, Mongo persistence, dashboard evidence, and strict premium motion blocking.
- Reviewer/QA: compact audit-only Reviewer prompt, response size guard, premium fail-closed behavior for malformed/oversized/unsupported/`needs_regeneration` output, and deterministic regeneration for static contract failures.
- Static landing contract: `landing_page` routes to `static-site`; static one-page builds forbid React scaffold files and require complete HTML/CSS/JS artifacts.
- Quality gates: no fallback-only ready, no media-missing premium ready, no motion-missing premium ready, no runtime-QA-missing premium ready, no placeholder/dead CTA/broken asset/template-contaminated premium ready.
- Repo Workbench: repo/branch listing, import/clone, repo profile/workflow run, patch/diff/check logs, PR gating, PR URL persistence, and self-update safety rules remain covered by existing workflow tests and live scripts.
- Idea Builder: persisted conversations, finalized brief generation, mode/tier/media/session handoff into New Build and Planner context remain covered by existing service/UI tests and live scripts.
- Production: Docker compose defaults `APP_ENV=production`; backend/config default missing `APP_ENV` to production; tests use `APP_ENV=test`.

## Exact Live Prompt Coverage
- Added regression coverage for the exact premium cinematic one-page Amarktai Builder prompt.
- The test feeds truncated HTML, stub CSS, `package.json`, and `src/App.jsx`; the active contract removes React scaffold files and regenerates complete static artifacts before validation.
- Expected generated static files: `index.html`, `styles.css`, `script.js`, `README.md`, `preview-manifest.json`, and `amarktai.project.json`.
- Expected runtime artifacts are enforced by quality gates and live scripts: `media_manifest.json`, `motion_manifest.json`, `runtime-qa/runtime-qa-report.json`, screenshots, accessibility report, and performance report.

## Verification
- `python -m py_compile backend/agents/build_contract.py backend/agents/orchestrator.py backend/app/services/quality_gate_service.py backend/config.py backend/server.py backend/tests/test_go_live_fixes.py backend/tests/test_phase3_services.py backend/tests/conftest.py`: pass.
- `python -m pytest -q`: 806 passed, 2 skipped, 1 warning.
- `python -m pytest -q backend/tests/test_go_live_fixes.py::test_frontend_dockerfile_does_not_require_missing_yarn_lock backend/tests/backend_test.py::test_build_pipeline_missing_audience_reaches_architect_and_coder backend/tests/test_go_live_fixes.py::test_exact_premium_static_prompt_enforces_no_react_and_complete_artifacts backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_pixabay_mock_response_persists_manifest_and_injects_assets`: 4 passed.
- `cd frontend && npm.cmd test -- --watchAll=false`: 38 passed.
- `cd frontend && npm.cmd run build`: compiled successfully.
- Git Bash syntax check: `bash -n scripts/verify_production_runtime.sh scripts/verify_premium_build_live.sh scripts/verify_static_premium_builder_live.sh scripts/verify_no_legacy_template_contamination.sh scripts/verify_agent_matrix.sh scripts/verify_idea_builder_live.sh scripts/verify_repo_workbench_live.sh`: passed.

## Local Environment Note
- Docker CLI is not installed in this Windows Codex environment, so `docker compose build backend frontend` could not be executed locally.
- Docker build failure coverage is implemented through the Dockerfile lockfile regression test and the live verification scripts.

## Verification Scripts
- `scripts/verify_production_runtime.sh`
- `scripts/verify_premium_build_live.sh`
- `scripts/verify_static_premium_builder_live.sh`
- `scripts/verify_no_legacy_template_contamination.sh`
- `scripts/verify_repo_workbench_live.sh`
- `scripts/verify_idea_builder_live.sh`
- `scripts/verify_agent_matrix.sh`

## 2026-05-15 Core Runtime Completion Addendum

Additional active-path fixes in `fix/final-core-runtime-completion`:
- Added `backend/app/services/build_contract_service.py` as the application-facing contract service for static/react contracts and final gate blockers.
- Stack engine static modes now require `script.js` and `preview-manifest.json`, matching the static contract enforced by the orchestrator.
- Premium static/media builds no longer accept CSS/SVG-only media strategy as passing evidence.
- Media runtime now tops up GenX/Qwen output with Pixabay fallback until at least 3 non-SVG local assets are persisted.
- `media_manifest.json` now reports approved non-SVG `asset_count`; stored SVGs do not count as premium media evidence.
- Runtime QA now checks browser-rendered dead anchors, missing anchor targets, broken image loads, and media element errors.
- Finalize and branch-PR endpoints run the shared final gate before pushing to GitHub.
- Idea Builder finalization sanitizes JSON-hostile control characters and can extract `build_prompt`/`final_prompt` from model-returned JSON/fenced JSON.

Verification for this addendum:
- `python -m py_compile ...` for changed backend files: passed.
- `python -m pytest -q`: 808 passed, 2 skipped, 1 warning.
- `frontend npm.cmd test -- --watchAll=false`: 38 passed.
- `frontend npm.cmd run build`: compiled successfully.
- Git Bash `bash -n` verification scripts: passed.
