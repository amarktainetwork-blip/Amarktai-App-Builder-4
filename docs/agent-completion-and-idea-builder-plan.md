# Agent Completion and Idea Builder Plan

Date: 2026-05-14

## Audit Summary

Source: `agent_forensic_audit.json`

- Registry inventory is complete: 28 agents are registered and active.
- No agent is marked dead or planned-only in the audit.
- The audit identifies real-world wiring/tooling gaps, not missing registry entries.
- Gaps requiring hardening:
  - Product Strategist / Scout declares web research, but Firecrawl remains capability-gated.
  - Frontend Coder and Motion/3D declared Framer Motion and Three.js; the builder UI now has Framer Motion installed, while generated projects must still use local/package or CDN-safe instructions depending on output format.
  - Media Director existed but needed explicit active-pipeline invocation and truthful fallback state.
  - Visual QA, Accessibility, and SEO/Performance are static validators today; full screenshot, axe-core, and Lighthouse browser execution require a later browser runtime container.
  - Runtime Engineer and Data Architect are registered extended agents; Data Architect remains deterministic, and Runtime Engineer is not forced into simple website builds.

## Changes Made In This Branch

- Wire Media Director into the normal build pipeline before Coder.
- Persist `media_director_result`, emit `media_manifest`, and pass media guidance into Coder input.
- Add deterministic Visual QA execution after contract validation so the visual agent produces project-visible results without consuming another model call.
- Add an Idea Builder API and dashboard page:
  - Create session.
  - Continue chat.
  - Finalize a build prompt.
  - Send that prompt to New Build with premium defaults.
- Keep capability truth honest:
  - If AI media is not explicitly confirmed/available, Media Director chooses CSS/SVG or stock fallback.
  - Visual QA reports `screenshot_runtime: not_available` rather than pretending browser screenshots ran.

## Agent Wiring Notes

- Manager, Planner, Scout, Architect, Frontend Coder, Reviewer, Validator, Advisor, Security, Backend Coder, Motion/3D, and Deployment were already present in the active orchestrator path.
- Media Director is now explicitly invoked in `_run_build_pipeline`.
- Visual QA is now explicitly invoked as a deterministic static analysis step and persisted to the project.
- Accessibility, SEO, responsiveness, and performance scores continue to come from `quality_validator.py`.
- Browser-grade Playwright, axe-core, and Lighthouse remain documented follow-up infrastructure, not fake green checks.

## Idea Builder Flow

1. The dashboard route `/dashboard/idea-builder` opens a chat workspace.
2. The frontend creates an authenticated session through `POST /api/idea-builder/sessions`.
3. User messages are appended through `POST /api/idea-builder/sessions/{id}/messages`.
4. If GenX is available, the Idea Builder uses the model. If not, it uses a deterministic fallback that still asks useful product questions.
5. `POST /api/idea-builder/sessions/{id}/finalize` generates a production build prompt.
6. The UI hands the prompt to `/dashboard/new`, prefilled with project name, mode, prompt, and premium quality tier.

## Remaining Honest Limitations

- Full screenshot-based Visual QA is not implemented until the production runtime includes a browser worker.
- Full axe-core browser accessibility checks are not implemented until that browser worker exists.
- Lighthouse/Core Web Vitals are not run in-process; static performance checks remain the current gate.
- Provider-backed media generation remains capability-gated and is never claimed available solely from agent registration.
