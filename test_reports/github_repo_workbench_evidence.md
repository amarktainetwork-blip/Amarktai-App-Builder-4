# GitHub Repo Workbench Evidence

Generated: 2026-05-14
Branch: fix/complete-all-agents-github-runtime-production

## Implemented

- Added `backend/app/services/github_repo_service.py` for sanitized GitHub repo and branch browsing with dashboard-managed `GITHUB_PAT`.
- Added `GET /api/integrations/github/repos`.
- Added `GET /api/integrations/github/repos/{owner}/{repo}/branches`.
- Updated `frontend/src/pages/dashboard/RepoWorkbenchPage.jsx` with repo browsing, search, branch selection, and Build Storage clone action.
- Added frontend API clients for repo browsing, branch browsing, Build Storage import, git status/commit/push/open-pr.
- Added branch-diff proof in `git_workspace_service.get_branch_diff()`.
- Hardened `/api/builds/{project_id}/git/open-pr` so it refuses empty/no-diff PR creation and persists successful PR URLs to Mongo project metadata and build workspace metadata.

## Tests Run

- `python -m py_compile backend/app/services/github_repo_service.py backend/app/services/git_workspace_service.py backend/app/services/command_runner_service.py backend/server.py` PASS
- `python -m pytest backend/tests/test_phase3_services.py -q` PASS: 105 passed

## Remaining Hard Blockers

- Authenticated live dashboard repo browse/import/PR acceptance was not run in this Codex environment because no live browser credentials or GitHub PAT were available in the local session.
- Full prompt-to-patch-to-test-to-repair agent chain from the dashboard still requires a dedicated repo-session orchestration UI beyond the implemented browse/import/PR safety work.


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
