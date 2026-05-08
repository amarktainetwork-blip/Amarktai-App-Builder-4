# Emergent — Autonomous Coding Platform

## Original problem statement
Build a "Modular Agentic Architecture" coding platform: a central Orchestrator delegates to
specialised agents (Scout, Architect, Coder, Reviewer) via MCP, with a single API key feeding
58 GenX models. Frontend dashboard has a split-screen (Agent Chat left, Live Preview right)
that updates in real-time as agents write files. User can iterate ("change logo to a horse")
and click Finalize & Push to publish to GitHub.

## Architecture (as built — Jan 2026)

### Backend (FastAPI)
- `agents/genx_provider.py` — `GenXProvider` abstraction. Routes tasks to model tiers:
  - `reasoning`/`coding` → Claude Sonnet 4.5
  - `research`/`fast`   → Gemini 2.5 Flash
  - `lightweight`/`edits` → Claude Haiku 4.5
  - Wraps sync `litellm.completion` via `asyncio.to_thread` so the FastAPI loop is never blocked.
  - 2× exponential-backoff retry on transient 502/503/504 upstream errors.
- `agents/orchestrator.py` — runs Scout → Architect → Coder → Reviewer for the first build,
  and a single `iteration` agent for follow-ups. Persists messages, agent events, file writes,
  and emits real-time events to the WebSocket hub.
- `agents/prompts.py` — strict-JSON system prompts for each agent.
- `agents/mcp_tools.py` — MCP-style tool layer (filesystem, web_search, github_create_repo)
  with mock fallbacks when API keys are absent. Exposes JSON tool schemas.
- `agents/preview.py` — renders a project's files into a self-contained HTML iframe document.
- `server.py` — REST + WebSocket endpoints, `PIPELINE_SEM = asyncio.Semaphore(2)` caps
  concurrent pipelines, lifespan-based shutdown, atomic queue-locking on iteration POSTs.

### Frontend (React + Tailwind + shadcn)
- `pages/ProjectList.jsx` — split create form + recent projects list, 4 starter templates.
- `pages/Workspace.jsx` — split workspace (35% left chat/timeline, 65% right code/preview tabs)
  with WebSocket-driven live updates.
- `components/AgentTimeline.jsx` — 4-step pipeline with strict color map
  (Scout #FF5722, Architect #2962FF, Coder #00E676, Reviewer #FFC107) and pulsing active dot.
- `components/ChatPanel.jsx` — conversation with role/agent/model labels.
- `components/{FileTree,CodeViewer,LivePreview}.jsx` — IDE-style file viewer + iframe preview.
- `components/StatusBar.jsx` — WS state, model, tokens, cost.
- `components/SettingsDialog.jsx` — API-key management with masked previews.
- Design tokens follow `/app/design_guidelines.json` (Swiss High-Contrast, JetBrains Mono +
  IBM Plex Sans).

### Data model (MongoDB — `emergent_platform`)
- `projects { id, name, prompt, status, usage{tokens,cost_usd,last_model}, repo_url, ... }`
- `messages { id, project_id, role, agent, content, meta, created_at }`
- `agent_events { id, project_id, agent, status, detail, meta, created_at }`
- `files { project_id, path, content, language, created_at, updated_at }`
- All datetime fields stored as ISO-8601 strings; `_id` excluded from every read.

## Personas
- **Founder/Builder** — describes an app idea in plain English, watches it materialise.
- **Developer** — uses Code tab to inspect what agents wrote, iterates with chat.

## Core requirements (static)
- One key, many models with auto-routing.
- Real-time agent timeline + chat + preview, never block the UI.
- MCP-style tools with graceful mocks when keys absent.
- Finalize & Push to GitHub (one-click, mockable).

## What's been implemented (Jan 2026)
- Full Scout → Architect → Coder → Reviewer pipeline working end-to-end (verified: dark-mode
  calculator generated and rendered live in iframe).
- Iteration loop (`/messages` POST → single iteration agent re-edits files).
- Real-time WebSocket updates for messages, agent events, file writes, status, usage,
  build-complete, finalize.
- Live preview via inlined-HTML iframe renderer (works without WebContainer key).
- Settings dialog for 4 API keys with masked previews (Emergent LLM, WebContainer, GitHub,
  Brave Search) — writes to `.env` and refreshes process env.
- Finalize & Push (mocked GitHub repo creation when `GITHUB_PAT` is empty).
- Cost & token tracker in the status bar.
- 19/19 backend tests passing individually; concurrent calls during a build no longer block.
- Frontend lints clean, full smoke + e2e tested.

## Prioritised backlog
- **P1** Real WebContainer integration when user provides StackBlitz key.
- **P1** Real GitHub push (Octokit) when user provides PAT.
- **P1** Real Brave Search MCP server (subprocess `npx @modelcontextprotocol/server-brave-search`).
- **P1** JSON-parse-error retry in orchestrator (re-prompt agent with "STRICT JSON only").
- **P2** Streaming agent output (token-by-token via WS rather than once-per-step).
- **P2** Project versioning / undo iterations.
- **P2** Multi-file React project support (currently single-page HTML).
- **P3** Full-text search across messages/files in workspace.
- **P3** Public preview share links.

## Test credentials
- No authentication in this MVP — public read/write per project ID.
- Backend keys live in `/app/backend/.env` (`EMERGENT_LLM_KEY` set, others placeholder).

## Next tasks
- Wait for user to provide WebContainer / GitHub / Brave keys, then promote those integrations
  out of mock mode.
- Ship JSON-parse retry to harden the pipeline against rare malformed model output.
