# Command Runner Evidence

Generated: 2026-05-14

## Implemented

- Existing command runner already restricted commands to an allowlist and enforced workspace path safety under `BUILDS_STORAGE_ROOT`.
- Added safe git inspection commands:
  - `git status`
  - `git status --porcelain`
  - `git diff`
  - `git diff --stat`
  - `git diff --name-status`
  - `git log`
  - `git branch`
- Added docker compose config/build command forms, but gated them behind `ALLOW_DOCKER_COMMANDS=true` so they cannot run accidentally from the dashboard.
- Added tests proving git commands are allowed and docker commands are blocked without the env gate.

## Tests Run

- `python -m pytest backend/tests/test_phase3_services.py -q` PASS: 105 passed

## Remaining Hard Blockers

- Command logs are saved by the existing runner, but the dashboard still needs fuller log streaming controls for all repo repair loops.
