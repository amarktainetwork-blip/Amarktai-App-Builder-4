# Final Media, Motion, and Runtime QA Evidence

Generated: 2026-05-14

## Media
- Runtime service: `backend/app/services/media_runtime_service.py`
- Provider order: GenX image endpoint, Qwen image endpoint, Pixabay image/video fallback.
- Persistence: workspace `media/` files plus `media_manifest.json`.
- Injection: persisted image/video assets are inserted into static `index.html`/CSS with `data-amarktai-media-asset`.
- Mongo/dashboard: orchestrator persists `media_runtime` and emits `media_runtime` events.
- Blocking: strict premium gates require a media manifest with existing local assets.

## Motion
- Runtime service: `backend/app/services/motion_runtime_service.py`
- Static output: CSS keyframes, reduced-motion styles, runtime JS hooks, canvas scene, and `data-amarktai-motion-scene`.
- React/source output: motion runtime helper file when applicable.
- Persistence: `motion_manifest.json` in files, workspace, and Mongo project metadata.
- Blocking: strict premium gates require manifest plus source-level motion evidence.

## Runtime QA
- Runtime service: `backend/app/services/runtime_qa_service.py`
- Browser: Playwright Chromium.
- Accessibility: axe-core injected into the page when available.
- Performance: Lighthouse CLI when available, plus browser performance evidence in report.
- Evidence: desktop/tablet/mobile screenshots, console errors, broken link/media checks, accessibility report, performance report, `runtime-qa-report.json`.
- Dashboard: `frontend/src/pages/Workspace.jsx` `RuntimeEvidencePanel` displays runtime QA, media, and motion evidence.

## Tests
- `python -m pytest backend/tests/test_phase3_services.py::TestQualityGateService backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices backend/tests/backend_test.py::test_premium_reviewer_invalid_json_blocks_ready_state -q`: 22 passed.
- `python -m pytest -q`: 801 passed, 2 skipped.
- `cd frontend && npm.cmd test -- --watchAll=false`: 36 passed.
- `cd frontend && npm.cmd run build`: compiled successfully.
