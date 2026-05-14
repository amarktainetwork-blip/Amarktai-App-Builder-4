# Final Runtime Implementation Evidence

Generated: 2026-05-14

## Runtime Qa
- backend/app/services/runtime_qa_service.py runs Playwright Chromium against static entrypoints
- axe-core is injected into the Playwright page when axe.min.js is available
- Lighthouse CLI is executed from the backend container PATH and scores are persisted
- backend Dockerfile installs node/npm, lighthouse, Playwright Chromium and dependencies
- runtime QA is exposed through /api/builds/{project_id}/runtime-qa and strict quality gates
- Workspace dashboard displays runtime QA screenshots, accessibility, performance, blockers

## Media
- backend/app/services/media_runtime_service.py calls OpenAI-compatible GenX/Qwen image endpoints when keys/models exist
- Pixabay image/video fallback downloads real assets when configured
- Assets are validated, saved under workspace media/, and media_manifest.json is persisted
- Media assets are injected into static HTML/CSS when generated output omitted them
- Media runtime endpoint persists media evidence to the project

## Motion
- backend/app/services/motion_runtime_service.py patches generated files with CSS/canvas motion runtime
- motion_manifest.json is produced and emitted by orchestrator for prompts requiring motion/3D
- Reduced-motion support is included in patched CSS
- Strict quality gate requires motion_manifest and source animation evidence when motion is required

## Repo Workbench
- Repo listing/branch listing endpoints and dashboard browse UI exist
- Build Storage clone/import, command runner, repair diff/apply, versioning, logs, quality gate endpoints exist
- New repo-workflow endpoint analyzes, plans, diffs/applies workflow docs, runs build/tests, persists status
- Empty PRs are blocked and failed test/build/quality statuses block PR unless allow_failing_pr is explicit
- PR URL persists to project and workspace metadata

## Idea Builder
- Idea Builder chat persists sessions/messages in backend
- Final prompt generation exists
- Idea Builder handoff passes prompt, project name, mode, premium quality tier, media choice, and session id into New Build

## Production
- Readiness checks Playwright and Lighthouse runtime availability in production
- Dashboard-managed secrets remain the runtime truth through _runtime_secret/safe_get_secret
- Verification scripts added for production runtime, repo workbench, and premium build smoke

## Verification Commands Added
- scripts/verify_production_runtime.sh
- scripts/verify_repo_workbench_live.sh
- scripts/verify_premium_build_live.sh


## Phase 4 Runtime Wiring Update

Implemented after PR #9 initial opening:
- Browser runtime QA service now executes Playwright Chromium, injects axe-core when available, runs Lighthouse CLI, captures screenshots/console/accessibility/performance evidence, and persists `runtime-qa/runtime-qa-report.json`.
- Backend Dockerfile installs Node/npm, Lighthouse, Playwright Chromium, and browser dependencies.
- Production readiness checks now validate Playwright and Lighthouse runtime availability.
- Strict quality gates can require runtime QA, persisted media assets, and motion manifests; premium orchestrator path blocks readiness when strict runtime gates fail.
- Media runtime service calls GenX/Qwen OpenAI-compatible image generation endpoints when configured, uses Pixabay as real asset fallback, persists media files and `media_manifest.json`, and injects saved assets into static generated pages.
- Motion runtime service patches generated files with CSS/canvas animation runtime, supports reduced motion, writes `motion_manifest.json`, and emits motion evidence.
- Repo workflow endpoint analyzes workspace, creates a checkpoint, produces a plan/diff, optionally applies a patch, runs build/test/quality, saves repo workflow evidence, and gates PR creation on clean check status.
- Workspace dashboard now shows runtime QA, media, motion, quality blockers, and evidence state.
- Idea Builder handoff now passes mode, premium tier, media choice, and session id into New Build.
- VPS/live verification scripts added under `scripts/`.

Tests run after this update:
- `python -m py_compile backend/app/services/runtime_qa_service.py backend/app/services/media_runtime_service.py backend/app/services/motion_runtime_service.py backend/app/services/quality_gate_service.py backend/agents/orchestrator.py backend/server.py` PASS
- `python -m pytest backend/tests/test_phase3_services.py -q` PASS: 110 passed
- `python -m pytest -q` PASS: 794 passed, 2 skipped, 1 warning
- `cd frontend && npm.cmd test -- --watchAll=false` PASS: 35 passed
- `cd frontend && npm.cmd run build` PASS

Local tool availability notes:
- Docker CLI is not installed in this Codex Windows environment; Dockerfile and scripts are updated for VPS/container verification.
- Bash is not installed in this Codex Windows environment; scripts are shell scripts intended for VPS/Linux verification.
