# Backend Orchestration Go-Live Core

## Quality tiers

Amarktai exposes two public quality tiers:

- **Standard**: Fast, capable generation using efficient high-quality models.
- **Premium**: Best available models, deeper reasoning, richer media, stronger QA.

Legacy project values are accepted safely:

- `cheap` -> `standard`
- `balanced` -> `standard`
- `premium` -> `premium`

Tiers affect model depth, repair budget, and QA strictness. They do not hide platform capabilities.

## Capability truth

`GET /api/capabilities/status` is the runtime truth source for provider-backed and local capabilities. It separates live provider capabilities from configurable optional integrations:

- GenX text/code/reasoning/image/video/audio/voice/avatar
- GitHub, Firecrawl, Pixabay, Qwen
- Runtime QA, preview, deployment/finalize
- Optional hooks: Whisper/STT, FAISS, Stable Diffusion, MusicGen, Playwright traces, internal orchestration graph

Optional open-source integrations report `setup_needed` or `configured_not_tested` until explicitly installed and probed.

## Model router status

`GET /api/models/router-status` returns task-level and agent-level routing. Each agent entry includes:

- agent name
- task type
- selected Standard model
- selected Premium model
- required/preferred capabilities
- fallback status and reason

## Internal reports and app-file contracts

Internal reports and manifests are persisted as build evidence, but they are not treated as generated app source files for agent payloads. This prevents missing report artifacts such as `content_quality_report.json` from becoming raw app-file `KeyError` failures.

Examples of internal artifacts:

- `content_quality_report.json`
- `quality-report.json`
- `runtime-qa/*`
- `media_manifest.json`
- `motion_manifest.json`
- `avatar_manifest.json`
- `amarktai.project.json`

Final gates may read these artifacts from their evidence locations, but Coder/Reviewer/Repair agents receive only app source files.

## Media and avatar manifests

Provider-backed media assets must be persisted with manifest evidence. Avatar video generation uses provider-accessible remote URLs for source image and audio inputs. If a provider returns only local files or no remote URL, the runtime writes `avatar_manifest.json` with `status: fallback` and patches the browser avatar fallback without claiming provider-generated avatar video.

## Repo Workbench flow

Repo Workbench backends support:

1. import/clone GitHub repo
2. detect stack and frontend/backend structure
3. create repair plan
4. checkpoint before patching
5. apply repairs or return a diff preview
6. run safe install/build/test commands
7. block empty PRs and failed normal PRs
8. create GitHub branch/PR when checks pass
9. persist PR URL and rollback evidence

Normal PR creation is blocked unless a diff exists and validation/quality checks are passing, unless a future explicit draft/failing PR mode is added.

## Runtime QA artifacts

Runtime QA writes artifacts under `runtime-qa/`:

- `runtime-qa-report.json`
- `accessibility-report.json`
- `performance-report.json`
- desktop/tablet/mobile screenshots

These reports are evidence for gates and dashboard display; they are not app source files.
