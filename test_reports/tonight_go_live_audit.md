# Tonight Go-Live Pipeline Audit

Date: 2026-05-13

Branch: `fix/tonight-go-live-pipeline-audience-preview`

Source of truth confirmed:

- `origin https://github.com/amarktainetwork-blip/Amarktai-App-Builder-4.git`
- Branch was created from `origin/main` after PR #2 merged.
- Recent main head at audit time: `4aa8ad3 Merge pull request #2 from amarktainetwork-blip/fix/production-deploy-truth-settings-hardening`

## Baseline

- Active backend already included `normalize_build_context()` with `DEFAULT_AUDIENCE`.
- Active orchestrator already injected `scout_data["audience"]` after Scout.
- `/api/builds` is mounted and auth-gated; 401/403 is expected without a bearer token.
- Docker is not installed in this local Codex Windows environment, so Docker syntax/build checks must be run on the VPS.

## Forensic Findings

1. The remaining audience risk was not the normalizer itself. The risk was that normalized context was not enforced as an invariant after every pipeline stage.
2. The pipeline only injected `audience` into Scout data, leaving `target_audience` absent for downstream prompts/metadata that expect that alias.
3. The orchestrator still had direct `normalized_context["audience"]` reads around design direction and creative director setup. A stale or partial context could still surface as `KeyError: 'audience'`, which would be caught at `run_full_build()` and reported as failed agent `pipeline`.
4. Generated app files were stored in MongoDB, but the standard generated-build path did not mirror completed files into `/var/www/amarktai/builds/generated/{project_id}` or run the filesystem quality gate automatically.
5. Readiness performed live provider checks but did not refresh the shared provider probe cache first, so `/api/capabilities/status` could continue to show `not_tested` until `/api/providers/probe` was called.

## Fixes Applied

- Added `ensure_build_context_defaults()` to enforce required build context fields and both audience aliases.
- Added stage-level audience alias enforcement for planner, scout, and architect payloads.
- Replaced direct `normalized_context["audience"]` reads with safe defaulted access.
- Added generated workspace mirroring after validation/coverage.
- Added automatic `preview-manifest.json` generation.
- Added automatic `quality-report.json` generation through `run_quality_gate()`.
- Added project metadata updates for `workspace_path`, `generated_files`, `preview_manifest`, `quality_report`, and `quality_report_path`.
- Updated readiness to refresh provider probe cache before capability truth is returned.

## Tests Added/Updated

- Missing audience and target audience defaulting in `normalize_build_context()` / `ensure_build_context_defaults()`.
- Premium/website pipeline regression where Planner and Scout omit both audience fields and Architect/Coder still run.
- Generated workspace, preview manifest, and quality report assertions on pipeline completion.
- Readiness probe-cache refresh regression.

## Verification Notes

Local focused verification passed:

- `python -m py_compile backend/app/services/build_context_service.py backend/agents/orchestrator.py`
- `python -m py_compile backend/server.py backend/tests/test_settings_capability_hardening.py backend/tests/backend_test.py`
- `python -m pytest -q backend/tests/test_settings_capability_hardening.py backend/tests/test_go_live_fixes.py backend/tests/backend_test.py::test_build_pipeline_emits_coverage_score backend/tests/backend_test.py::test_build_pipeline_missing_audience_reaches_architect_and_coder`
- `python -m pytest -q` -> 767 passed, 2 skipped, 1 warning
- `cd frontend && npm run build` -> compiled successfully

Known local limitation:

- Docker is unavailable locally: `docker` command is not installed.
- Authenticated dashboard premium build verification requires live credentials/session on the VPS dashboard.
- SSH deployment from this environment is blocked: `admin@builder.amarktai.com: Permission denied (publickey)`.

## Live Endpoint Snapshot Before This PR Is Deployed

These calls were run against the currently deployed site before this branch was deployed:

- `GET /api/health` -> 200, `{"status":"ok"}`
- `GET /api/readiness` -> JSON `overall=WARN`; GenX, GitHub PAT, and Brave live checks pass; APP_ENV remains `development`.
- `GET /api/capabilities` -> JSON, but configured providers still show `live_status=not_tested`.
- `GET /api/capabilities/status` -> JSON, only `preview_generation` available because live probe cache is not refreshed.
- `GET /api/providers/status` -> JSON note that no probe results are cached.
- `GET /api/builds` -> 401 `Missing bearer token`, which is correct for unauthenticated access.

The readiness probe-cache fix in this PR specifically targets the deployed `not_tested` mismatch.
