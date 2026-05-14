# Browser QA Evidence

Generated: 2026-05-14

## Implemented in This PR

- Added backend `playwright` dependency.
- Added backend Docker Chromium install step with `python -m playwright install --with-deps chromium`.
- Added frontend dev dependencies for `@playwright/test` and `lighthouse`, plus direct `axe-core` dependency.

## Hard Blocker

- The active registry still documents Visual QA, accessibility, and performance as static/future-runtime in `backend/agents/agent_registry.py`. Browser-backed screenshot capture, axe execution, and Lighthouse/performance scoring still need to be wired into a runtime service and dashboard evidence panel before claiming full production QA.
