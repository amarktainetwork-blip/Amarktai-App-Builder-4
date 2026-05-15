# Final Live Blockers Evidence

Generated: 2026-05-15

## Root Causes Fixed

### Frontend Docker Build
- Root cause: `frontend/Dockerfile` copied `yarn.lock` and ran `yarn install --frozen-lockfile`, so a clean checkout without `frontend/yarn.lock` could not build.
- Fix: Dockerfile now copies `package.json package-lock.json`, runs `npm ci --no-audit --no-fund`, and builds with `npm run build`.
- Build context hardening: root `.dockerignore` and `frontend/.dockerignore` exclude `node_modules`, build outputs, caches, env files, and backup files.
- Test coverage: `test_frontend_dockerfile_does_not_require_missing_yarn_lock` fails if the Dockerfile again requires a missing lockfile.

### Legacy Automotive Template Contamination
- Root cause: active code in `backend/agents/build_contract.py::get_required_files()` and `backend/agents/quality_validator.py::score_project_quality()` mapped generic `inventory`, `vehicle`, and `finance` words to `inventory.html`, `vehicle-detail.html`, and `finance.html` outside automotive intent.
- Fix: `backend/agents/template_policy.py` centralizes `is_automotive_prompt()` and `remove_legacy_template_contamination()`.
- Active path hardening:
  - `get_required_files()` only adds automotive pages for clear automotive/dealership prompts.
  - `ensure_required_files()` strips automotive files from non-automotive repair/fallback paths.
  - `orchestrator.py` strips contamination before file writes and build-storage persistence.
  - `quality_validator.py` and `quality_gate_service.py` block non-automotive contamination.
- Test coverage: non-automotive Amarktai, SaaS, and fighter-style prompts block or strip legacy pages; automotive/dealership prompts still allow them.

### Static Premium Build Contract
- Root cause: `landing_page` still mapped through the React/Vite contract in the active build contract, so static one-page outputs could retain `package.json`, `src/App.jsx`, and stub-level CSS even when the user requested a one-page website.
- Fix: `landing_page` now maps to the static-site contract, static landing pages forbid React scaffold files, and malformed/stub static output is repaired before Reviewer using a deterministic premium static generator.
- The deterministic generator creates complete `index.html`, `styles.css`, `script.js`, `README.md`, `preview-manifest.json`, and `amarktai.project.json` with 8+ sections, motion selectors, responsive CSS, design tokens, and no placeholder copy.
- Safety nuance: secret-like unsafe content is not overwritten by deterministic repair, so security validation still fails instead of being hidden by fallback.

### Media Persistence
- Root cause: media runtime existed, but active orchestration did not sync `media_manifest.json` into project files and did not fail at `media_director` when zero assets were persisted.
- Fix:
  - Orchestrator resolves dashboard-managed secrets safely through `safe_get_secret()`.
  - Media runtime uses GenX/Qwen image generation and Pixabay fallback, downloads up to 3 stock image assets, validates uploads, persists `media/` assets and `media_manifest.json`.
  - Orchestrator writes `media_manifest.json` to the project file store, syncs injected static files back to Mongo/project files, persists `media_runtime` and `media_manifest`, and emits `media_runtime.completed`.
  - Premium/media builds require at least 3 persisted local assets. `asset_count=0` keeps an explicit zero-assets blocker; `asset_count=1` or `2` fails with a minimum-3 blocker.
- Test coverage: mocked Pixabay 200 response persists 3 assets, writes manifest, and injects generated HTML references.

### Runtime QA Persistence
- Root cause: runtime QA wrote a single report but did not create the exact artifact layout expected by live verification.
- Fix:
  - `runtime_qa_service.py` persists screenshots to `runtime-qa/screenshots/desktop.png`, `tablet.png`, and `mobile.png`.
  - It writes `runtime-qa/accessibility-report.json`, `runtime-qa/performance-report.json`, and `runtime-qa/runtime-qa-report.json`.
  - It verifies motion selectors when `motion_manifest.json` exists.
  - Server and orchestrator persist both `runtime_qa` and `runtime_qa_result`.
- Test coverage: mocked Playwright path writes runtime QA reports, screenshots, accessibility/performance files, and motion selector evidence.

### Motion Evidence
- Deterministic motion patching is preserved.
- Runtime QA verifies `data-amarktai-motion-scene` and `data-motion-runtime` selectors when motion is required.
- Strict gates block missing `motion_manifest.json` or missing source-level motion implementation.

### Production Default
- Root cause: `backend/server.py` and `backend/config.py` defaulted missing `APP_ENV` to `development`.
- Fix: backend defaults now target `production`; backend tests explicitly use `APP_ENV=test` through `backend/tests/conftest.py`.
- Compose now requires explicit `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `SETTINGS_ENCRYPTION_KEY` instead of supplying development defaults while `APP_ENV=production`.

## Tests Run
- `python -m py_compile backend/agents/build_contract.py backend/agents/orchestrator.py backend/app/services/quality_gate_service.py backend/config.py backend/server.py backend/tests/test_go_live_fixes.py backend/tests/test_phase3_services.py backend/tests/conftest.py` - passed.
- `python -m pytest -q` - 806 passed, 2 skipped, 1 warning.
- Targeted live-blocker tests - 4 passed.
- `cd frontend && npm.cmd test -- --watchAll=false` - 38 passed.
- `cd frontend && npm.cmd run build` - compiled successfully.
- Git Bash syntax check for verification scripts - passed.

## Docker Verification
- Local Windows Codex environment does not have Docker CLI installed (`docker` command not found).
- The exact live Dockerfile root cause is fixed in source and covered by a smoke test.
- VPS verification scripts now fail on Docker frontend build issues, missing runtime artifacts, APP_ENV development, stale frontend container evidence, and legacy template contamination.

## Verification Scripts
- `scripts/verify_production_runtime.sh`
- `scripts/verify_premium_build_live.sh`
- `scripts/verify_static_premium_builder_live.sh`
- `scripts/verify_repo_workbench_live.sh`
- `scripts/verify_idea_builder_live.sh`
- `scripts/verify_agent_matrix.sh`
- `scripts/verify_no_legacy_template_contamination.sh`
