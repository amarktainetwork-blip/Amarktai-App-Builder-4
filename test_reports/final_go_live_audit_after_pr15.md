# Final Go-Live Audit After PR15

Branch: `fix/final-go-live-after-pr15`

Base deployed source audited locally: `main` at `9f12d08` (`Merge pull request #15 from amarktainetwork-blip/fix/final-go-live-runtime-media-proof`)

## Audit Findings

- PR #15 is present on `main` and includes GenX runtime category discovery, async media job handling, capability truth wiring, and the secured `/api/genx/runtime/status` endpoint.
- Existing gates already block missing persisted media, missing motion manifest, missing runtime QA artifacts, broken local media links, stale automotive template contamination, hardcoded secrets, and placeholder copy.
- A dedicated Content Director/content-quality gate was missing. The active pipeline could rely on reviewer/visual checks without a deterministic report proving product/content alignment, CTA quality, and requested capability coverage.
- Dashboard runtime evidence surfaced QA/media/motion/quality, but did not surface content-quality evidence.

## Fixes Implemented

- Added `backend/app/services/content_quality_service.py`.
- Wired Content Director into `backend/agents/orchestrator.py` after Coder/Motion/Backend Coder and before Reviewer.
- Content Director writes and emits `content_quality_report.json`, updates the project document, and records dashboard events.
- Added content-quality checks to `run_quality_gate`.
- Added final-gate enforcement that premium builds require a passing `content_quality_report.json`.
- Updated the Workspace runtime evidence panel to show Content PASS/BLOCKED, score, section count, CTA count, and blockers.
- Added backend regression tests for wrong-product/generic content blocking and specific product copy passing.
- Added frontend smoke coverage for content-quality dashboard evidence.

## Local Verification

- `python -m py_compile backend/app/services/content_quality_service.py backend/app/services/quality_gate_service.py backend/app/services/build_contract_service.py backend/agents/orchestrator.py` passed.
- `python -m pytest backend -q` passed: `816 passed, 2 skipped`.
- `npm.cmd test -- --watchAll=false` passed: `38 passed`.
- `npm.cmd run build` passed and produced an optimized frontend production build.

## Not Run Locally

- `docker compose build backend frontend` could not run because Docker is not installed on PATH in this Windows Codex environment.
- VPS deploy, authenticated `/api/genx/runtime/status`, live provider probes, premium media job proof, and dashboard-authenticated scripts require VPS access plus a valid admin token.

## Required VPS Proof After Merge

```bash
cd /var/www/amarktai/repo
git fetch origin main
git checkout main
git reset --hard origin/main
docker compose build backend frontend
docker compose up -d
docker compose ps
docker compose logs backend --tail=200
docker compose logs frontend --tail=100
curl -s https://builder.amarktai.com/api/health | python3 -m json.tool
curl -s https://builder.amarktai.com/api/readiness | python3 -m json.tool
curl -s https://builder.amarktai.com/api/capabilities/status | python3 -m json.tool
AMARKTAI_TOKEN=<admin-token> scripts/verify_production_runtime.sh
AMARKTAI_TOKEN=<admin-token> scripts/verify_premium_build_live.sh
AMARKTAI_TOKEN=<admin-token> scripts/verify_static_premium_builder_live.sh
AMARKTAI_TOKEN=<admin-token> scripts/verify_idea_builder_live.sh
AMARKTAI_TOKEN=<admin-token> scripts/verify_repo_workbench_live.sh
scripts/verify_agent_matrix.sh
```

## Remaining Blockers

- No code blocker remains from the local audit.
- Final go-live approval still requires VPS runtime proof with Docker and a valid authenticated admin token. That proof must include GenX category counts, real media job/download evidence, media manifest proof, runtime QA screenshots/reports, and dashboard route checks.
