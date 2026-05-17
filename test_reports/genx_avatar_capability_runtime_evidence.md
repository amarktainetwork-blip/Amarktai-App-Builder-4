# GenX Avatar Capability Runtime Evidence

Branch: `fix/genx-avatar-capability-runtime`

Base: `origin/main` at `7844055` (`Merge pull request #19 from amarktainetwork-blip/fix/final-phase-all-blockers`)

## Summary

This change teaches capability truth to infer GenX modalities from live model metadata, including multi-modal models that are returned under broad categories. The main production blocker was that `kling-avatar-v2-pro` appeared under the GenX video catalog, while avatar readiness only looked for models from the empty `category=avatar` endpoint.

## Implemented

- Added GenX model capability inference for:
  - text/reasoning/streaming/tool/repo analysis
  - image generation
  - video generation
  - voice/audio generation
  - speech-to-text/audio transcription
  - image-to-video
  - audio+image-to-video
  - avatar generation
- Classified `kling-avatar-v2-pro` as `avatar`, `avatar_generation`, `video`, and `audio_image_to_video` when live-discovered.
- Added capability model indexes and capability counts to GenX runtime discovery.
- Updated capability truth so `/api/capabilities/status` can expose `avatar_generation` with model IDs instead of relying only on the empty avatar endpoint count.
- Added a GenX avatar runtime pipeline:
  - generates/selects avatar image
  - generates voice audio
  - calls `kling-avatar-v2-pro` for image+audio-to-video
  - persists local media files
  - writes `avatar_manifest.json`
  - injects generated avatar video into static output when ready
  - falls back honestly to browser avatar runtime when provider generation fails
- Updated dashboard capability panels to show avatar status, model counts, and discovered GenX catalog summaries.

## Verification

### Python Compile

```bash
python -m py_compile backend/app/services/genx_live_probe_service.py backend/app/services/genx_model_sync.py backend/app/services/capability_truth_service.py backend/app/services/genx_runtime_service.py backend/app/services/avatar_runtime_service.py backend/agents/orchestrator.py backend/server.py
```

Result: PASS

### Targeted Tests

```bash
python -m pytest backend/tests/test_phase3_services.py::TestGenxModelSync backend/tests/test_phase3_services.py::TestGenxRuntimeTruth backend/tests/test_phase3_services.py::TestRuntimeMediaMotionServices -q
```

Result: `35 passed`

### Full Backend Tests

```bash
python -m pytest backend -q
```

Result: `834 passed, 2 skipped, 1 warning`

### Frontend Tests and Build

```bash
cd frontend && npm.cmd test -- --watchAll=false
cd frontend && npm.cmd run build
```

Results:

- `38 passed`
- Production build compiled successfully

### Direct Capability Truth Proof

Mocked GenX runtime containing `kling-avatar-v2-pro`:

```json
{
  "avatar_available": true,
  "avatar_provider": "genx",
  "avatar_models": ["kling-avatar-v2-pro"]
}
```

### Direct Avatar Runtime Proof

Mocked image + audio -> avatar video pipeline:

```json
{
  "status": "ready",
  "model": "kling-avatar-v2-pro",
  "video_path": "media/genx-avatar-video-ccd4181301a9.mp4",
  "manifest_exists": true,
  "video_exists": true,
  "injected": ["index.html"]
}
```

### Live Public Endpoints

```bash
curl.exe -fsS https://builder.amarktai.com/api/health
curl.exe -fsS https://builder.amarktai.com/api/readiness
```

Results:

- Health returned `status=ok`
- Readiness returned `overall=PASS`, no blockers

## Remaining Live Proof

The new avatar classifier/runtime is not deployed until this PR is merged and the VPS is rebuilt. Current live readiness still reflects the pre-PR runtime and therefore reports avatar unavailable even though `kling-avatar-v2-pro` is present under video models. After deployment, verify:

```bash
cd /var/www/amarktai/repo
git fetch origin main
git checkout main
git reset --hard origin/main
docker compose build backend frontend
docker compose up -d
curl -s https://builder.amarktai.com/api/capabilities/status | python3 -m json.tool
```

Expected post-deploy: `summary.avatar_generation.available=true` when `kling-avatar-v2-pro` remains live-discovered.
