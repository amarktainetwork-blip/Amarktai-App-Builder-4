# Final Motion Runtime Evidence

Implemented runtime path:
- `backend/app/services/motion_runtime_service.py` patches generated files deterministically.
- Static builds receive CSS keyframes, reduced-motion support, JS runtime hooks, and `data-amarktai-motion-scene` / `data-motion-runtime` selectors.
- React/source builds receive a `src/motion-runtime.js` helper when source files are present.
- `motion_manifest.json` is written into generated project files and persisted into Mongo by `backend/agents/orchestrator.py`.

Tests:
- `backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_motion_patch_writes_manifest_and_files`
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_media_and_motion_checks_pass_with_real_files`

Gate behavior:
- Premium/motion builds block when `motion_manifest.json` is missing or when no source-level motion implementation is found.
- Repair/persist flow keeps motion files and manifest in the workspace used by runtime QA and preview.
