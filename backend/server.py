"""Emergent Autonomous Coding Platform — FastAPI backend."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

from agents.genx_provider import AGENT_TIER, MODEL_ROUTES, GenXProvider
from agents.mcp_tools import TOOL_SCHEMAS, ProjectFS, github_create_repo
from agents.orchestrator import Orchestrator
from agents.preview import render_preview

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("emergent")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Cap concurrent agent pipelines so a burst of project creations cannot exhaust the LLM proxy.
PIPELINE_SEM = asyncio.Semaphore(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    client.close()


app = FastAPI(title="Emergent Autonomous Coding Platform", lifespan=lifespan)
api = APIRouter(prefix="/api")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------- WebSocket Hub ----------------------------

class Hub:
    """Per-project WebSocket fan-out."""

    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def join(self, project_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.rooms.setdefault(project_id, set()).add(ws)

    async def leave(self, project_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.rooms.get(project_id, set()).discard(ws)

    async def broadcast(self, project_id: str, payload: dict) -> None:
        # Snapshot to avoid mutation during iteration.
        async with self.lock:
            sockets = list(self.rooms.get(project_id, set()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                for ws in dead:
                    self.rooms.get(project_id, set()).discard(ws)


hub = Hub()


def emitter_for(project_id: str):
    async def _emit(payload: dict) -> None:
        await hub.broadcast(project_id, payload)
    return _emit


# ---------------------------- Pydantic Models ----------------------------

class ProjectCreate(BaseModel):
    name: str
    prompt: str


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    prompt: str
    status: str = "queued"  # queued | running | ready | failed
    usage: dict = Field(default_factory=lambda: {"tokens": 0, "cost_usd": 0.0, "last_model": None})
    repo_url: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class MessageCreate(BaseModel):
    content: str


class SettingsUpdate(BaseModel):
    EMERGENT_LLM_KEY: str | None = None
    WEBCONTAINER_API_KEY: str | None = None
    GITHUB_PAT: str | None = None
    BRAVE_SEARCH_API_KEY: str | None = None


# ---------------------------- Orchestrator launcher ----------------------------

async def _launch_pipeline(project_id: str, prompt: str, mode: str) -> None:
    provider = GenXProvider()
    orch = Orchestrator(db, provider, project_id, emitter_for(project_id))
    try:
        if mode == "iterate":
            await orch.run_iteration(prompt)
        else:
            await orch.run_full_build(prompt)
    except Exception as e:
        logger.exception("pipeline failed: %s", e)


# ---------------------------- Routes ----------------------------

@api.get("/")
async def root() -> dict:
    return {"service": "emergent-platform", "status": "ok"}


@api.get("/models")
async def list_models() -> dict:
    return {
        "tiers": {tier: {"provider": p, "model": m, "label": label}
                  for tier, (p, m, label) in MODEL_ROUTES.items()},
        "agents": AGENT_TIER,
        "tools": TOOL_SCHEMAS,
    }


@api.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate) -> Project:
    proj = Project(name=body.name, prompt=body.prompt)
    doc = proj.model_dump()
    await db.projects.insert_one(dict(doc))
    asyncio.create_task(_launch_pipeline(proj.id, body.prompt, "build"))
    return proj


@api.get("/projects", response_model=list[Project])
async def list_projects() -> list[Project]:
    cur = db.projects.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cur.to_list(500)
    return [Project(**d) for d in docs]


@api.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**doc)


@api.delete("/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    await db.projects.delete_one({"id": project_id})
    await db.messages.delete_many({"project_id": project_id})
    await db.agent_events.delete_many({"project_id": project_id})
    await db.files.delete_many({"project_id": project_id})
    return {"ok": True}


@api.get("/projects/{project_id}/messages")
async def list_messages(project_id: str) -> list[dict]:
    cur = db.messages.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1)
    return await cur.to_list(2000)


@api.get("/projects/{project_id}/events")
async def list_events(project_id: str) -> list[dict]:
    cur = db.agent_events.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1)
    return await cur.to_list(2000)


@api.get("/projects/{project_id}/files")
async def list_files(project_id: str) -> list[dict]:
    fs = ProjectFS(db, project_id)
    return await fs.list()


@api.get("/projects/{project_id}/files/content")
async def file_content(project_id: str, path: str) -> dict:
    fs = ProjectFS(db, project_id)
    doc = await fs.read(path)
    if not doc:
        raise HTTPException(404, "File not found")
    return doc


@api.post("/projects/{project_id}/messages")
async def send_message(project_id: str, body: MessageCreate) -> dict:
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    if proj.get("status") in ("running", "queued"):
        raise HTTPException(409, "Build already in progress")
    # Optimistically lock to avoid a race window before the orchestrator flips status.
    await db.projects.update_one({"id": project_id}, {"$set": {"status": "queued"}})
    asyncio.create_task(_launch_pipeline(project_id, body.content, "iterate"))
    return {"ok": True, "queued": True}


@api.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def project_preview(project_id: str) -> HTMLResponse:
    fs = ProjectFS(db, project_id)
    files = await fs.list_full()
    html = render_preview(files)
    return HTMLResponse(content=html, headers={"X-Frame-Options": "SAMEORIGIN"})


@api.post("/projects/{project_id}/finalize")
async def finalize(project_id: str) -> dict:
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    repo = await github_create_repo(
        name=proj["name"].lower().replace(" ", "-")[:60] or "emergent-app",
        description=proj["prompt"][:120],
        private=False,
    )
    await db.projects.update_one(
        {"id": project_id}, {"$set": {"repo_url": repo["url"], "updated_at": _now()}}
    )
    await hub.broadcast(project_id, {"type": "finalized", "data": repo})
    return repo


# ---------------------------- Settings ----------------------------

ENV_FILE = ROOT_DIR / ".env"
SETTINGS_KEYS = ["EMERGENT_LLM_KEY", "WEBCONTAINER_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY"]


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"')
    return out


def _write_env(updates: dict[str, str]) -> None:
    current = _read_env()
    current.update({k: v for k, v in updates.items() if v is not None})
    lines = [f'{k}="{current.get(k, "")}"' for k in
             ["MONGO_URL", "DB_NAME", "CORS_ORIGINS", *SETTINGS_KEYS]]
    ENV_FILE.write_text("\n".join(lines) + "\n")


def _mask(v: str | None) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "***"
    return f"{v[:4]}…{v[-4:]}"


@api.get("/settings")
async def get_settings() -> dict:
    env = _read_env()
    return {k: {"set": bool(env.get(k)), "preview": _mask(env.get(k))} for k in SETTINGS_KEYS}


@api.post("/settings")
async def update_settings(body: SettingsUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    _write_env(updates)
    # Refresh process env so subsequent calls use new values without restart.
    for k, v in updates.items():
        os.environ[k] = v
    return {"ok": True, "updated": list(updates.keys())}


# ---------------------------- WebSocket ----------------------------

@app.websocket("/api/ws/{project_id}")
async def ws_project(ws: WebSocket, project_id: str) -> None:
    await ws.accept()
    await hub.join(project_id, ws)
    try:
        await ws.send_json({"type": "hello", "data": {"project_id": project_id}})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_json({"type": "pong", "data": {"t": _now()}})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "data": {"t": _now()}})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(project_id, ws)


# ---------------------------- App wiring ----------------------------

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
