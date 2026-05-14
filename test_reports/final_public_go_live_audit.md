# Final Public Go-Live Audit

Date: 2026-05-14

## Baseline

- Source of truth: `https://github.com/amarktainetwork-blip/Amarktai-App-Builder-4.git`
- Base main: `8dc2ab9` (`Merge pull request #5 from amarktainetwork-blip/fix/coder-output-parser-and-fallback-preview`)
- Working branch: `fix/final-public-go-live-hardening`

## Root Cause: Coder Parser Fatal

The old fatal message remained possible when file-block parsing, defensive extraction, JSON parsing, and JSON repair all failed. PR #5 recovered the main Coder path, but public-go-live hardening found remaining gaps:

- deterministic fallback did not include `README.md`;
- normal successful builds did not guarantee a dashboard-visible `quality_report.md`;
- markdown headings like `### src/App.jsx` before code fences were not recognized as file paths;
- the old fatal wording still existed for non-coder block agents;
- parse-failure snippets were not persisted as user-visible system messages;
- production startup still required `GENX_API_KEY` in environment even though runtime settings-backed provider resolution is supported.

## Fixes Applied

- Improved code-fence extraction for heading/path patterns before fences.
- Added sanitized parser-failure snippets to events and messages.
- Redacted obvious token/key/password-shaped values from event/message snippets.
- Added raw response hash, length, truncation flag, and persisted raw Coder response for backend debugging.
- Removed the old fatal wording from the remaining non-coder block-agent failure path.
- Expanded deterministic fallback to generate:
  - `index.html`
  - `styles.css`
  - `script.js`
  - `quality_report.md`
  - `README.md`
- Ensured completed builds write `quality_report.md` into project files before build-storage sync.
- Allowed production startup without env `GENX_API_KEY` when provider key is supplied through encrypted dashboard Settings; readiness still validates runtime provider availability.
- Updated `.env.example`, `README.md`, and `docs/deploy.md` to document settings-backed GenX and env fallback.
- Fixed two existing Python 3.13 test event-loop flakes in mocked async tests.

## Pipeline Completion

Regression coverage confirms:

- Planner, Scout, Architect, Coder, Reviewer, validation, preview manifest, and quality reporting complete in malformed Coder-output scenarios.
- Fallback files are written to project storage.
- Preview manifest status is `ready`.
- `quality_report.md` is visible in project files.
- Project status becomes `ready` rather than `failed` when fallback files are usable.

## Finalize And GitHub PR Flow

Existing mocked tests were run for:

- finalize blocking when coverage is low;
- finalize allowing full coverage;
- GitHub branch PR body including quality/coverage/changed-file evidence.

No fake PR success path was added.

## Production Mode

Production static config now requires strong static secrets and infrastructure env:

- `APP_ENV=production`
- `JWT_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `SETTINGS_ENCRYPTION_KEY`
- `MONGO_URL`
- `DB_NAME`
- `CORS_ORIGINS`
- `BUILDS_STORAGE_ROOT`

`GENX_API_KEY` is required at runtime but may be supplied through encrypted dashboard Settings. If neither Settings nor env provides it, `/api/readiness` reports a structured blocker and build routes return clear 503 errors.

## Public Security Notes

- `/api/builds` remains auth-gated and returns 401 without bearer token.
- Settings/admin routes remain protected by existing auth dependencies.
- CORS live readiness reports `https://builder.amarktai.com`.
- Generated file path sync uses path-safety checks before writing to build storage.
- Coder parser snippets in events/messages redact obvious secret-shaped values.
- Local Docker/VPS shell verification could not be executed from this Codex Windows environment because Docker is not installed and VPS SSH keys are unavailable here.

## Remaining Live Verification

After merging and deploying this branch on the VPS, run the authenticated premium dashboard prompt and verify:

- files tab includes `index.html`, `styles.css`, `script.js`, `README.md`, and `quality_report.md`;
- preview renders;
- quality panel/report appears;
- Finalize & Push creates and saves a GitHub PR URL.
