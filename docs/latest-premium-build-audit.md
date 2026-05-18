# Latest Premium Build Audit: Premium Bakery Fixture

Project: `284c4875-a5bd-4224-9fc8-a99263b7e2b4`

This audit records why the audited premium bakery build was not a truthful premium/cinematic pass.

## Provider Execution

- GenX image/video models were discovered, but the runtime media call failed with `GenX generate HTTP 400: {"error":{"code":"INVALID_REQUEST","message":"params is required"}}`.
- Qwen image/media was not end-to-end working; the image endpoint returned `qwen image endpoint HTTP 404`.
- Pixabay search returned usable metadata, but repeated image downloads hit `429 Too Many Requests`.
- The resulting build had no persisted AI-generated images. It had one Pixabay video and two local runtime fallback images.

## Manifest And Section Assignment

`media_manifest.json` reported `status: stock` and `asset_count: 3`, but the asset mix was not equivalent to premium media coverage:

- one Pixabay video,
- two local runtime fallback images,
- all assets assigned to `hero`.

`gallery`, `story`, `menu`, and `contact` had no media assignment. `aligned_sections` showed only `hero`, even though the page had several user-visible sections.

## Runtime QA

Runtime QA did create screenshots, but it also recorded:

- axe-core missing/setup-needed,
- Lighthouse failed because Chrome was not configured through `CHROME_PATH`/`CHROMIUM_PATH`,
- broken runtime media assets.

Those issues were not reflected strongly enough in final premium status.

## Quality Gate Inconsistency

`quality-report.json` returned `score: 100`, `blockers: []`, and `warnings: []` while runtime/provider evidence showed failures. This was a source-of-truth bug: file presence and static completeness overrode runtime media truth.

## Fix Implemented In This PR

- GenX media jobs now include required `params`.
- Media manifest now records provider discovery, runtime failures, persistence, injection, fallback use, rate limits, section alignment, and `premium_media_complete`.
- Media injection distributes assets across expected sections and injects hero video/image as a background layer.
- Premium quality scoring now penalizes provider failures, fallback-only media, hero-only alignment, missing gallery/story/menu media, broken runtime media, missing hero background media, generic fallback wording, and runtime QA setup issues.
- Capability labels now distinguish `Provider discovered`, `Runtime failed`, `Rate limited`, `Setup needed`, and `End-to-end available`.

## Retest Requirement

After merge/deploy, rerun the audited premium bakery prompt. The build must show provider attempts clearly, truthful manifest status, gallery/story/menu alignment, hero cinematic media treatment when available, realistic premium score, and final status that reflects runtime QA issues.
