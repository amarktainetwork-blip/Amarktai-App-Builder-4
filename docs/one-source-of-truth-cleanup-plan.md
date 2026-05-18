# One Source Of Truth Cleanup Plan

The builder must report capability and build readiness from evidence, not optimism. These are the remaining truth-source boundaries and cleanup rules.

## Capabilities, Readiness, And Go-Live

Truth source: `CapabilityTruthService` plus provider probes and latest build evidence.

- `/api/readiness`, `/api/go-live/status`, and `/api/capabilities/status` must consume the same provider/config/runtime evidence.
- Provider discovery means `Provider discovered`, not `Available`.
- `End-to-end available` requires provider configured, provider/model discovered, runtime call passed, artifact persisted, used in latest build, visible in preview, and final gate enforcement.

## Provider Discovery Vs Provider Execution

Discovery proves only that a provider or model exists. Execution proof requires a successful runtime call and persisted result. Media providers must write attempts to `media_manifest.json` with explicit success/failure/rate-limit reasons.

## Agents Registry Vs Build Pipeline

Agent registry entries describe what the system can attempt. Build pipeline events and artifacts prove what happened. Dashboard labels must prefer build evidence over registry claims.

## Media Director Vs Media Runtime Service

Media Director decides intent and prompts. `media_runtime_service` is the persistence and injection truth source. The runtime manifest must include provider attempts, fallback use, section alignment, injection status, and `premium_media_complete`.

## Quality Report Vs Content Quality Vs Runtime QA

`content_quality_report.json` scores content. `runtime-qa-report.json` scores browser/runtime evidence. `quality-report.json` must aggregate both and include `premium_quality_score`; it must not return 100 when provider execution, runtime QA, or media alignment fails.

## Final Gate Vs Dashboard State

Final gate blockers are the production decision. Dashboard state must show those exact blockers, warnings, provider attempts, media section alignment, fallback reason, and next action.

## Project Files Vs Build Storage Files Vs API Files

Generated app source files are separate from internal evidence files. Evidence files such as `media_manifest.json`, `quality-report.json`, `content_quality_report.json`, and runtime QA reports remain build evidence and must not be treated as app source payload.

## Frontend Labels Vs Backend Truth

Frontend capability cards must use backend `dashboard_label` and `capability_status`. They must not infer “Available” from `configured`, `available`, or discovered model counts alone.

## Deprecated References

- Brave: remove active user-facing Brave labels and keep Firecrawl as the search/crawl provider.
- App Builder 2/3: mark historical docs only; do not show them as current product identity.
- Old tier labels such as `cheap` and ambiguous `balanced`: use current quality/runtime language.
- Public GenX-first branding: avoid claims that imply every visible output is GenX-generated unless manifest proof exists.
- Duplicate capability helpers: retire summary helpers that bypass `CapabilityTruthService`.

## Cleanup Order

1. Route capability/readiness/go-live endpoints through shared truth objects.
2. Record provider execution attempts in build artifacts.
3. Make final gate consume runtime QA, media manifest, content quality, and premium quality.
4. Make dashboard labels consume final backend evidence labels.
5. Keep deprecated labels out of public UI and active docs.
