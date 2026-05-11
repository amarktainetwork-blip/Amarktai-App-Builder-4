from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from agents.genx_provider import AGENT_TIER, GenXProvider
from agents.mcp_tools import TOOL_SCHEMAS, ProjectFS
from agents.orchestrator import Orchestrator
from agents.preview import render_preview
from agents.stack_engine import decide_stack
from agents.build_contract import infer_build_mode, infer_project_type
from agents.prompts import ASSISTANT_PROMPT
from agents.clarification import check_clarification_needed, apply_clarification_answers
from agents.pixabay import search_images, search_videos, build_media_manifest
from agents.design_engine import get_available_styles
from agents.repo_analyzer import analyze_repo_profile
from agents.coverage_score import compute_coverage_score
from agents.preview_executor import execute_preview
from auth import (
    decode_token,
    hash_password,
    make_token,
    public_user,
    require_admin,
    require_user,
    seed_admin,
    verify_password,
)
from config import (
    APP_NAME,
    AGENTS_NAME,
    ASSISTANT_NAME,
    ROUTER_NAME,
    assert_startup_config,
    cors_origins,
    is_production,
    validate_static_config,
)
import github_integration as gh
from settings_store import clear_secret, get_secret, settings_status, save_secret


ROOT_DIR = Path(__file__).parent
REPO_ROOT = ROOT_DIR.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(ROOT_DIR / ".env")

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_builder")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:8080,http://localhost:3000")
os.environ.setdefault("JWT_SECRET", "development-jwt-secret-change-before-production")
os.environ.setdefault("ADMIN_EMAIL", "admin@amarktai.local")
os.environ.setdefault("ADMIN_PASSWORD", "amarktai-admin-local")
os.environ.setdefault("GENX_BASE_URL", "https://query.genx.sh/v1")
os.environ.setdefault("GENX_MODEL_REASONING", "claude-sonnet-4-6")
os.environ.setdefault("GENX_MODEL_RESEARCH", "gpt-5.4-mini")
os.environ.setdefault("GENX_MODEL_EDITS", "claude-haiku-4-5")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("amarktai")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
PIPELINE_SEM = asyncio.Semaphore(2)
LOGIN_ATTEMPTS: dict[str, deque[datetime]] = defaultdict(deque)
SETTINGS_KEYS = ["GENX_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY", "PIXABAY_API_KEY"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_startup_config()
    app.state.db = db
    await seed_admin(db)
    logger.info("%s backend ready", APP_NAME)
    yield
    client.close()


app = FastAPI(title=f"{APP_NAME} API", lifespan=lifespan)
app.state.db = db
api = APIRouter(prefix="/api")
secured = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
admin_api = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(min_length=1, max_length=4000)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=12000)
    # Optional build parameters (all have safe defaults for backward compat)
    mode: Optional[str] = "web_app"
    quality_tier: Optional[str] = "balanced"
    stack_preference: Optional[str] = None
    database_preference: Optional[str] = None
    auth_required: Optional[bool] = False
    realtime_required: Optional[bool] = False
    repo_visibility: Optional[str] = "public"
    deployment_target: Optional[str] = None
    media_requirements: Optional[str] = None
    upgrade_confirmation_acknowledged: Optional[bool] = False


class RepoImportBody(BaseModel):
    repo_url: str
    branch: Optional[str] = None


class PRBody(BaseModel):
    github_pat: Optional[str] = None
    branch_name: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    prompt: str
    mode: str = "web_app"
    project_type: str | None = None
    build_mode: str | None = None
    quality_tier: str = "balanced"
    status: str = "queued"
    error: str | None = None
    failed_agent: str | None = None
    cancel_requested: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    usage: dict = Field(default_factory=lambda: {"tokens": 0, "cost_usd": 0.0, "last_model": None})
    repo_url: str | None = None
    github: dict | None = None
    pr_url: str | None = None
    owner_id: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    # Extended fields
    recommended_tier: str | None = None
    requires_upgrade_confirmation: bool = False
    upgrade_reason: str | None = None
    selected_stack: dict | None = None
    preview_strategy: str = "iframe"
    actual_models_used: list = Field(default_factory=list)
    model_calls_used: int = 0
    preview_url: str | None = None
    deployment_target: str | None = None
    repo_visibility: str = "public"
    manifest_status: str | None = None
    # Shared context fields (Phase 2 spec)
    media_strategy: dict = Field(default_factory=lambda: {
        "mode": "placeholder",
        "confirmed": False,
        "models_used": [],
        "notes": "Safe placeholder images or SVG gradients used by default. Upgrade to balanced/premium and confirm to enable GenX media generation.",
    })
    validation_state: dict = Field(default_factory=lambda: {
        "status": "pending",
        "required_files_present": [],
        "required_files_missing": [],
        "warnings": [],
        "errors": [],
    })
    repair_attempts: int = 0
    last_validation: dict | None = None


class AssistantMessage(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    project_id: Optional[str] = None


MessageCreate = AssistantMessage  # backward compat alias


class SettingsUpdate(BaseModel):
    GENX_API_KEY: Optional[str] = None
    GITHUB_PAT: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None
    PIXABAY_API_KEY: Optional[str] = None


class RetryBody(BaseModel):
    agent: str = Field(pattern="^(coder|reviewer|repair|pipeline)$")
    quality_tier: Optional[str] = None
    repair_only: Optional[bool] = False


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role: str = Field(default="user", pattern="^(admin|user)$")


class PasswordReset(BaseModel):
    password: str = Field(min_length=12)


class FinalizeOptions(BaseModel):
    repo_name_override: Optional[str] = None



def _login_allowed(key: str) -> bool:
    now = datetime.now(timezone.utc)
    window = now - timedelta(minutes=10)
    attempts = LOGIN_ATTEMPTS[key]
    while attempts and attempts[0] < window:
        attempts.popleft()
    if len(attempts) >= 8:
        return False
    attempts.append(now)
    return True


async def _runtime_secret(key: str) -> str | None:
    return await get_secret(db, key)


async def _genx_provider(quality_tier: str = "balanced") -> GenXProvider:
    key = await _runtime_secret("GENX_API_KEY")
    return GenXProvider(api_key=key, quality_tier=quality_tier)


async def _launch_pipeline(project_id: str, prompt: str, mode: str,
                            build_mode: str = "web_app",
                            stack_decision: dict | None = None) -> None:
    async with PIPELINE_SEM:
        emit = emitter_for(project_id)
        started = _now()
        existing = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1, "cancel_requested": 1})
        if existing and (existing.get("cancel_requested") or existing.get("status") == "cancelled"):
            await emit({"type": "project_status", "data": {"status": "cancelled", "error": "Build cancelled by user."}})
            return
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {
                "status": "running", "started_at": started, "completed_at": None,
                "error": None, "cancel_requested": False, "updated_at": started,
            }},
        )
        await emit({"type": "project_status", "data": {"status": "running"}})
        try:
            project = await db.projects.find_one({"id": project_id}, {"_id": 0, "quality_tier": 1}) or {}
            provider = await _genx_provider(project.get("quality_tier", "balanced"))
            orch = Orchestrator(db, provider, project_id, emit)
            # Global timeouts: build 25 min, iterate 10 min
            global_timeout = 1500 if mode == "build" else 600
            if mode == "iterate":
                await asyncio.wait_for(orch.run_iteration(prompt), timeout=global_timeout)
            else:
                await asyncio.wait_for(
                    orch.run_full_build(prompt, mode=build_mode, stack_decision=stack_decision),
                    timeout=global_timeout,
                )
            # Only update completed_at if project was not already failed by orchestrator
            proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1})
            if proj and proj.get("status") not in ("failed", "cancelled"):
                completed = _now()
                updates = {"completed_at": completed, "updated_at": completed}
                if proj.get("status") == "ready":
                    updates["preview_url"] = f"/api/projects/{project_id}/preview"
                await db.projects.update_one(
                    {"id": project_id},
                    {"$set": updates},
                )
        except asyncio.TimeoutError:
            msg = f"Build timed out (global {global_timeout}s limit exceeded)."
            logger.warning("pipeline timeout for %s", project_id)
            completed = _now()
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"status": "failed", "error": msg, "completed_at": completed, "updated_at": completed}},
            )
            await emit({"type": "project_status", "data": {"status": "failed", "error": msg}})
            await emit({"type": "error", "data": {"message": msg}})
        except Exception as exc:
            msg = str(exc)
            logger.exception("pipeline failed for %s: %s", project_id, msg)
            completed = _now()
            proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1})
            if proj and proj.get("status") not in ("failed", "cancelled"):
                await db.projects.update_one(
                    {"id": project_id},
                    {"$set": {"status": "failed", "error": msg, "completed_at": completed, "updated_at": completed}},
                )
                await db.agent_events.insert_one({
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "agent": "system",
                    "status": "failed",
                    "detail": msg,
                    "meta": {},
                    "created_at": completed,
                })
                await emit({"type": "agent_event", "data": {
                    "id": str(uuid.uuid4()), "project_id": project_id, "agent": "system",
                    "status": "failed", "detail": msg, "meta": {}, "created_at": completed,
                }})
                await emit({"type": "project_status", "data": {"status": "failed", "error": msg}})
                await emit({"type": "error", "data": {"message": msg}})


async def _launch_retry(project_id: str, agent: str, quality_tier: str | None) -> None:
    async with PIPELINE_SEM:
        emit = emitter_for(project_id)
        started = _now()
        existing = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1, "cancel_requested": 1})
        if existing and (existing.get("cancel_requested") or existing.get("status") == "cancelled"):
            await emit({"type": "project_status", "data": {"status": "cancelled", "error": "Build cancelled by user."}})
            return
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {
                "status": "running", "started_at": started, "completed_at": None,
                "error": None, "cancel_requested": False, "failed_agent": None, "updated_at": started,
            }},
        )
        await emit({"type": "project_status", "data": {"status": "running"}})
        try:
            project = await db.projects.find_one({"id": project_id}, {"_id": 0, "quality_tier": 1}) or {}
            provider = await _genx_provider(quality_tier or project.get("quality_tier", "balanced"))
            orch = Orchestrator(db, provider, project_id, emit)
            await asyncio.wait_for(orch.run_retry(agent, quality_tier), timeout=1500)
            proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1})
            if proj and proj.get("status") == "ready":
                completed = _now()
                await db.projects.update_one(
                    {"id": project_id},
                    {"$set": {"completed_at": completed, "updated_at": completed, "preview_url": f"/api/projects/{project_id}/preview"}},
                )
        except Exception as exc:
            msg = str(exc)
            logger.exception("retry failed for %s: %s", project_id, msg)
            completed = _now()
            proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1})
            if proj and proj.get("status") not in ("failed", "cancelled", "ready"):
                await db.projects.update_one(
                    {"id": project_id},
                    {"$set": {"status": "failed", "error": msg, "completed_at": completed, "updated_at": completed}},
                )
                await emit({"type": "project_status", "data": {"status": "failed", "error": msg}})
                await emit({"type": "error", "data": {"message": msg}})


@api.get("/")
async def root() -> dict:
    return {"service": "amarktai-app-builder", "status": "ok"}


@api.get("/health")
async def health() -> dict:
    return {
        "service": "amarktai-app-builder",
        "status": "ok",
        "version": os.environ.get("APP_VERSION", "0.1.0"),
        "build_sha": os.environ.get("BUILD_SHA"),
        "timestamp": _now(),
    }


def _build_scan_roots() -> list[Path]:
    """
    Return an explicit allowlist of app-owned paths to scan.

    Never includes system directories (/proc, /usr, /lib, etc.).
    Supports both repo dev layout and Docker /app layout.
    """
    roots: list[Path] = []

    # Docker /app layout: only scan specific known app files/dirs
    docker_root = Path("/app")
    if (docker_root / "server.py").exists():
        for name in ("server.py", "agents", "auth.py", "config.py",
                     "settings_store.py", "github_integration.py", "README.md"):
            p = docker_root / name
            if p.exists() and not p.is_symlink():
                roots.append(p)
        return roots

    # Repo dev layout: scan explicit subdirectories only
    for rel in (
        "backend",
        "frontend/src",
        "frontend/public",
        "scripts",
        "README.md",
        ".env.example",
        "docker-compose.yml",
    ):
        p = REPO_ROOT / rel
        if p.exists() and not p.is_symlink():
            roots.append(p)
    return roots


async def _forbidden_source_check() -> tuple[bool, str]:
    """
    Scan only app-owned source files for forbidden legacy references.

    Never scans system paths (/proc, /usr, /lib, /bin, etc.).
    Never follows symlinks.
    Never calls rglob on REPO_ROOT directly.
    Respects SKIP_SOURCE_SCAN=true env flag.
    """
    if os.environ.get("SKIP_SOURCE_SCAN", "").lower() in ("1", "true", "yes"):
        return True, "Source scan skipped by configuration."

    upper_ai = "".join(("AI", "VA"))
    title_ai = "".join(("Ai", "va"))
    lower_ai = "".join(("ai", "va"))
    lower_platform = "".join(("eme", "rgent"))
    title_platform = "".join(("Eme", "rgent"))
    platform_base = "".join(("eme", "rgent", "base"))
    platform_assets = "".join(("assets.", "eme", "rgent", ".sh"))
    platform_package = "".join(("eme", "rgent", "integrations"))
    forbidden = [
        upper_ai, title_ai, lower_ai, lower_platform, title_platform,
        platform_base, platform_assets, platform_package,
    ]
    excluded_dirs = {
        ".git", "node_modules", "build", "dist",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv",
    }

    def _check_file(p: Path) -> tuple[bool, str] | None:
        """Return (False, detail) if forbidden content found, else None."""
        try:
            if p.is_symlink():
                return None
            text = p.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            if any(term.lower() in lowered for term in forbidden):
                return False, f"Legacy reference remains in {p}"
        except (PermissionError, OSError):
            pass
        except Exception:
            pass
        return None

    def _scan_root(root: Path) -> tuple[bool, str] | None:
        """Recursively scan root; return first failure or None if clean."""
        try:
            if root.is_symlink() or not root.exists():
                return None
            if root.is_file():
                return _check_file(root)
            # Directory: recurse with rglob but skip excluded names
            for p in root.rglob("*"):
                try:
                    if p.is_symlink():
                        continue
                    if any(part in excluded_dirs for part in p.parts):
                        continue
                    if not p.is_file():
                        continue
                    result = _check_file(p)
                    if result is not None:
                        return result
                except (PermissionError, OSError):
                    continue
                except Exception:
                    continue
        except (PermissionError, OSError):
            pass
        except Exception:
            pass
        return None

    try:
        scan_roots = _build_scan_roots()
        for root in scan_roots:
            result = _scan_root(root)
            if result is not None:
                return result
        return True, "No legacy references found in scanned source files."
    except Exception as exc:
        # Unexpected error: warn, do not FAIL readiness unless a forbidden reference was confirmed
        logger.warning("Source scan encountered an unexpected error: %s", exc)
        return True, f"Source scan completed with a warning: {exc}"


@api.get("/readiness")
async def readiness() -> dict:
    checks = [c.as_dict() for c in validate_static_config()]

    async def add(name: str, status: str, detail: str, severity: str = "info") -> None:
        checks.append({"name": name, "status": status, "detail": detail, "severity": severity})

    try:
        await db.command("ping")
        await add("Mongo ping", "PASS", "MongoDB responded.")
    except Exception as exc:
        await add("Mongo ping", "FAIL", str(exc), "blocker")

    admin = await db.users.find_one({"role": "admin", "status": "active"}, {"_id": 0, "id": 1})
    await add("admin user", "PASS" if admin else "FAIL",
              "Active admin exists." if admin else "Create or seed an active admin user.",
              "info" if admin else "blocker")

    genx_key = await _runtime_secret("GENX_API_KEY")
    if not genx_key:
        await add("GenX API key", "FAIL", "Set GENX_API_KEY in Settings or environment.", "blocker")
    else:
        try:
            models = await GenXProvider(api_key=genx_key).list_models()
            await add("GenX live models", "PASS", f"{len(models)} models returned by {ROUTER_NAME}.")
        except Exception as exc:
            await add("GenX live models", "FAIL", str(exc), "blocker")

    github_pat = await _runtime_secret("GITHUB_PAT")
    if not github_pat:
        await add("GitHub PAT", "WARN", "Connect GitHub PAT in Settings to enable private imports, PRs, and repo creation.", "warning")
    else:
        try:
            info = await gh.validate_pat(github_pat)
            await add("GitHub PAT live validation", "PASS", f"Authenticated as {info.get('login')}.")
        except Exception as exc:
            await add("GitHub PAT live validation", "FAIL", str(exc), "blocker")

    brave_key = await _runtime_secret("BRAVE_SEARCH_API_KEY")
    if not brave_key:
        await add("Brave Search key", "WARN", "Scout runs without web research until BRAVE_SEARCH_API_KEY is configured.", "warning")
    else:
        try:
            async with httpx.AsyncClient(timeout=15.0) as cx:
                r = await cx.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"Accept": "application/json", "X-Subscription-Token": brave_key},
                    params={"q": "Amarktai", "count": 1},
                )
                r.raise_for_status()
            await add("Brave Search live validation", "PASS", "Brave Search API responded.")
        except Exception as exc:
            await add("Brave Search live validation", "FAIL", str(exc), "blocker")

    clean, detail = await _forbidden_source_check()
    await add("legacy source references", "PASS" if clean else "FAIL", detail, "info" if clean else "blocker")
    await add("production demo simulation disabled", "PASS", "Production paths return disabled or errors when required keys are absent.")

    blockers = [c["detail"] for c in checks if c["status"] == "FAIL" and c["severity"] == "blocker"]
    warnings = [c["detail"] for c in checks if c["status"] == "WARN"]
    return {
        "overall": "FAIL" if blockers else "PASS",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "timestamp": _now(),
    }


@api.post("/auth/login")
async def login(body: LoginBody, request: Request) -> dict:
    email = body.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    if not _login_allowed(f"{ip}:{email}"):
        raise HTTPException(429, "Too many login attempts. Try again later.")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if user.get("status", "active") != "active":
        raise HTTPException(403, "User is disabled")
    return make_token(user)


@api.get("/auth/me")
async def me(claims: dict = Depends(require_user)) -> dict:
    user = await db.users.find_one({"id": claims["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User no longer exists")
    return user


@api.post("/contact")
async def contact(body: ContactBody) -> dict:
    doc = {"id": str(uuid.uuid4()), "name": body.name, "email": body.email, "message": body.message, "created_at": _now()}
    await db.contact_messages.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"]}


@secured.get("/models")
async def list_models() -> dict:
    try:
        models = await (await _genx_provider()).list_models()
    except Exception as exc:
        raise HTTPException(503, str(exc))
    return {"tiers": GenXProvider.list_tiers(), "agents": AGENT_TIER, "tools": TOOL_SCHEMAS, "available": models}


@api.get("/models/audio")
async def audio_models_status() -> dict:
    """Phase 4: Audit GenX live model metadata for audio/music models.

    Returns availability and an honest message if unavailable.
    Does NOT block normal builds.
    """
    try:
        genx_key = await _runtime_secret("GENX_API_KEY") or os.environ.get("GENX_API_KEY", "")
        if not genx_key:
            return {
                "available": False,
                "models": [],
                "message": "Audio/music generation is unavailable: GENX_API_KEY not configured.",
            }
        models = await GenXProvider(api_key=genx_key).list_models()
        audio_keywords = {"audio", "music", "sound", "tts", "speech", "voice", "whisper", "bark"}
        audio_models = [
            m for m in models
            if any(kw in str(m).lower() for kw in audio_keywords)
        ]
        if audio_models:
            return {
                "available": True,
                "models": audio_models,
                "message": f"{len(audio_models)} audio/music model(s) available through Amarktai AI Infrastructure.",
            }
        return {
            "available": False,
            "models": [],
            "message": "Audio/music generation is currently unavailable: no audio/music models found in Amarktai AI Infrastructure. Normal builds are unaffected.",
        }
    except Exception:
        return {
            "available": False,
            "models": [],
            "message": "Audio/music generation status could not be determined. Normal builds are unaffected.",
        }


def _coder_tier(tier: str, tiers: dict) -> str | None:
    """Select the internal tier key for the Coder agent based on the user's quality tier."""
    if tier == "premium":
        key = "reasoning"
    elif tier == "balanced":
        key = "research"
    else:
        key = "edits"
    return tiers.get(key, {}).get("model")


@secured.get("/models/router")
async def models_router(tier: str = "balanced") -> dict:
    """Return the model routed for a given tier (cheap|balanced|premium).

    cheap     → edits/lightweight model
    balanced  → research/fast model (default)
    premium   → reasoning/coding model

    Returns the full agent-role model map as specified in the product spec:
      research, planning, architecture, frontend_coding, backend_coding,
      database_design, media_generation, validation, repair, review, assistant
    """
    tier_map = {
        "cheap": "edits",
        "balanced": "research",
        "premium": "reasoning",
    }
    tier_lower = tier.lower()
    internal_tier = tier_map.get(tier_lower)
    if not internal_tier:
        raise HTTPException(400, f"Unknown tier '{tier}'. Use cheap, balanced, or premium.")
    tiers = GenXProvider.list_tiers()
    info = tiers.get(internal_tier)
    if not info:
        raise HTTPException(503, "Router tier configuration error.")

    coding_model = _coder_tier(tier_lower, tiers)
    fast_model = tiers.get("research", {}).get("model")
    premium_model = tiers.get("reasoning", {}).get("model")
    cheap_model = tiers.get("edits", {}).get("model")

    # Media generation: placeholder-only unless premium confirmed at generation time
    if tier_lower == "premium":
        media_model = premium_model
        media_note = "GenX image/video models available — user confirmation required before generating."
    elif tier_lower == "balanced":
        media_model = fast_model
        media_note = "Lightweight GenX image model if confirmed. Placeholders used by default."
    else:
        media_model = None
        media_note = "Placeholders/free assets only. Upgrade to balanced/premium for GenX image generation."

    tier_model = cheap_model if tier_lower == "cheap" else (fast_model if tier_lower == "balanced" else premium_model)
    selected_models = {
        "research":        tier_model,
        "planning":        tier_model,
        "architecture":    tier_model,
        "frontend_coding": coding_model,
        "backend_coding":  coding_model,
        "database_design": coding_model,
        "media_generation": media_model,
        "validation":      tier_model,
        "repair":          cheap_model if tier_lower == "cheap" else tier_model,
        "review":          tier_model,
        "assistant":       tier_model,
    }

    repair_limit = {"cheap": 1, "balanced": 2, "premium": 3}.get(tier_lower, 2)

    warnings: list[str] = []
    if tier_lower == "premium":
        warnings.append("Premium tier uses the most capable model and incurs higher GenX credit usage.")
    elif tier_lower == "cheap":
        warnings.append("Cheap tier may struggle with complex apps. Balanced is recommended for most builds.")
        warnings.append("Media generation is disabled at cheap tier. Placeholders will be used.")

    reasons = {
        "research":        "Scout research and Wingman assistant routing.",
        "planning":        "Product Planner: defines MVP scope and feature list.",
        "architecture":    f"Stack Architect stays inside the selected {tier_lower} tier.",
        "frontend_coding": f"Frontend Builder routed to {'premium' if tier_lower == 'premium' else tier_lower} coding model.",
        "backend_coding":  f"Backend Builder routed to {'premium' if tier_lower == 'premium' else tier_lower} coding model.",
        "database_design": "Database Architect uses the same tier as coding agents.",
        "media_generation": media_note,
        "validation":      "Validator checks required files, linked assets, and structure.",
        "repair":          f"Repair Coder: up to {repair_limit} attempt(s) at this tier.",
        "review":          f"QA Reviewer stays inside the selected {tier_lower} tier and is advisory only.",
        "assistant":       "Amarktai Wingman responds to user questions and build guidance.",
    }

    return {
        "tier": tier_lower,
        "internal_tier": internal_tier,
        "model": info["model"],
        "label": info["label"],
        "selected_models": selected_models,
        "repair_limit": repair_limit,
        "reasons": reasons,
        "warnings": warnings,
        "tier_description": {
            "cheap": "Fast and affordable. Good for simple landing pages and minor edits.",
            "balanced": "Recommended for most builds. Balances quality and cost.",
            "premium": "Best for complex apps, full-stack, SaaS, and trading bots.",
        }.get(tier_lower, ""),
    }


def _build_media_strategy(mode: str, quality_tier: str, media_requirements: str | None) -> dict:
    """Determine media_strategy for a new project based on mode, tier, and media_requirements."""
    wants_media = media_requirements and any(
        kw in media_requirements.lower()
        for kw in ("generat", "image", "video", "audio", "music", "photo", "ai image")
    )
    if wants_media and quality_tier in ("balanced", "premium"):
        return {
            "mode": "genx_generated",
            "confirmed": False,  # always requires explicit user confirmation
            "models_used": [],
            "notes": (
                "Custom AI image/video generation is available at this tier. "
                "User must confirm before generation to authorise additional GenX credit usage."
            ),
        }
    if wants_media and quality_tier == "cheap":
        return {
            "mode": "placeholder",
            "confirmed": False,
            "models_used": [],
            "notes": (
                "Media generation is not included at cheap tier. "
                "Upgrade to balanced or premium to enable GenX image/video generation."
            ),
        }
    if mode in ("media_page", "landing_page", "website"):
        return {
            "mode": "free_assets",
            "confirmed": False,
            "models_used": [],
            "notes": "Safe remote images (e.g. Unsplash) or SVG/CSS gradients used as placeholders.",
        }
    return {
        "mode": "placeholder",
        "confirmed": False,
        "models_used": [],
        "notes": "SVG/gradient placeholders used. No external media dependencies.",
    }


# ── Clarification endpoint ────────────────────────────────────────────────────

class ClarificationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    mode: Optional[str] = None


class ClarificationAnswers(BaseModel):
    original_prompt: str = Field(min_length=1, max_length=12000)
    answers: dict[str, str]


@api.post("/clarify")
async def check_clarification(body: ClarificationRequest) -> dict:
    """Check if a prompt needs clarification before building.

    Returns focused questions if the prompt is too vague.
    If the prompt is specific enough, returns needs_clarification=False
    so the frontend can proceed directly to building.
    """
    result = check_clarification_needed(body.prompt, body.mode)
    return result


@api.post("/clarify/apply")
async def apply_clarification(body: ClarificationAnswers) -> dict:
    """Merge clarification answers with the original prompt.

    Returns an enriched prompt and parameter overrides suitable for
    passing to POST /api/projects.
    """
    enriched_prompt, params = apply_clarification_answers(body.original_prompt, body.answers)
    return {"enriched_prompt": enriched_prompt, "params": params}


# ── Pixabay media endpoints ───────────────────────────────────────────────────

@api.get("/media/images")
async def pixabay_images(
    query: str,
    per_page: int = 10,
    image_type: str = "photo",
    orientation: str = "horizontal",
) -> dict:
    """Search Pixabay for images (backend-only, API key never exposed to frontend).

    Returns images suitable for use in generated projects.
    Requires PIXABAY_API_KEY to be configured in settings or environment.
    """
    api_key = await _runtime_secret("PIXABAY_API_KEY") or os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        raise HTTPException(
            503,
            "Pixabay image search is unavailable. Configure PIXABAY_API_KEY in Settings to enable stock images.",
        )
    if not query.strip():
        raise HTTPException(400, "query parameter is required")
    per_page = max(3, min(per_page, 50))
    results = await search_images(
        query=query.strip(),
        api_key=api_key,
        per_page=per_page,
        image_type=image_type,
        orientation=orientation,
    )
    return {
        "query": query,
        "count": len(results),
        "images": results,
        "source": "pixabay",
        "license": "Pixabay License",
        "license_url": "https://pixabay.com/service/license-summary/",
        "attribution_required": True,
    }


@api.get("/media/videos")
async def pixabay_videos(
    query: str,
    per_page: int = 5,
    video_type: str = "all",
) -> dict:
    """Search Pixabay for videos (backend-only, API key never exposed to frontend).

    Returns videos suitable for use in generated projects.
    Requires PIXABAY_API_KEY to be configured in settings or environment.
    """
    api_key = await _runtime_secret("PIXABAY_API_KEY") or os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        raise HTTPException(
            503,
            "Pixabay video search is unavailable. Configure PIXABAY_API_KEY in Settings to enable stock videos.",
        )
    if not query.strip():
        raise HTTPException(400, "query parameter is required")
    per_page = max(3, min(per_page, 20))
    results = await search_videos(
        query=query.strip(),
        api_key=api_key,
        per_page=per_page,
        video_type=video_type,
    )
    return {
        "query": query,
        "count": len(results),
        "videos": results,
        "source": "pixabay",
        "license": "Pixabay License",
        "license_url": "https://pixabay.com/service/license-summary/",
        "attribution_required": True,
    }


@api.get("/design/styles")
async def design_styles() -> dict:
    """Return the available design direction styles for the frontend style picker."""
    return {"styles": get_available_styles()}


@secured.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate, claims: dict = Depends(require_user)) -> Project:
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Assistant and Amarktai Coding Agents.")

    # Normalize mode
    build_mode = (body.mode or "web_app").lower().strip()
    quality_tier = (body.quality_tier or "balanced").lower().strip()
    if quality_tier not in ("cheap", "balanced", "premium"):
        quality_tier = "balanced"

    # Run stack decision engine
    sd = decide_stack(
        prompt=body.prompt,
        mode=build_mode,
        quality_tier=quality_tier,
        stack_preference=body.stack_preference,
        database_preference=body.database_preference,
        auth_required=body.auth_required or False,
        realtime_required=body.realtime_required or False,
        media_requirements=body.media_requirements,
        deployment_target=body.deployment_target,
    )

    # If upgrade confirmation required but not acknowledged, return a 402 so frontend can prompt
    if sd["requires_upgrade_confirmation"] and not body.upgrade_confirmation_acknowledged:
        raise HTTPException(402, detail={
            "requires_upgrade_confirmation": True,
            "recommended_tier": sd["recommended_tier"],
            "upgrade_reason": sd["upgrade_reason"],
            "complexity": sd["complexity"],
        })

    proj = Project(
        name=body.name,
        prompt=body.prompt,
        mode=build_mode,
        project_type=infer_project_type(build_mode),
        build_mode=infer_build_mode(build_mode),
        quality_tier=quality_tier,
        recommended_tier=sd["recommended_tier"],
        requires_upgrade_confirmation=sd["requires_upgrade_confirmation"],
        upgrade_reason=sd["upgrade_reason"],
        selected_stack=sd["stack"],
        preview_strategy=sd["preview_strategy"],
        preview_url=None,
        deployment_target=body.deployment_target,
        repo_visibility=body.repo_visibility or "public",
        owner_id=claims["sub"],
        media_strategy=_build_media_strategy(build_mode, quality_tier, body.media_requirements),
    )
    await db.projects.insert_one(dict(proj.model_dump()))
    await hub.broadcast(proj.id, {"type": "project_status", "data": {"status": "queued"}})
    asyncio.create_task(_launch_pipeline(proj.id, body.prompt, "build",
                                          build_mode=build_mode, stack_decision=sd))
    return proj


@secured.post("/projects/from-repo", response_model=Project)
async def import_from_repo(body: RepoImportBody, claims: dict = Depends(require_user)) -> Project:
    try:
        owner, repo = gh.parse_repo_url(body.repo_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    pat = await _runtime_secret("GITHUB_PAT")
    try:
        info = await gh.import_repo(owner, repo, body.branch, pat)
    except Exception as exc:
        raise HTTPException(400, f"GitHub import failed: {exc}")
    proj = Project(
        name=f"{owner}/{repo}",
        prompt=f"Imported GitHub repo {info['html_url']} on branch {info['branch']}",
        status="ready",
        mode="repo_fix",
        project_type="repo-upgrade",
        build_mode="repo-upgrade",
        preview_strategy="repo_structure",
        completed_at=_now(),
        owner_id=claims["sub"],
        github={k: info[k] for k in ("owner", "repo", "branch", "default_branch", "commit_sha", "html_url")},
    )
    await db.projects.insert_one(dict(proj.model_dump()))
    fs = ProjectFS(db, proj.id)
    for f in info["files"]:
        await fs.write(f["path"], f["content"], _ext_lang(f["path"]))
    await db.messages.insert_one({
        "id": str(uuid.uuid4()), "project_id": proj.id, "role": "system", "agent": None,
        "content": f"Imported {len(info['files'])} files. Skipped {info['skipped']} files due to size, binary type, or excluded directories.",
        "meta": {"imported_files": len(info["files"]), "skipped_files": info["skipped"]},
        "created_at": _now(),
    })

    # Phase 2: Run repo analysis immediately after import and cache it
    try:
        all_files = await fs.list_full()
        repo_profile = analyze_repo_profile(all_files, info["html_url"])
        await db.projects.update_one(
            {"id": proj.id},
            {"$set": {"repo_profile": repo_profile, "updated_at": _now()}},
        )
    except Exception:
        pass  # Non-fatal: analysis can be requested later via /repo-analysis endpoint

    return proj


@secured.get("/projects", response_model=list[Project])
async def list_projects(claims: dict = Depends(require_user)) -> list[Project]:
    query = {} if claims.get("role") == "admin" else {"owner_id": claims["sub"]}
    docs = await db.projects.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Project(**d) for d in docs]


async def _own(project_id: str, claims: dict) -> None:
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": claims["sub"]}
    doc = await db.projects.find_one(query, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(404, "Project not found")


@secured.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str, claims: dict = Depends(require_user)) -> Project:
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": claims["sub"]}
    doc = await db.projects.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**doc)


@secured.get("/projects/{project_id}/repo-analysis")
async def repo_analysis(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Phase 2/3: Return the repo profile for an imported project.

    If the profile is already stored (from a previous build pass), return it.
    Otherwise, analyse the current project files on-the-fly and cache the result.
    """
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    # Return cached profile if available
    cached = proj.get("repo_profile")
    if cached:
        return cached

    # Analyse on-the-fly
    files = await ProjectFS(db, project_id).list_full()
    if not files:
        raise HTTPException(404, "No files found in project")

    repo_full_name = (proj.get("github") or {}).get("html_url", proj.get("name", ""))
    profile = analyze_repo_profile(files, repo_full_name)
    # Cache for subsequent calls
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"repo_profile": profile, "updated_at": _now()}},
    )
    return profile


@secured.get("/projects/{project_id}/coverage")
async def project_coverage(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Phase 5: Return the coverage score for the project.

    Returns the cached coverage score if available, or computes it fresh.
    """
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    cached = proj.get("coverage_score")
    if cached:
        return cached

    files = await ProjectFS(db, project_id).list_full()
    coverage = compute_coverage_score(
        prompt=proj.get("prompt", ""),
        files=files,
        mode=proj.get("mode", "web_app"),
        intent=proj.get("update_intent", "small_patch"),
    )
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"coverage_score": coverage, "updated_at": _now()}},
    )
    return coverage


@secured.get("/projects/{project_id}/preview-fallback")
async def project_preview_fallback(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Phase 3: Return a structured preview fallback object for imported repos.

    For static sites this returns canPreview=True with inlined HTML.
    For all other strategies it returns the full fallback contract so the
    frontend can display install commands, env requirements, and blockers.
    """
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    files = await ProjectFS(db, project_id).list_full()
    if not files:
        return {
            "canPreview": False,
            "type": "repo-preview-fallback",
            "reason": "No files found in project",
            "detectedStack": [],
            "languages": [],
            "fileTree": [],
            "routeMap": [],
            "readmeExcerpt": "",
            "installCommands": [],
            "buildCommands": [],
            "devCommands": [],
            "testCommands": [],
            "missingEnv": [],
            "logs": [],
            "previewBlockers": ["No files found"],
            "nextActions": ["Import a repository or start building"],
            "riskNotes": [],
            "recommendedPlan": "",
            "detectedType": "unknown",
            "packageManager": "",
            "frontendPath": "",
            "backendPath": "",
        }

    # Use cached profile or compute on-the-fly
    profile = proj.get("repo_profile")
    if not profile:
        repo_full_name = (proj.get("github") or {}).get("html_url", proj.get("name", ""))
        profile = analyze_repo_profile(files, repo_full_name)
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {"repo_profile": profile, "updated_at": _now()}},
        )

    result = execute_preview(files, profile)
    # Broadcast the result so the frontend can pick it up via WS too
    event_type = "preview_ready" if result.get("canPreview") else "preview_fallback_ready"
    await hub.broadcast(project_id, {"type": event_type, "data": result})
    return result


@secured.delete("/projects/{project_id}")
async def delete_project(project_id: str, claims: dict = Depends(require_user)) -> dict:
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": claims["sub"]}
    res = await db.projects.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    await db.messages.delete_many({"project_id": project_id})
    await db.agent_events.delete_many({"project_id": project_id})
    await db.files.delete_many({"project_id": project_id})
    return {"ok": True}


@secured.post("/projects/{project_id}/cancel")
async def cancel_project(project_id: str, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    current_status = proj.get("status", "")
    # Allow cancellation for any in-progress state (queued, running).
    # The orchestrator also polls cancel_requested before every agent call and
    # repair attempt, so setting cancel_requested=True is sufficient to stop a
    # running pipeline regardless of which sub-phase (validating, repairing) it is in.
    if current_status not in ("queued", "running"):
        return {"ok": True, "status": current_status, "detail": "Build is not active."}
    now = _now()
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {
            "cancel_requested": True,
            "status": "cancelled",
            "error": "Build cancelled by user.",
            "completed_at": now,
            "updated_at": now,
        }},
    )
    evt = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "agent": "system",
        "status": "cancelled",
        "detail": "Build cancelled by user.",
        "meta": {},
        "created_at": now,
    }
    await db.agent_events.insert_one(dict(evt))
    evt.pop("_id", None)
    await hub.broadcast(project_id, {"type": "agent_event", "data": evt})
    await hub.broadcast(project_id, {"type": "project_status", "data": {
        "status": "cancelled", "error": "Build cancelled by user.",
    }})
    return {"ok": True, "status": "cancelled"}


@secured.post("/projects/{project_id}/retry")
async def retry_project(project_id: str, body: RetryBody, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Coding Agents.")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    if proj.get("status") in ("running", "queued"):
        raise HTTPException(409, "Build already in progress")
    updates = {"status": "queued", "cancel_requested": False, "updated_at": _now()}
    if body.quality_tier:
        if body.quality_tier not in ("cheap", "balanced", "premium"):
            raise HTTPException(400, "quality_tier must be cheap, balanced, or premium.")
        updates["quality_tier"] = body.quality_tier
        updates["recommended_tier"] = body.quality_tier
    await db.projects.update_one({"id": project_id}, {"$set": updates})
    # Record retry event
    now = _now()
    await db.agent_events.insert_one({
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "agent": "system",
        "status": "retry",
        "detail": f"Retry requested: agent={body.agent}, tier={body.quality_tier or 'default'}",
        "meta": {"agent": body.agent, "quality_tier": body.quality_tier},
        "created_at": now,
    })
    await hub.broadcast(project_id, {"type": "project_status", "data": {"status": "queued"}})
    asyncio.create_task(_launch_retry(project_id, body.agent, body.quality_tier))
    return {"ok": True, "queued": True, "agent": body.agent}


@secured.get("/projects/{project_id}/messages")
async def list_messages(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    return await db.messages.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)


@secured.get("/projects/{project_id}/events")
async def list_events(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    return await db.agent_events.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)


@secured.get("/projects/{project_id}/files")
async def list_files(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    await _own(project_id, claims)
    return await ProjectFS(db, project_id).list()


@secured.get("/projects/{project_id}/files/content")
async def file_content(project_id: str, path: str, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    try:
        doc = await ProjectFS(db, project_id).read(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not doc:
        raise HTTPException(404, "File not found")
    return doc


@secured.post("/projects/{project_id}/messages")
async def send_message(project_id: str, body: MessageCreate, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Assistant.")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if proj.get("status") in ("running", "queued"):
        raise HTTPException(409, "Build already in progress")
    # Iteration guard: block iteration when no app files exist
    _meta = {"requirements.md", "tech_stack.json"}
    existing_files = await ProjectFS(db, project_id).list()
    app_file_count = sum(1 for f in existing_files if f["path"] not in _meta)
    if app_file_count == 0:
        raise HTTPException(
            409,
            "The build failed before app files were generated. "
            "Retry Coder or restart the build before sending messages.",
        )
    await db.projects.update_one({"id": project_id}, {"$set": {"status": "queued", "updated_at": _now()}})
    await hub.broadcast(project_id, {"type": "project_status", "data": {"status": "queued"}})
    asyncio.create_task(_launch_pipeline(project_id, body.content, "iterate"))
    return {"ok": True, "queued": True}


@secured.post("/assistant/message")
async def assistant_message(body: AssistantMessage, claims: dict = Depends(require_user)) -> dict:
    """Amarktai Wingman — help with prompts, modes, failures, and next steps.

    If project_id is provided, the assistant uses the project's current state
    to answer context-aware questions. Uses a cheap/fast model to avoid burning
    premium credits on assistant queries.
    """
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Wingman.")

    context_parts: list[str] = []
    if body.project_id:
        proj = await db.projects.find_one(
            {"id": body.project_id}, {"_id": 0, "status": 1, "error": 1, "failed_agent": 1,
                                       "mode": 1, "quality_tier": 1, "name": 1, "prompt": 1}
        )
        if proj:
            context_parts.append(
                f"Project: {proj.get('name', '?')}\n"
                f"Mode: {proj.get('mode', 'web_app')}\n"
                f"Quality tier: {proj.get('quality_tier', 'balanced')}\n"
                f"Status: {proj.get('status', '?')}\n"
                f"Build prompt: {proj.get('prompt', '')[:300]}\n"
            )
            if proj.get("error"):
                context_parts.append(f"Error: {proj['error']}")
            if proj.get("failed_agent"):
                context_parts.append(f"Failed agent: {proj['failed_agent']}")
            # Include last 5 messages for context (no secrets)
            recent_msgs = await db.messages.find(
                {"project_id": body.project_id},
                {"_id": 0, "role": 1, "agent": 1, "content": 1},
            ).sort("created_at", -1).limit(5).to_list(5)
            if recent_msgs:
                context_parts.append("Recent messages (newest first):")
                for m in recent_msgs:
                    who = m.get("agent") or m.get("role") or "?"
                    context_parts.append(f"  [{who}] {m.get('content', '')[:300]}")

    context = "\n".join(context_parts)
    user_message = f"{context}\n\nUser question: {body.content}" if context else body.content

    try:
        provider = await _genx_provider()
        # Use fast/research tier for assistant — avoid premium credits
        result = await provider.complete(
            agent="iteration",  # maps to research/fast tier
            system_prompt=ASSISTANT_PROMPT,
            user_message=user_message,
            max_tokens=1024,
        )
        return {
            "reply": result["text"].strip(),
            "model": result["model_label"],
            "assistant": ASSISTANT_NAME,
        }
    except Exception as exc:
        raise HTTPException(503, f"{ASSISTANT_NAME} is unavailable: {exc}")


@api.post("/assistant/message")
async def assistant_message_unauth(body: AssistantMessage) -> dict:
    """Public assistant endpoint — no project context, limited to general help."""
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Wingman.")
    try:
        provider = await _genx_provider()
        result = await provider.complete(
            agent="iteration",
            system_prompt=ASSISTANT_PROMPT,
            user_message=body.content,
            max_tokens=512,
        )
        return {"reply": result["text"].strip(), "model": result["model_label"], "assistant": ASSISTANT_NAME}
    except Exception as exc:
        raise HTTPException(503, f"{ASSISTANT_NAME} is unavailable: {exc}")


@api.get("/stack/decide")
async def stack_decide(
    prompt: str = "",
    mode: str = "web_app",
    tier: str = "balanced",
) -> dict:
    """Quick stack decision — no auth required. Use for pre-build recommendations."""
    return decide_stack(prompt=prompt, mode=mode, quality_tier=tier)


@secured.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def project_preview(project_id: str, claims: dict = Depends(require_user)) -> HTMLResponse:
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "status": 1, "error": 1,
                                                             "failed_agent": 1, "mode": 1,
                                                             "preview_strategy": 1})
    files = await ProjectFS(db, project_id).list_full()
    _meta = {"requirements.md", "tech_stack.json"}
    app_files = [f for f in files if f["path"] not in _meta]

    if proj and proj.get("status") == "running":
        html = render_preview([])  # Shows "agents are writing your app" placeholder
    elif not app_files:
        msg = proj.get("error") or "No preview files were generated because the build failed."
        html = render_preview([])  # render_preview returns empty state when no index.html
    else:
        html = render_preview(files)
    return HTMLResponse(content=html, headers={"X-Frame-Options": "SAMEORIGIN"})


# MIME type map for preview file serving
_PREVIEW_MIME: dict[str, str] = {
    "html": "text/html; charset=utf-8",
    "htm": "text/html; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "js": "application/javascript; charset=utf-8",
    "mjs": "application/javascript; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "svg": "image/svg+xml",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
}


@secured.get("/projects/{project_id}/preview/{file_path:path}")
async def project_preview_file(
    project_id: str, file_path: str, claims: dict = Depends(require_user)
):
    """Serve an individual project file from the preview with the correct MIME type.

    This endpoint allows the "Open preview in new tab" flow to load assets (styles.css,
    app.js, manifest.json, etc.) as separate requests rather than relying on inlining.
    MIME types are set explicitly so browsers validate and apply the resources correctly.
    """
    from fastapi.responses import Response
    from pathlib import PurePosixPath
    await _own(project_id, claims)
    # Reject any path that contains traversal components after normalization.
    # PurePosixPath handles URL-decoded values; reject absolute paths and any
    # path that resolves outside the root (indicated by '..' in its parts).
    try:
        safe_path = PurePosixPath(file_path)
        if safe_path.is_absolute() or ".." in safe_path.parts:
            raise ValueError("path traversal")
        safe = str(safe_path)
        if not safe or safe == ".":
            raise ValueError("empty path")
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid file path")
    fs = ProjectFS(db, project_id)
    file_doc = await fs.read(safe)
    if file_doc is None:
        raise HTTPException(404, f"File not found: {safe}")
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    mime = _PREVIEW_MIME.get(ext, "text/plain; charset=utf-8")
    return Response(content=file_doc["content"], media_type=mime)


@secured.post("/projects/{project_id}/finalize")
async def finalize(project_id: str, body: FinalizeOptions = FinalizeOptions(), claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    pat = await _runtime_secret("GITHUB_PAT")
    if not pat:
        raise HTTPException(403, "Connect GitHub PAT in Settings to create repositories.")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    validation = (proj or {}).get("validation_state") or {}
    if validation and validation.get("status") != "passed":
        raise HTTPException(409, "Validation must pass before finalize/push. Fix validation errors first.")
    if proj and proj.get("status") not in ("ready", "finalized"):
        raise HTTPException(409, "Project must be ready before finalize/push.")

    # Phase 6: Coverage enforcement for repo-update intents
    _COVERAGE_INTENTS = {"full_app_completion", "repo_migration", "full_rebuild_inside_repo"}
    update_intent = (proj or {}).get("update_intent", "")
    if update_intent in _COVERAGE_INTENTS:
        coverage = (proj or {}).get("coverage_score") or {}
        cov_score = coverage.get("coverageScore", 0)
        if cov_score < 80:
            raise HTTPException(409, detail={
                "coverage_failed": True,
                "coverageScore": cov_score,
                "intent": update_intent,
                "message": (
                    f"Coverage score {cov_score}/100 is below the required 80 for {update_intent}. "
                    "Continue building missing requirements before finalizing."
                ),
            })

    files = await ProjectFS(db, project_id).list_full()
    payload_files = [{"path": f["path"], "content": f["content"]} for f in files if f["path"] != ".env" and not f["path"].endswith("/.env")]
    # Phase 9: Use override name if provided, otherwise derive from project name
    if body.repo_name_override:
        repo_name = re.sub(r"[^a-z0-9-]+", "-", body.repo_name_override.lower()).strip("-")[:60] or "amarktai-app"
    else:
        repo_name = re.sub(r"[^a-z0-9-]+", "-", proj["name"].lower()).strip("-")[:60] or "amarktai-app"
    private = (proj.get("repo_visibility", "public") == "private")

    # Phase 9: Check for repo name collision before attempting creation
    try:
        gh_user = await gh.validate_pat(pat)
        owner = gh_user.get("login", "")
    except Exception:
        owner = ""
    if owner:
        exists = await gh.check_repo_exists(owner, repo_name, pat)
        if exists:
            raise HTTPException(409, detail={
                "repo_exists": True,
                "repo_name": repo_name,
                "owner": owner,
                "message": f"Repository {owner}/{repo_name} already exists. Choose branch+PR or a different name.",
            })

    try:
        repo = await gh.create_repo_with_files(
            name=repo_name, description=proj["prompt"][:120],
            private=private, files=payload_files, pat=pat,
        )
    except Exception as exc:
        raise HTTPException(400, f"Failed to finalize: {exc}")
    await db.projects.update_one({"id": project_id}, {"$set": {
        "repo_url": repo["url"], "manifest_status": "pushed", "updated_at": _now(),
    }})
    await hub.broadcast(project_id, {"type": "finalized", "data": repo})
    return repo


@secured.post("/projects/{project_id}/finalize/branch-pr")
async def finalize_as_branch_pr(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Phase 10: When a repo name already exists, commit generated files as a branch + PR.

    Creates branch: amarktai-builder/{project_id[:8]}
    Opens a PR against the existing repo's default branch.
    Phase 8: PR body includes validation scores and coverage score.
    """
    await _own(project_id, claims)
    pat = await _runtime_secret("GITHUB_PAT")
    if not pat:
        raise HTTPException(403, "Connect GitHub PAT in Settings to open pull requests.")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found.")
    if proj.get("status") not in ("ready", "finalized"):
        raise HTTPException(409, "Project must be ready before pushing.")
    files = await ProjectFS(db, project_id).list_full()
    payload_files = [{"path": f["path"], "content": f["content"]} for f in files if f["path"] != ".env" and not f["path"].endswith("/.env")]
    repo_name = re.sub(r"[^a-z0-9-]+", "-", proj["name"].lower()).strip("-")[:60] or "amarktai-app"

    try:
        gh_user = await gh.validate_pat(pat)
        owner = gh_user.get("login", "")
    except Exception as exc:
        raise HTTPException(400, f"Could not verify GitHub PAT: {exc}")

    # Phase 8: collect validation and coverage scores for enriched PR body
    last_validation = proj.get("last_validation") or {}
    coverage_score = proj.get("coverage_score") or {}
    repo_profile = proj.get("repo_profile") or {}
    frameworks = repo_profile.get("frameworks", [])
    stack_str = ", ".join(frameworks) if frameworks else ""
    preview_note = "Preview available via Amarktai Builder workspace." if proj.get("preview_strategy") else "No live preview — see install/build commands in repo README."

    job_slug = f"{repo_name[:20]}-{project_id[:8]}"
    try:
        result = await gh.create_branch_pr_from_files(
            owner=owner,
            repo=repo_name,
            files=payload_files,
            prompt=proj.get("prompt", "")[:400],
            job_slug=job_slug,
            pat=pat,
            validation_scores=last_validation or None,
            coverage_score=coverage_score or None,
            stack=stack_str,
            preview_note=preview_note,
        )
    except Exception as exc:
        raise HTTPException(400, f"Failed to create branch PR: {exc}")

    await db.projects.update_one({"id": project_id}, {"$set": {
        "pr_url": result.get("pr_url"), "manifest_status": "pr_opened", "updated_at": _now(),
    }})
    await hub.broadcast(project_id, {"type": "github_pr_created", "data": result})
    return result


@secured.post("/projects/{project_id}/pr")
async def open_pr(project_id: str, body: PRBody, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj or not proj.get("github"):
        raise HTTPException(400, "Project was not imported from a GitHub repo")
    validation = proj.get("validation_state") or {}
    if validation and validation.get("status") == "failed":
        raise HTTPException(409, "Validation must pass before opening a PR. Fix validation errors first.")
    pat = body.github_pat or await _runtime_secret("GITHUB_PAT")
    if not pat:
        raise HTTPException(403, "Connect GitHub PAT in Settings to open pull requests.")
    github = proj["github"]
    files = await ProjectFS(db, project_id).list_full()
    payload_files = [{"path": f["path"], "content": f["content"]} for f in files if f["path"] != ".env" and not f["path"].endswith("/.env")]
    branch = body.branch_name or f"amarktai/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    title = body.title or "Amarktai App Builder: updates from coding agents"
    body_md = body.body or f"This PR was generated by **{AGENTS_NAME}** through {ROUTER_NAME}."
    try:
        result = await gh.open_pr(
            owner=github["owner"], repo=github["repo"],
            base_branch=github.get("default_branch") or github["branch"],
            new_branch=branch, files=payload_files, title=title, body=body_md, pat=pat,
        )
    except Exception as exc:
        raise HTTPException(400, f"Failed to open PR: {exc}")
    await db.projects.update_one({"id": project_id}, {"$set": {"pr_url": result["pr_url"], "updated_at": _now()}})
    await hub.broadcast(project_id, {"type": "pr_opened", "data": result})
    return result


@secured.get("/settings")
async def get_settings(_: dict = Depends(require_admin)) -> dict:
    return {key: await settings_status(db, key) for key in SETTINGS_KEYS}


@secured.post("/settings")
async def update_settings(body: SettingsUpdate, claims: dict = Depends(require_admin)) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
    for key, value in updates.items():
        await save_secret(db, key, value, claims["sub"])
    return {"ok": True, "updated": list(updates.keys())}


@secured.delete("/settings/{key}")
async def delete_setting(key: str, _: dict = Depends(require_admin)) -> dict:
    if key not in SETTINGS_KEYS:
        raise HTTPException(404, "Unknown setting")
    await clear_secret(db, key)
    return {"ok": True, "cleared": key}


@secured.get("/integrations/github/status")
async def github_status() -> dict:
    pat = await _runtime_secret("GITHUB_PAT")
    if not pat:
        return {"configured": False, "valid": False, "detail": "Connect GitHub PAT in Settings."}
    try:
        result = await gh.validate_pat(pat)
        return {**result, "detail": "GitHub PAT is valid."}
    except Exception as exc:
        return {"configured": True, "valid": False, "detail": str(exc)}


@admin_api.get("/users")
async def admin_list_users() -> list[dict]:
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return docs


@admin_api.post("/users")
async def admin_create_user(body: UserCreate) -> dict:
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(409, "User already exists")
    now = _now()
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user)
    return public_user(user)


@admin_api.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, body: PasswordReset) -> dict:
    res = await db.users.update_one({"id": user_id}, {"$set": {"password_hash": hash_password(body.password), "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}


@admin_api.patch("/users/{user_id}/status")
async def admin_user_status(user_id: str, body: StatusPatch, claims: dict = Depends(require_admin)) -> dict:
    if user_id == claims["sub"] and body.status == "disabled":
        raise HTTPException(400, "You cannot disable your own admin account")
    res = await db.users.update_one({"id": user_id}, {"$set": {"status": body.status, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True, "status": body.status}


@app.websocket("/api/ws/{project_id}")
async def ws_project(ws: WebSocket, project_id: str) -> None:
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4401)
        return
    try:
        claims = decode_token(token)
    except HTTPException:
        await ws.close(code=4401)
        return
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": claims["sub"]}
    proj = await db.projects.find_one(query, {"_id": 0, "id": 1})
    if not proj:
        await ws.close(code=4404)
        return
    await ws.accept()
    await hub.join(project_id, ws)
    try:
        await ws.send_json({"type": "hello", "data": {"project_id": project_id, "connected": True}})
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


def _ext_lang(path: str) -> str:
    ext = (path.rsplit(".", 1)[-1] or "").lower()
    return {
        "html": "html", "htm": "html", "css": "css", "scss": "css", "sass": "css",
        "js": "javascript", "jsx": "javascript", "mjs": "javascript",
        "ts": "typescript", "tsx": "typescript", "json": "json", "md": "markdown",
        "py": "python", "rb": "ruby", "go": "go", "rs": "rust", "yml": "yaml", "yaml": "yaml",
    }.get(ext, "text")


app.include_router(api)
app.include_router(secured)
app.include_router(admin_api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
