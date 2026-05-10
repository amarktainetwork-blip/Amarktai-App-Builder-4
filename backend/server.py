"""AmarktAI Network — Autonomous Coding Platform (FastAPI backend)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from agents.genx_provider import AGENT_TIER, GenXProvider
from agents.mcp_tools import TOOL_SCHEMAS, ProjectFS, github_create_repo
from agents.orchestrator import Orchestrator
from agents.preview import render_preview
from auth import (
    decode_token, hash_password, make_token, require_user, seed_admin, verify_password,
)
import github_integration as gh

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("amarktai")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

PIPELINE_SEM = asyncio.Semaphore(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await seed_admin(db)
    logger.info("AmarktAI Network ready")
    yield
    client.close()


app = FastAPI(title="AmarktAI Network — Autonomous Coding Platform", lifespan=lifespan)
api = APIRouter(prefix="/api")
secured = APIRouter(prefix="/api", dependencies=[Depends(require_user)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------- WebSocket Hub ----------------------------

class Hub:
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

class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(min_length=1, max_length=4000)


class ProjectCreate(BaseModel):
    name: str
    prompt: str


class RepoImportBody(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    github_pat: Optional[str] = None  # used only if repo is private


class PRBody(BaseModel):
    github_pat: str
    branch_name: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    prompt: str
    status: str = "queued"  # queued | running | ready | failed
    usage: dict = Field(default_factory=lambda: {"tokens": 0, "cost_usd": 0.0, "last_model": None})
    repo_url: str | None = None
    github: dict | None = None     # { owner, repo, branch, default_branch, commit_sha, html_url }
    pr_url: str | None = None
    owner_id: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class MessageCreate(BaseModel):
    content: str


class SettingsUpdate(BaseModel):
    GENX_API_KEY: Optional[str] = None
    GITHUB_PAT: Optional[str] = None
    WEBCONTAINER_API_KEY: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None


# ---------------------------- Orchestrator launcher ----------------------------

async def _launch_pipeline(project_id: str, prompt: str, mode: str) -> None:
    async with PIPELINE_SEM:
        provider = GenXProvider()
        orch = Orchestrator(db, provider, project_id, emitter_for(project_id))
        try:
            if mode == "iterate":
                await orch.run_iteration(prompt)
            else:
                await orch.run_full_build(prompt)
        except Exception as e:
            logger.exception("pipeline failed: %s", e)


# ---------------------------- Public Routes ----------------------------

@api.get("/")
async def root() -> dict:
    return {"service": "amarktai-network", "status": "ok"}


@api.post("/auth/login")
async def login(body: LoginBody) -> dict:
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return make_token(user)


@api.get("/auth/me")
async def me(claims: dict = Depends(require_user)) -> dict:
    user = await db.users.find_one({"id": claims["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User no longer exists")
    return user


@api.post("/contact")
async def contact(body: ContactBody) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name, "email": body.email, "message": body.message,
        "created_at": _now(),
    }
    await db.contact_messages.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"]}


# ---------------------------- Secured Routes ----------------------------

@secured.get("/models")
async def list_models() -> dict:
    provider = GenXProvider()
    try:
        models = await provider.list_models()
    except Exception as e:
        logger.warning("Could not fetch GenX /v1/models: %s", e)
        models = []
    return {
        "tiers": GenXProvider.list_tiers(),
        "agents": AGENT_TIER,
        "tools": TOOL_SCHEMAS,
        "available": models,
    }


@secured.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate, claims: dict = Depends(require_user)) -> Project:
    proj = Project(name=body.name, prompt=body.prompt, owner_id=claims["sub"])
    await db.projects.insert_one(dict(proj.model_dump()))
    asyncio.create_task(_launch_pipeline(proj.id, body.prompt, "build"))
    return proj


@secured.post("/projects/from-repo", response_model=Project)
async def import_from_repo(body: RepoImportBody, claims: dict = Depends(require_user)) -> Project:
    try:
        owner, repo = gh.parse_repo_url(body.repo_url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pat = body.github_pat or os.environ.get("GITHUB_PAT") or None
    try:
        info = await gh.import_repo(owner, repo, body.branch, pat)
    except Exception as e:
        raise HTTPException(400, f"GitHub import failed: {e}")
    proj = Project(
        name=f"{owner}/{repo}",
        prompt=f"Imported public repo {info['html_url']} (branch {info['branch']})",
        status="ready",
        owner_id=claims["sub"],
        github={k: info[k] for k in ("owner", "repo", "branch", "default_branch", "commit_sha", "html_url")},
    )
    await db.projects.insert_one(dict(proj.model_dump()))
    fs = ProjectFS(db, proj.id)
    for f in info["files"]:
        await fs.write(f["path"], f["content"], _ext_lang(f["path"]))
    return proj


@secured.get("/projects", response_model=list[Project])
async def list_projects(claims: dict = Depends(require_user)) -> list[Project]:
    cur = db.projects.find({"owner_id": claims["sub"]}, {"_id": 0}).sort("created_at", -1)
    docs = await cur.to_list(500)
    return [Project(**d) for d in docs]


@secured.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str, claims: dict = Depends(require_user)) -> Project:
    doc = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**doc)


@secured.delete("/projects/{project_id}")
async def delete_project(project_id: str, claims: dict = Depends(require_user)) -> dict:
    res = await db.projects.delete_one({"id": project_id, "owner_id": claims["sub"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    await db.messages.delete_many({"project_id": project_id})
    await db.agent_events.delete_many({"project_id": project_id})
    await db.files.delete_many({"project_id": project_id})
    return {"ok": True}


async def _own(project_id: str, claims: dict) -> None:
    doc = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(404, "Project not found")


@secured.get("/projects/{project_id}/messages")
async def list_messages(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    cur = db.messages.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1)
    return await cur.to_list(2000)


@secured.get("/projects/{project_id}/events")
async def list_events(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    cur = db.agent_events.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1)
    return await cur.to_list(2000)


@secured.get("/projects/{project_id}/files")
async def list_files(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    return await ProjectFS(db, project_id).list()


@secured.get("/projects/{project_id}/files/content")
async def file_content(project_id: str, path: str, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    doc = await ProjectFS(db, project_id).read(path)
    if not doc:
        raise HTTPException(404, "File not found")
    return doc


@secured.post("/projects/{project_id}/messages")
async def send_message(project_id: str, body: MessageCreate,
                       claims: dict = Depends(require_user)) -> dict:
    proj = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    if proj.get("status") in ("running", "queued"):
        raise HTTPException(409, "Build already in progress")
    await db.projects.update_one({"id": project_id}, {"$set": {"status": "queued"}})
    asyncio.create_task(_launch_pipeline(project_id, body.content, "iterate"))
    return {"ok": True, "queued": True}


# Preview is intentionally public (so the iframe inside our own UI just works
# without juggling auth headers); URL is unguessable thanks to UUID project IDs.
@api.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def project_preview(project_id: str) -> HTMLResponse:
    files = await ProjectFS(db, project_id).list_full()
    html = render_preview(files)
    return HTMLResponse(content=html, headers={"X-Frame-Options": "SAMEORIGIN"})


@secured.post("/projects/{project_id}/finalize")
async def finalize(project_id: str, claims: dict = Depends(require_user)) -> dict:
    proj = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    repo = await github_create_repo(
        name=re.sub(r"[^a-z0-9-]+", "-", proj["name"].lower()).strip("-")[:60] or "amarktai-app",
        description=proj["prompt"][:120],
        private=False,
    )
    await db.projects.update_one(
        {"id": project_id}, {"$set": {"repo_url": repo["url"], "updated_at": _now()}}
    )
    await hub.broadcast(project_id, {"type": "finalized", "data": repo})
    return repo


@secured.post("/projects/{project_id}/pr")
async def open_pr(project_id: str, body: PRBody,
                  claims: dict = Depends(require_user)) -> dict:
    proj = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0})
    if not proj or not proj.get("github"):
        raise HTTPException(400, "Project was not imported from a GitHub repo")
    github = proj["github"]
    files = await ProjectFS(db, project_id).list_full()
    payload_files = [{"path": f["path"], "content": f["content"]} for f in files]
    branch = body.branch_name or f"amarktai/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    title = body.title or f"AmarktAI Network: updates from agentic build"
    body_md = body.body or (
        f"This PR was generated by **AmarktAI Network**.\n\n"
        f"Files updated by autonomous agents (Scout → Architect → Coder → Reviewer)."
    )
    try:
        result = await gh.open_pr(
            owner=github["owner"], repo=github["repo"],
            base_branch=github.get("default_branch") or github["branch"],
            new_branch=branch, files=payload_files,
            title=title, body=body_md, pat=body.github_pat,
        )
    except Exception as e:
        raise HTTPException(400, f"Failed to open PR: {e}")
    await db.projects.update_one(
        {"id": project_id}, {"$set": {"pr_url": result["pr_url"], "updated_at": _now()}}
    )
    await hub.broadcast(project_id, {"type": "pr_opened", "data": result})
    return result


# ---------------------------- Settings ----------------------------

ENV_FILE = ROOT_DIR / ".env"
SETTINGS_KEYS = ["GENX_API_KEY", "GITHUB_PAT", "WEBCONTAINER_API_KEY", "BRAVE_SEARCH_API_KEY"]
ALL_KEYS = ["MONGO_URL", "DB_NAME", "CORS_ORIGINS",
            "GENX_API_KEY", "GENX_BASE_URL",
            "GENX_MODEL_REASONING", "GENX_MODEL_RESEARCH", "GENX_MODEL_EDITS",
            "JWT_SECRET", "JWT_ALGO", "JWT_TTL_HOURS",
            "ADMIN_EMAIL", "ADMIN_PASSWORD",
            *SETTINGS_KEYS]


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
    seen: set[str] = set()
    lines = []
    for k in ALL_KEYS:
        if k not in current:
            continue
        lines.append(f'{k}="{current[k]}"')
        seen.add(k)
    for k, v in current.items():
        if k not in seen:
            lines.append(f'{k}="{v}"')
    ENV_FILE.write_text("\n".join(lines) + "\n")


def _mask(v: str | None) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "***"
    return f"{v[:4]}…{v[-4:]}"


@secured.get("/settings")
async def get_settings() -> dict:
    env = _read_env()
    return {k: {"set": bool(env.get(k)), "preview": _mask(env.get(k))} for k in SETTINGS_KEYS}


@secured.post("/settings")
async def update_settings(body: SettingsUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    _write_env(updates)
    for k, v in updates.items():
        os.environ[k] = v
    return {"ok": True, "updated": list(updates.keys())}


# ---------------------------- WebSocket ----------------------------

@app.websocket("/api/ws/{project_id}")
async def ws_project(ws: WebSocket, project_id: str) -> None:
    # WebSockets carry the JWT as ?token=... query param.
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4401)
        return
    try:
        claims = decode_token(token)
    except HTTPException:
        await ws.close(code=4401)
        return
    proj = await db.projects.find_one({"id": project_id, "owner_id": claims["sub"]}, {"_id": 0, "id": 1})
    if not proj:
        await ws.close(code=4404)
        return
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


# ---------------------------- Helpers ----------------------------

def _ext_lang(path: str) -> str:
    ext = (path.rsplit(".", 1)[-1] or "").lower()
    return {
        "html": "html", "htm": "html",
        "css": "css", "scss": "css", "sass": "css",
        "js": "javascript", "jsx": "javascript", "mjs": "javascript",
        "ts": "typescript", "tsx": "typescript",
        "json": "json", "md": "markdown",
        "py": "python", "rb": "ruby", "go": "go", "rs": "rust",
        "yml": "yaml", "yaml": "yaml",
    }.get(ext, "text")


# ---------------------------- App wiring ----------------------------

app.include_router(api)
app.include_router(secured)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
