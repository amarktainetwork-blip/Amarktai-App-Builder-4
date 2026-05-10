# Amarktai App Builder

Amarktai App Builder is a self-hosted real-time app builder with Amarktai Assistant built in. Amarktai Coding Agents run Scout, Architect, Coder, Reviewer, and Iteration through GenX Router using one required AI key: `GENX_API_KEY`.

## Features

- Prompt-to-app builds through GenX Router.
- GitHub repository import for public repos, and private repos when `GITHUB_PAT` is configured.
- Real-time workspace updates over WebSocket.
- Persisted agent events, messages, generated files, usage estimates, and failure reasons.
- Authenticated live preview.
- Amarktai Assistant chat for project iteration.
- Pull request creation for imported repositories when `GITHUB_PAT` is configured.
- New GitHub repository creation during finalize when `GITHUB_PAT` is configured.
- Encrypted settings storage in MongoDB for `GENX_API_KEY`, `GITHUB_PAT`, and `BRAVE_SEARCH_API_KEY`.
- Admin user management.
- Truthful `/api/health` and `/api/readiness` endpoints.

## Docker Quick Start

```bash
cp .env.example .env
openssl rand -hex 48
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

Put the generated values into `.env`:

```bash
JWT_SECRET=<openssl-output>
SETTINGS_ENCRYPTION_KEY=<fernet-output>
GENX_API_KEY=<your-genx-key>
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong-12-plus-character-password>
CORS_ORIGINS=https://builder.amarktai.com
REACT_APP_BACKEND_URL=https://builder.amarktai.com
```

Start the stack:

```bash
docker compose up -d --build
```

Deployment target:

- Frontend and API origin: `https://builder.amarktai.com`
- Backend health: `https://builder.amarktai.com/api/health`
- Backend readiness: `https://builder.amarktai.com/api/readiness`

## Required Environment

- `APP_ENV=production`
- `GENX_API_KEY`
- `JWT_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `SETTINGS_ENCRYPTION_KEY`
- `MONGO_URL`
- `DB_NAME`
- `REACT_APP_BACKEND_URL`
- `CORS_ORIGINS`

Production startup fails if critical secrets are missing or weak. `JWT_SECRET` must be at least 32 characters, `ADMIN_PASSWORD` at least 12 characters, `SETTINGS_ENCRYPTION_KEY` must be a Fernet-compatible key, and `CORS_ORIGINS` cannot be `*`.

## Optional Environment

- `GITHUB_PAT`: enables private repo import, pull requests, and finalize-to-repo.
- `BRAVE_SEARCH_API_KEY`: enables web research for Scout.
- `GENX_BASE_URL`: defaults to `https://query.genx.sh/v1`.
- `GENX_MODEL_REASONING`, `GENX_MODEL_RESEARCH`, `GENX_MODEL_EDITS`.
- `JWT_TTL_HOURS`, `BACKEND_PORT`, `FRONTEND_PORT`.

When GitHub PAT is missing, GitHub write actions are disabled and readiness warns. When Brave Search is missing, web research is disabled and readiness warns. When GenX is missing or invalid, readiness fails and AI actions are disabled.

## Readiness

`GET https://builder.amarktai.com/api/readiness` returns `PASS` only when required production configuration is strong, Mongo responds, an active admin exists, GenX is configured and live, and source checks pass. Optional GitHub and Brave Search keys produce warnings when absent.

## Verification

Development check:

```bash
bash scripts/go_live_check.sh
```

Production check:

```bash
CHECK_MODE=production bash scripts/go_live_check.sh
```

The production check builds the frontend and backend, validates Docker Compose, starts the stack, calls `/api/health`, calls `/api/readiness`, and exits non-zero unless readiness is `PASS`.
