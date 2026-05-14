# Amarktai App Builder

Amarktai App Builder is a self-hosted real-time app builder with Amarktai Assistant built in. Amarktai Coding Agents run Scout, Architect, Coder, Reviewer, and Iteration through GenX Router using one required runtime AI key: `GENX_API_KEY`, supplied either by environment or encrypted dashboard Settings.

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
- `JWT_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `SETTINGS_ENCRYPTION_KEY`
- `MONGO_URL`
- `DB_NAME`
- `REACT_APP_BACKEND_URL`
- `CORS_ORIGINS`
- `BUILDS_STORAGE_ROOT`

Production startup fails if critical static secrets are missing or weak. `JWT_SECRET` must be at least 32 characters, `ADMIN_PASSWORD` at least 12 characters, `SETTINGS_ENCRYPTION_KEY` must be a Fernet-compatible key, `BUILDS_STORAGE_ROOT` must be writable, and `CORS_ORIGINS` cannot be `*`. `GENX_API_KEY` is required at runtime for builder agents, but may be supplied through encrypted dashboard Settings; readiness fails clearly if neither Settings nor environment provides a valid key.

## Optional Environment

- `GITHUB_PAT`: enables private repo import, pull requests, and finalize-to-repo.
- `BRAVE_SEARCH_API_KEY`: enables web research for Scout.
- `GENX_BASE_URL`: defaults to `https://query.genx.sh/v1`.
- `GENX_MODEL_REASONING`, `GENX_MODEL_RESEARCH`, `GENX_MODEL_EDITS`.
- `JWT_TTL_HOURS`, `BACKEND_PORT`, `FRONTEND_PORT`.
- `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL_CHAT`, `QWEN_MODEL_CODE`, `QWEN_MODEL_IMAGE`, `QWEN_MODEL_VIDEO`, `QWEN_MODEL_AUDIO`.
- `PIXABAY_API_KEY`: enables stock media.

When GitHub PAT, Qwen, Brave Search, or Pixabay are missing, their provider-backed actions are disabled and readiness warns. When GenX is missing or invalid, readiness fails and AI actions are disabled.

## Settings Encryption Recovery

Saved provider settings are encrypted with `SETTINGS_ENCRYPTION_KEY`. Do not generate a new key for an existing Mongo database unless you are intentionally rotating settings. If the key changes, old saved settings become undecryptable. The app reports this as `decrypt_failed` and falls back to environment variables where available.

Cleanup tools:

```bash
python scripts/cleanup_bad_settings.py --dry-run
python scripts/cleanup_bad_settings.py --delete-bad
```

See `docs/production-settings-recovery.md`.

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

## Staging Deployment: test.amarktai.com

A staging deployment runs at `https://test.amarktai.com` for pre-production testing. It uses the same Docker images but with a separate database volume and different ports so it does not interfere with production (`builder.amarktai.com`).

### Staging environment variables (`.env.test`)

```bash
REACT_APP_BACKEND_URL=https://test.amarktai.com
CORS_ORIGINS=https://test.amarktai.com
BACKEND_PORT=8011
FRONTEND_PORT=8090
DB_NAME=amarktai_builder_test
```

Copy `.env.example` to `.env.test`, fill in secrets, then start the test stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test up -d --build
```

### Nginx example for test.amarktai.com

See `nginx/test.amarktai.com.conf` for the full Nginx reverse-proxy config including WebSocket support and certbot integration.

Obtain the TLS certificate:

```bash
sudo certbot --nginx -d test.amarktai.com
```

Copy and enable the config:

```bash
sudo cp nginx/test.amarktai.com.conf /etc/nginx/sites-available/test.amarktai.com
sudo ln -s /etc/nginx/sites-available/test.amarktai.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Verify staging readiness:

```bash
curl https://test.amarktai.com/api/readiness
```

### Nginx example for builder.amarktai.com

See `nginx/builder.amarktai.com.conf` for the production Nginx config.

```bash
sudo certbot --nginx -d builder.amarktai.com
sudo cp nginx/builder.amarktai.com.conf /etc/nginx/sites-available/builder.amarktai.com
sudo ln -s /etc/nginx/sites-available/builder.amarktai.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## VPS Deployment (builder.amarktai.com)

1. SSH into your VPS.
2. Clone the repository:
   ```bash
   git clone https://github.com/amarktainetwork-blip/Amarktai-App-Builder-4.git
   cd Amarktai-App-Builder-4
   ```
3. Generate secrets and fill in `.env`:
   ```bash
   cp .env.example .env
   openssl rand -hex 48   # → JWT_SECRET
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # → SETTINGS_ENCRYPTION_KEY
   ```
4. Start the stack:
   ```bash
   docker compose up -d --build
   ```
5. Install Nginx and obtain a certificate:
   ```bash
   sudo apt-get install -y nginx certbot python3-certbot-nginx
   sudo certbot --nginx -d builder.amarktai.com
   sudo cp nginx/builder.amarktai.com.conf /etc/nginx/sites-available/builder.amarktai.com
   sudo ln -s /etc/nginx/sites-available/builder.amarktai.com /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
6. Verify:
   ```bash
   curl https://builder.amarktai.com/api/health
   curl https://builder.amarktai.com/api/readiness
   curl https://builder.amarktai.com/api/capabilities
   ```

For the current VPS path and full redeploy checklist, see `docs/deploy.md`.
