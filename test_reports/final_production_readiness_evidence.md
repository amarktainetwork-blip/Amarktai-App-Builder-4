# Final Production Readiness Evidence

Generated: 2026-05-14

## Production Runtime Paths
- `backend/Dockerfile` installs Node/npm, Playwright Chromium, browser dependencies, and Lighthouse.
- `/api/readiness` validates runtime QA tooling availability in the container.
- Dashboard-managed provider secrets remain the runtime truth; environment variables are fallback paths.
- CORS/auth/rate-limit/readiness hardening from the prior production-hardening work remains intact.

## Verification Scripts
- `scripts/verify_production_runtime.sh`
- `scripts/verify_premium_build_live.sh`
- `scripts/verify_repo_workbench_live.sh`
- `scripts/verify_idea_builder_live.sh`
- `scripts/verify_agent_matrix.sh`

## Local Verification Completed
- Python compile: changed backend runtime/orchestrator files compile successfully.
- Backend test suite: `python -m pytest -q` -> 801 passed, 2 skipped, 1 warning.
- Frontend tests: `cd frontend && npm.cmd test -- --watchAll=false` -> 36 passed.
- Frontend production build: `cd frontend && npm.cmd run build` -> compiled successfully.

## VPS Verification Path
Run after deploy:
```bash
export BASE_URL=https://builder.amarktai.com
export AMARKTAI_TOKEN=<admin bearer token>
scripts/verify_production_runtime.sh
scripts/verify_premium_build_live.sh
scripts/verify_repo_workbench_live.sh
scripts/verify_idea_builder_live.sh
scripts/verify_agent_matrix.sh
```

Docker CLI is not present in the local Windows Codex environment, so Docker build execution is delegated to the VPS/container verification script path. The repository implementation includes the Docker installation steps required for the runtime tools.
