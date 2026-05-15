# Final Live Blockers Evidence

Generated: 2026-05-14

## Root Causes Fixed

### Frontend Docker Build
- Root cause: `frontend/Dockerfile` copied `yarn.lock` and ran `yarn install --frozen-lockfile`, so a clean checkout without `frontend/yarn.lock` could not build.
- Fix: Dockerfile now copies `package.json package-lock.json`, runs `npm ci --no-audit --no-fund`, and builds with `npm run build`.
- Build context hardening: added root `.dockerignore` and `frontend/.dockerignore` to exclude `node_modules`, build outputs, caches, env files, and backup files.
- Test coverage: frontend smoke test verifies Dockerfile does not require `yarn.lock`, does require `package-lock.json`, and `.dockerignore` excludes build junk.

### Legacy Automotive Template Contamination
- Root cause: active code in `backend/agents/build_contract.py::get_required_files()` and `backend/agents/quality_validator.py::score_project_quality()` mapped generic `inventory`, `vehicle`, and `finance` words to `inventory.html`, `vehicle-detail.html`, and `finance.html` outside automotive intent.
- Fix: added `backend/agents/template_policy.py` with `is_automotive_prompt()` and `remove_legacy_template_contamination()`.
- Active path hardening:
  - `get_required_files()` only adds automotive pages for clear automotive/dealership prompts.
  - `ensure_required_files()` strips automotive files from non-automotive repair/fallback paths.
  - `orchestrator.py` strips contamination before file writes and before build-storage persistence.
  - `quality_validator.py` fails non-automotive contamination.
  - `quality_gate_service.py` strict gate blocks contamination.
- Test coverage: non-automotive Amarktai/SaaS/fighter-style prompts block or strip legacy pages; automotive/dealership prompts still allow them.

### Media Persistence
- Root cause: media runtime existed, but active orchestration did not sync `media_manifest.json` into project files and did not fail at `media_director` when zero assets were persisted.
- Fix:
  - Orchestrator resolves dashboard-managed secrets safely through `safe_get_secret()`.
  - Media runtime uses GenX/Qwen image generation and Pixabay fallback, downloads up to 3 stock image assets, validates uploads, persists `media/` assets and `media_manifest.json`.
  - Orchestrator writes `media_manifest.json` to the project file store, syncs injected static files back to Mongo/project files, persists `media_runtime` and `media_manifest`, and emits `media_runtime.completed`.
  - Premium/media builds with `asset_count=0` fail with `failed_agent=media_director`.
- Test coverage: mocked Pixabay 200 response persists assets, writes manifest, and injects generated HTML references.

### Runtime QA Persistence
- Root cause: runtime QA wrote a single report but did not create the exact artifact layout expected by live verification.
- Fix:
  - `runtime_qa_service.py` now persists screenshots to `runtime-qa/screenshots/desktop.png`, `tablet.png`, and `mobile.png`.
  - It writes `runtime-qa/accessibility-report.json`, `runtime-qa/performance-report.json`, and `runtime-qa/runtime-qa-report.json`.
  - It verifies motion selectors when `motion_manifest.json` exists.
  - Server and orchestrator persist both `runtime_qa` and `runtime_qa_result`.
- Test coverage: mocked Playwright path writes runtime QA reports, screenshots, accessibility/performance files, and motion selector evidence.

### Motion Evidence
- Existing deterministic motion patching is preserved.
- Runtime QA now verifies `data-amarktai-motion-scene` / `data-motion-runtime` selectors when motion is required.
- Strict gates still block missing `motion_manifest.json` or missing source-level motion implementation.

## Tests Run
- `python -m py_compile backend/agents/template_policy.py backend/agents/build_contract.py backend/agents/quality_validator.py backend/app/services/runtime_qa_service.py backend/app/services/media_runtime_service.py backend/app/services/quality_gate_service.py backend/agents/orchestrator.py backend/server.py` — passed.
- Targeted live-blocker tests — 4 passed.
- `python -m pytest -q` — 804 passed, 2 skipped, 1 warning.
- `cd frontend && npm.cmd test -- --watchAll=false` — 38 passed.
- `cd frontend && npm.cmd run build` — compiled successfully.

## Docker Verification
- Local Windows Codex environment does not have the Docker CLI installed (`docker` command not found).
- The exact live Dockerfile root cause is fixed in source and covered by a smoke test.
- VPS verification script now fails on Docker frontend build issues, missing runtime artifacts, APP_ENV development, stale frontend container evidence, and legacy template contamination.

## Verification Scripts
- `scripts/verify_production_runtime.sh`
- `scripts/verify_premium_build_live.sh`
- `scripts/verify_repo_workbench_live.sh`
- `scripts/verify_idea_builder_live.sh`
- `scripts/verify_agent_matrix.sh`
- `scripts/verify_no_legacy_template_contamination.sh`
