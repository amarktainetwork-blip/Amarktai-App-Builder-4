# Final Media Runtime Evidence

Implemented runtime path:
- `backend/app/services/media_runtime_service.py` executes GenX/Qwen OpenAI-compatible image generation first and Pixabay image/video fallback when provider image generation is unavailable.
- Pixabay 200/mock responses are downloaded, validated through `agents.media_storage.validate_upload`, persisted under workspace `media/`, and listed in `media_manifest.json`.
- `inject_media_assets()` updates static HTML/CSS with `data-amarktai-media-asset` references so generated pages actually use persisted files.
- `backend/agents/orchestrator.py` calls the media runtime for media-required/premium builds, persists `media_runtime`/`media_manifest` to Mongo, emits dashboard events, and syncs injected static files back to the project file store.

Tests:
- `backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_pixabay_mock_response_persists_manifest_and_injects_assets`
- `backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices::test_media_injects_persisted_assets`
- `backend/tests/test_phase3_services.py::TestQualityGateService::test_media_and_motion_checks_pass_with_real_files`

Gate behavior:
- Premium/media builds block when `media_manifest.json` is missing or contains zero existing local assets.
- CSS/SVG-only fallback does not satisfy `check_media_manifest()`.
