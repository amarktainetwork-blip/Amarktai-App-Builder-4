# Final Runtime QA Evidence

Implemented runtime path:
- `backend/app/services/runtime_qa_service.py` runs Playwright Chromium rendering against generated entry files.
- The service captures desktop/tablet/mobile screenshots, browser console errors, broken link/media checks, axe-core accessibility results, and Lighthouse CLI scores when available.
- Reports are persisted under `runtime-qa/` as `runtime-qa-report.json`, `accessibility-report.json`, optional `lighthouse-report.json`, and screenshots.
- `backend/app/services/quality_gate_service.py` invokes runtime QA for strict/premium gates.
- `backend/server.py` exposes `POST /api/builds/{project_id}/runtime-qa` to run QA on demand and persist evidence.
- `frontend/src/pages/Workspace.jsx` displays runtime QA pass/block state, scores, screenshot names, blockers, media evidence, and motion evidence.

Docker/runtime readiness:
- `backend/Dockerfile` installs Playwright Chromium and Lighthouse.
- `/api/readiness` checks Playwright import availability and Lighthouse executable availability.

Tests:
- `backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_runtime_qa_returns_blocker_when_playwright_missing`
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_strict_gate_blocks_without_runtime_media_motion`
- `frontend/src/__tests__/smoke.test.js` verifies dashboard runtime evidence panel wiring.
