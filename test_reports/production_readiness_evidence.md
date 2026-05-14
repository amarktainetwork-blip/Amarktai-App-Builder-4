# Production Readiness Evidence

Generated: 2026-05-14

## Implemented in This PR

- PR creation is no longer allowed without a verified branch diff.
- GitHub repo/branch browsing uses settings/env runtime secret resolution and never exposes PAT values.
- Docker compose commands in the command runner require an explicit environment gate.

## Verification Run

- Backend compile check PASS.
- Backend phase 3 service tests PASS.

## Hard Blocker

- Full production mode (`APP_ENV=production`) was not live-verified in this local Codex environment. Docker is not assumed healthy until `docker compose build` and authenticated endpoint checks pass on the VPS.

## Additional Verification

- python -m pytest -q PASS: 789 passed, 2 skipped, 1 warning.
- cd frontend; npm.cmd test -- --watchAll=false PASS: 34 passed.
- cd frontend; npm.cmd run build PASS.
- docker --version BLOCKED locally: Docker CLI is not installed in this Codex environment.
- python -m pip show playwright reports not installed on host Python; backend Dockerfile installs it inside the container from backend/requirements.txt.




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
