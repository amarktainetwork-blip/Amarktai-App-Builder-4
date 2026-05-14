# Live Pipeline Audience Root Cause

Date: 2026-05-14

## Repo Baseline

- Source of truth: `https://github.com/amarktainetwork-blip/Amarktai-App-Builder-4.git`
- Working branch: `fix/live-build-pipeline-audience-hardening`
- Latest deployed baseline reported by live recovery: `47edacc` (`Merge PR #3 fix/tonight-go-live-pipeline-audience-preview`)

## Symptom

The live dashboard started a build and failed at pipeline level with:

- Failed agent: `pipeline`
- Error: `'audience'`
- Planner UI state remained `thinking / Calling model`
- Scout/Architect/Coder/Reviewer/Advisor stayed idle
- No preview files were generated

## Audit Findings

Searches for raw active-code access to `["audience"]`, `['audience']`, `["target_audience"]`, and `['target_audience']` found no remaining direct unsafe access in the main orchestrator/build-context path after PR #3.

An AST scan did find the only runtime subscript on `audience` in active backend code:

- `backend/agents/project_memory.py`
  - `brand["audience"]`

The server still seeded new projects through `server._empty_project_memory()` with:

```json
{
  "brand": {}
}
```

`agents.project_memory._ensure_schema()` only repaired missing top-level keys. Because `brand` existed as an empty object, it did not add nested keys like `brand.audience`.

When Scout output was merged into project memory, `update_memory_brand()` evaluated `brand["audience"]` and raised `KeyError("audience")`. The outer pipeline catch converted that into the generic failed agent `pipeline`, which explains the live error message.

## Fix

- Made project memory schema repair recursive and type-safe.
- Updated new project memory seeding to use the canonical `make_empty_memory()` shape while preserving legacy extra fields used by existing routes/UI.
- Added a regression pipeline test using a legacy `project_memory: {"brand": {}}` document so missing `audience` cannot regress.
- Committed the readiness gate rule so WARN readiness with no blockers does not prevent live testing.

## Verification Notes

Local verification completed:

- `python -m py_compile backend/agents/project_memory.py backend/server.py backend/agents/orchestrator.py` passed.
- `python -m pytest -q` passed: 768 passed, 2 skipped, 1 warning.
- `npm.cmd install` passed without legacy peer-dep flags.
- `npm.cmd test -- --watchAll=false src/lib/readiness.test.js` passed.
- `npm.cmd run build` passed.

Live public endpoint verification before deploying this branch:

- `GET /api/health`: 200, status `ok`.
- `GET /api/readiness`: 200, overall `WARN`, blockers `[]`, warning only for development mode.
- `GET /api/capabilities/status`: 200, providers live_ok and capabilities available.
- `GET /api/builds`: 401 `Missing bearer token` rather than 404, expected without auth.

Local Docker is unavailable in this Codex Windows environment, so Docker/VPS commands require the live host. Public endpoint verification can be re-run after merge/deploy:

```bash
curl -s https://builder.amarktai.com/api/health | python3 -m json.tool
curl -s https://builder.amarktai.com/api/readiness | python3 -m json.tool
curl -s https://builder.amarktai.com/api/capabilities/status | python3 -m json.tool
curl -i https://builder.amarktai.com/api/builds | head
```
