# AmarktAI Network

> Autonomous coding studio. Four agents (Scout · Architect · Coder · Reviewer)
> collaborate over a single **GenX Router** key to ship working web apps and
> open pull requests against your GitHub repos — in real-time.

![status](https://img.shields.io/badge/status-MVP-00E676?style=flat-square)
![stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20MongoDB-2962FF?style=flat-square)
![models](https://img.shields.io/badge/models-40%2B%20via%20GenX-FF5722?style=flat-square)

---

## Why

One key. Forty-plus models. Four agents. Real pull requests.

- **GenX Router** (https://genx.sh) gives you Claude, GPT-5, Gemini, Grok, etc.
  through a single OpenAI-compatible endpoint. No provider accounts to juggle.
- **Cost-aware routing** — cheap models for research and edits, premium models
  for architecture and code. Token & cost meter is always on screen.
- **GitHub integration** — paste a public repo URL, let agents iterate, open a PR
  back against the original. No manual `git push`.
- **Self-hosted** — your VPS, your data, your credits.

## Quick start (Docker)

```bash
# 1. Clone
git clone https://github.com/<you>/amarktai-network.git
cd amarktai-network

# 2. Configure
cp .env.example .env
# edit .env — at minimum set GENX_API_KEY, REACT_APP_BACKEND_URL,
# JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD.

# 3. Launch
docker compose up -d --build

# 4. Open
open http://your-vps:8080      # frontend
# backend lives at http://your-vps:8001/api/
```

That's it. The backend will seed your admin user on first boot. Sign in,
describe an app or paste a GitHub repo URL, and the agents take over.

### Putting it behind a reverse proxy

For a production VPS deploy, terminate TLS with Caddy / Nginx / Traefik and
point both routes at the right service:

```caddy
amarktai.example.com {
    @api path /api/*
    reverse_proxy @api  backend:8001
    reverse_proxy frontend:80
}
```

Set `REACT_APP_BACKEND_URL=https://amarktai.example.com` in `.env` so the
browser bundle calls back through your TLS endpoint, then `docker compose up
--build` to bake the URL into the frontend bundle.

## Configuration

All runtime config lives in `.env`. The most important keys:

| Variable | Required | What it does |
|---|---|---|
| `GENX_API_KEY` | ✅ | Your `gnxk_...` key from genx.sh — drives every agent. |
| `REACT_APP_BACKEND_URL` | ✅ | Public URL the browser uses for `/api` calls. Baked into the bundle at build time. |
| `JWT_SECRET` | ✅ | Long random string. Use `openssl rand -hex 48`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | ✅ | Seeded on first boot. Change them before going live. |
| `GITHUB_PAT` | ⚪ | Personal access token with `repo` + `pull_request` scopes. Needed to open PRs. |
| `GENX_MODEL_*` | ⚪ | Override the cheap-vs-expensive routing. Use any ID from `GET /api/models`. |
| `WEBCONTAINER_API_KEY` | ⚪ | StackBlitz key for full Node sandboxes. Static iframe renderer is used otherwise. |

## Architecture

```
┌──────────────┐    JWT/REST     ┌────────────────────┐    OpenAI-compat
│  React SPA   │ ──────────────▶ │  FastAPI backend   │ ───────────────────▶  GenX Router
│  (Tailwind)  │ ◀── WebSocket ─ │  Orchestrator      │ ◀── streamed text ── (40+ models)
└──────────────┘                 │  ↓ MCP tool layer  │
                                 │  • filesystem (Mongo)
                                 │  • github API
                                 │  • web search (Brave)
                                 └────────────────────┘
```

- `backend/agents/genx_provider.py` — single class; swap providers in one place.
- `backend/agents/orchestrator.py` — Scout → Architect → Coder → Reviewer + iteration agent.
- `backend/agents/mcp_tools.py` — MCP-style tool surface (filesystem, GitHub, web search).
- `backend/agents/preview.py` — inlined-iframe live preview renderer.
- `backend/github_integration.py` — GitHub REST client (import repo, open PR).
- `backend/auth.py` — JWT + bcrypt + seeded admin.

## API

All `/api/projects/*` endpoints require `Authorization: Bearer <token>`.

```
POST   /api/auth/login                  { email, password } → { token, expires_at, user }
GET    /api/auth/me                     → user
GET    /api/models                      → tiers + agents + GenX /v1/models
POST   /api/projects                    { name, prompt }
POST   /api/projects/from-repo          { repo_url, branch?, github_pat? }
GET    /api/projects                    → user's projects
GET    /api/projects/{id}               → project
DELETE /api/projects/{id}
POST   /api/projects/{id}/messages      { content }    (iteration)
GET    /api/projects/{id}/messages      → list
GET    /api/projects/{id}/events        → agent timeline
GET    /api/projects/{id}/files         → file list
GET    /api/projects/{id}/files/content?path=foo.html
GET    /api/projects/{id}/preview       → self-contained HTML (public)
POST   /api/projects/{id}/finalize      → mocked GitHub repo creation
POST   /api/projects/{id}/pr            { github_pat, branch_name?, title?, body? }
WS     /api/ws/{id}?token=<jwt>         → live agent events
GET/POST /api/settings                  → masked / update API keys
POST   /api/contact                     → public contact form
```

## Development (without Docker)

Backend:

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env  && edit .env
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

Frontend:

```bash
cd frontend
yarn install
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env
yarn start
```

## License

MIT — do whatever you want, just don't blame us when the AI ships a typo.
