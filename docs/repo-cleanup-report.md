# Repo Cleanup Report

Scope: App Builder 4 production hardening branch.

## Checked

- Route mounting and `/api/builds` behavior
- Settings encryption/decryption paths
- Capability registry and capability status endpoints
- Frontend capability displays in Settings, New Build, Overview, and Repo Workbench
- Build storage and preview service paths
- Legacy repo references to App Builder 2/3
- Backup/stale file patterns

## Removed

- `test_result.md`
- `go_live_blockers.json`
- `frontend_readiness_report.json`
- `repo_index_report.json`

Reason: these were tracked root-level audit/report artifacts that referenced the old App Builder 3 repository and were not imported by code, referenced by routes, or used by tests. Keeping them in App Builder 4 made deployment provenance ambiguous.

## Consolidated

- Public capability endpoints now use `CapabilityTruthService`.
- Readiness uses safe secret resolution and provider truth.
- Settings status uses `safe_get_secret`, so one bad encrypted setting no longer crashes dashboards or runtime endpoints.
- Model availability is annotated from provider configuration/live state rather than static registry names.

## Remaining Watch Items

- `capabilities_summary()` and `async_capabilities_summary()` remain for backward-compatible tests and older internal callers. New public runtime endpoints use `CapabilityTruthService`.
- Future cleanup can migrate remaining internal callers to the service, then remove the legacy helpers in a separate low-risk PR.
