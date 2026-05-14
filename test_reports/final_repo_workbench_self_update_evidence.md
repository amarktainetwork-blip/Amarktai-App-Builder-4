# Final Repo Workbench Self-Update Evidence

Implemented workflow:
- GitHub PAT validation and repo/branch listing are exposed through backend integration endpoints.
- Repo Workbench UI can search repos, select branches, import/clone, and start repo workflow runs.
- Repo workflow endpoint analyzes workspace profile, creates a checkpoint, plans a patch, applies a safe documented file change, runs allowed install/build/test/quality commands, persists command logs, and stores git status/diff evidence.
- Finalize/Open PR blocks empty diffs and blocks failed checks unless the user explicitly asks for draft/failing PR mode.
- PR URL is persisted to the project document and workspace metadata.

Self-update safety:
- The workflow works in a branch/workspace only.
- It does not auto-merge and does not edit live production files directly.
- `scripts/verify_repo_workbench_live.sh` provides the VPS/dashboard verification path.

Tests:
- `backend/tests/test_phase3_services.py` covers GitHub repo service, command runner allowlist, git diff, Docker command gating, and quality command execution.
- Frontend smoke tests verify Repo Workbench repo/branch UI and API clients.
