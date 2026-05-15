# Final Go-Live Runtime Media Proof

Branch: `fix/final-go-live-runtime-media-proof`

## Runtime Truth Implemented

- Added live GenX runtime discovery for `/v1/models` plus `/api/v1/models?category=image|video|voice|audio|avatar`.
- Wired provider probes and `CapabilityTruthService` to consume GenX category counts and runtime capabilities.
- Added secured `GET /api/genx/runtime/status` for authenticated runtime catalog proof.
- Removed stale GenX image catalog assumptions from the static capability registry; runtime media model IDs now come from live discovery.

## Media Execution Implemented

- Added GenX async media job execution for `POST /api/v1/generate` and `GET /api/v1/jobs/{job_id}`.
- Media runtime now tries GenX first, Qwen second, and Pixabay last.
- Persisted GenX job metadata into `media_manifest.json`: provider, model, job ID, status, result URL, mime, size, and local path.
- CSS/SVG placeholders are still excluded from approved premium media counts.

## Verification Coverage

- Tests cover GenX runtime category discovery, capability truth using GenX media categories, GenX async job payload handling, GenX media persistence metadata, and Pixabay fallback manifest injection.
- `python -m py_compile backend/app/services/genx_live_probe_service.py backend/app/services/genx_runtime_service.py backend/app/services/live_probe_service.py backend/app/services/capability_truth_service.py backend/app/services/genx_model_sync.py backend/app/services/media_runtime_service.py backend/server.py` passed.
- `python -m pytest backend -q` passed: 814 passed, 2 skipped.
- `npm.cmd test -- --watchAll=false` passed: 38 frontend tests passed.
- `npm.cmd run build` passed and produced an optimized frontend build.
- `docker compose build backend frontend` was not available in this local Windows environment because Docker is not installed on PATH; VPS deploy verification is covered by `scripts/verify_production_runtime.sh`.
- Live VPS endpoint execution still requires deployed secrets and authenticated calls:
  - `curl -H "Authorization: Bearer $AMARKTAI_TOKEN" https://builder.amarktai.com/api/genx/runtime/status`
  - `curl https://builder.amarktai.com/api/capabilities/status`
  - `curl https://builder.amarktai.com/api/readiness`

## VPS Deploy Commands

```bash
cd /var/www/amarktai/repo
git fetch origin main
git checkout main
git reset --hard origin/main
git fetch origin fix/final-go-live-runtime-media-proof
git checkout fix/final-go-live-runtime-media-proof
docker compose build backend frontend
docker compose up -d
curl -s https://builder.amarktai.com/api/readiness | python3 -m json.tool
curl -s https://builder.amarktai.com/api/capabilities/status | python3 -m json.tool
AMARKTAI_TOKEN=<admin-token> scripts/verify_production_runtime.sh
```
