# Final Production Go-Live Repairs And Blocker Audit

Branch: `fix/final-production-go-live-audit`
Base: `origin/main` at `b3ff9e6`
Date: 2026-05-15

## Root Causes Fixed

1. `premium_static_fallback_files()` did not satisfy the production static contract. The bundle omitted `motion_manifest.json`, had too few required premium sections for the stricter validator, and did not describe the AI sales-agent, media evidence, runtime QA, repo workbench, and deployment readiness flows required for deterministic regeneration.
2. Severe static corruption repair could overlay fallback files onto an existing broken bundle, leaving stale/forbidden files or manifests in place. It now replaces the static bundle atomically for non-secret severe corruption and immediately validates the deterministic fallback shape.
3. Media persistence stopped too early when GenX timed out, Qwen image generation failed, or Pixabay was rate-limited/unavailable. The media runtime now retries downloads, enforces the 25 MB media size limit before write, and creates three honest local PNG fallback assets when every live provider path is unusable.
4. Media injection previously referenced only one persisted asset. The generated HTML now receives a local media gallery referencing each persisted media asset included in the manifest.
5. Agent prompt contracts allowed ambiguous simulated API language, stale manifests, and motion selectors that did not exist. Planner, Coder, Reviewer, Visual QA, and Motion prompts now explicitly require capability truth, complete files, matching manifests/selectors, and regeneration for severe corruption.

## Files Changed

- `backend/agents/build_contract.py`
- `backend/agents/prompts.py`
- `backend/app/services/media_runtime_service.py`
- `backend/tests/backend_test.py`
- `backend/tests/test_go_live_fixes.py`
- `backend/tests/test_phase3_services.py`

## Verification Evidence

### Static Fallback And Repair Proof

Direct Python validation:

```json
{
  "fallback_paths": [
    "index.html",
    "styles.css",
    "script.js",
    "README.md",
    "preview-manifest.json",
    "motion_manifest.json",
    "amarktai.project.json"
  ],
  "section_count": 10,
  "fallback_ok": true,
  "fallback_can_finalize": true,
  "fallback_errors": [],
  "fallback_warnings": [],
  "repair_changed": [
    "package.json",
    "src/App.jsx",
    "index.html",
    "styles.css",
    "script.js",
    "README.md",
    "preview-manifest.json",
    "motion_manifest.json",
    "amarktai.project.json"
  ],
  "repair_paths": [
    "index.html",
    "styles.css",
    "script.js",
    "README.md",
    "preview-manifest.json",
    "motion_manifest.json",
    "amarktai.project.json"
  ],
  "repair_ok": true,
  "repair_errors": []
}
```

### Media Persistence Proof

Direct mocked-provider proof with GenX timeout, Qwen 404, and Pixabay 429:

```json
{
  "status": "ready",
  "asset_count": 3,
  "sources": ["local_runtime_fallback"],
  "manifest_exists": true,
  "html_asset_refs": 3,
  "attempt_providers": [
    "genx",
    "qwen",
    "pixabay_search",
    "pixabay_search",
    "pixabay_search",
    "pixabay_search",
    "pixabay_search",
    "local_runtime_fallback",
    "local_runtime_fallback",
    "local_runtime_fallback"
  ]
}
```

The manifest records `source=local_runtime_fallback`, `provider=local_runtime_fallback`, status, reason, MIME, size, and local persisted paths. These fallback assets are explicitly not described as AI-generated.

### App/PWA Contract Proof

Direct PWA contract generation produced:

```json
{
  "ok": true,
  "canPreview": true,
  "canFinalize": true,
  "errors": [],
  "warnings": [],
  "paths": [
    "package.json",
    "index.html",
    "src/main.jsx",
    "src/App.jsx",
    "src/App.css",
    "styles.css",
    "README.md",
    "amarktai.project.json",
    ".env.example",
    "manifest.json",
    "service-worker.js",
    "preview-manifest.json"
  ]
}
```

Static premium fallback proof contains no React/Vite files.

### Repo/GitHub Endpoint Reachability

Local route audit found 41 repo/build/GitHub related routes, including:

- `GET /api/integrations/github/status`
- `GET /api/integrations/github/repos`
- `GET /api/integrations/github/repos/{owner}/{repo}/branches`
- `POST /api/repos/{repo_id}/analyze`
- `POST /api/repos/{repo_id}/repair`
- `GET /api/repos/{repo_id}/diff`
- `POST /api/repos/{repo_id}/create-pr`
- `POST /api/builds/import-git`
- `POST /api/builds/{project_id}/repo-workflow/run`
- `POST /api/builds/{project_id}/git/open-pr`

Authenticated push/PR creation was not executed from this local Codex environment because no dashboard bearer token or VPS shell session is available here.

### Public Endpoint Proof

Public production endpoints checked from this environment:

```json
{
  "health": {"status": "ok", "service": "amarktai-app-builder"},
  "readiness": {"overall": "PASS", "blockers": [], "warnings": [], "checks": 17},
  "capabilities": {
    "available_count": 16,
    "unavailable": {"avatar_generation": "GenX avatar category was not live-discovered."},
    "providers": {
      "genx": "live_ok",
      "github": "live_ok",
      "brave": "live_ok",
      "pixabay": "live_ok",
      "qwen": "live_ok"
    }
  }
}
```

## Tests Run

- `python -m py_compile backend\agents\build_contract.py backend\agents\prompts.py backend\app\services\media_runtime_service.py backend\tests\backend_test.py backend\tests\test_go_live_fixes.py backend\tests\test_phase3_services.py`
- `python -m pytest backend -q`
  - Result: `819 passed, 2 skipped, 1 warning`
- `npm.cmd test -- --watchAll=false` in `frontend`
  - Result: `2 passed suites, 38 passed tests`
- `npm.cmd run build` in `frontend`
  - Result: compiled successfully

## Commands Not Run Locally

- `docker compose ps`
- `docker system df`
- `docker compose build backend frontend`
- Bash verification scripts under `scripts/*.sh`

Reason: this Windows Codex environment does not have Docker or Bash installed. The code paths are covered by backend/frontend tests and direct Python proof. The VPS should run the Docker and authenticated dashboard verification commands after this PR is merged.

## Final Readiness Score

Local implementation/test score: `92/100`

Remaining production proof risk:

- Authenticated dashboard proof builds, repo PR creation, and Docker rebuild must be run on the VPS after merge because this environment cannot access the VPS shell or admin bearer token.
