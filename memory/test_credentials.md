# AmarktAI Network — Test Credentials

## Admin (seeded on first boot)
- **Email**: `admin@amarktai.io`
- **Password**: `amarktai-admin`

These are configured via `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `backend/.env`.
On first boot, the backend's lifespan handler calls `seed_admin()` which creates
the user (idempotent — running it twice is safe).

## Public test endpoints (no auth)
- `GET  /api/`                      → `{"service": "amarktai-network", "status": "ok"}`
- `POST /api/auth/login`            → returns JWT
- `POST /api/contact`               → contact form

## Authenticated test flows
1. `POST /api/auth/login` → grab `token`
2. `GET  /api/auth/me`     `Authorization: Bearer <token>`
3. `POST /api/projects`    body `{"name":"X","prompt":"Y"}`
4. `POST /api/projects/from-repo` body `{"repo_url":"https://github.com/octocat/Hello-World"}`

## GenX
- `GENX_API_KEY=gnxk_10fafedf9dd242d68fd9005bfb376668`
- Default model routing:
  - reasoning/coding: `claude-sonnet-4-6`
  - research/fast:    `gpt-5.4-mini`
  - lightweight/edits: `claude-haiku-4-5`

## Known good public repo for import-tests
- `https://github.com/octocat/Hello-World`
