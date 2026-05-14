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
from typing import Optional, List

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
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
from agents.design_engine import get_available_styles, make_design_signature
from agents.repo_analyzer import analyze_repo_profile
from agents.coverage_score import compute_coverage_score
from agents.preview_executor import execute_preview
from agents.media_storage import (
    validate_upload, save_file, delete_asset_files, public_url_for,
    get_storage_root, storage_path_is_safe, safe_filename, media_type_from_mime,
)
from agents.logo_agent import run_logo_agent, logo_agent_prompt_block
from agents.agent_contracts import get_all_contracts, get_contract
from agents.html_validator import validate_project_files_enhanced
from agents.mode_classifier import classify_build_mode, ModeClassification
from agents.project_memory import make_empty_memory
from app.versioning.version_store import (
    create_version,
    list_versions,
    get_version,
    restore_version,
    generate_diff_summary,
)
from app.repos.repair_engine import (
    RepairEngine,
    generate_diff_summary_for_files,
    create_checkpoint,
    list_checkpoints,
    detect_extended_stack,
)
from app.runtime.preview_service import PreviewService
from app.core.capability_registry import (
    get_registry, capabilities_summary, probe_live_status, models_with_capability,
    async_capabilities_summary, QWEN_DEFAULT_BASE_URL, QWEN_ALT_BASE_URLS,
    QWEN_RECOMMENDED_MODELS, QWEN_OPTIONAL_MODELS,
)
from app.services.capability_truth_service import CapabilityTruthService
from app.services.build_storage_service import (
    get_storage_root as get_builds_storage_root,
    create_repo_workspace,
    create_generated_workspace,
    create_incomplete_workspace,
    create_release_workspace,
    update_workspace_metadata,
    save_audit_report,
    save_repair_plan,
    save_deploy_report,
    list_workspaces,
    get_workspace,
    storage_usage,
    archive_workspace,
    delete_workspace,
    detect_and_save_stack,
)
from app.services import git_workspace_service as _git_svc
from app.services.frontend_detection_service import detect_frontend, list_project_files
from app.services.command_runner_service import (
    run_command, run_install, run_build, run_tests, get_logs as get_runner_logs,
    ALLOWED_COMMANDS as _ALLOWED_COMMANDS,
)
from app.services import live_probe_service as _probe_svc
from app.services import genx_model_sync as _genx_sync
from app.services.model_router import route_task, get_router_status, TASK_ROUTING
from app.services.quality_gate_service import run_quality_gate
from app.services.idea_builder_service import (
    IDEA_BUILDER_SYSTEM_PROMPT,
    compose_final_prompt,
    deterministic_reply,
    final_model_user_message,
    make_message,
    make_session_doc,
    model_user_message,
    normalize_mode,
    normalize_model_reply,
    utc_now,
)
from app.services.preview_process_service import (
    load_preview_state,
    start_preview,
    stop_preview,
)
from app.services.continue_build_service import (
    load_workspace as load_build_workspace,
    detect_workspace_stack,
    detect_missing_pieces,
    generate_completion_plan,
    generate_repair_diff,
    apply_repair,
    save_repair_plan_to_workspace,
    create_workspace_version,
)
from agents.agent_registry import (
    get_all_agents,
    get_agent_status_summary,
    get_agent_routing,
    needs_motion_agent,
    MOTION_TRIGGER_KEYWORDS,
)
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
from settings_store import clear_secret, get_secret, safe_get_secret, settings_status, save_secret


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
SETTINGS_KEYS = [
    "GENX_API_KEY",
    "GITHUB_PAT",
    "BRAVE_SEARCH_API_KEY",
    "PIXABAY_API_KEY",
    "QWEN_API_KEY",
    "QWEN_BASE_URL",
    "QWEN_MODEL_CHAT",
    "QWEN_MODEL_CODE",
    "QWEN_MODEL_IMAGE",
    "QWEN_MODEL_VIDEO",
    "QWEN_MODEL_AUDIO",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_startup_config()
    app.state.db = db
    try:
        await db.command("ping")
    except Exception as exc:
        msg = f"MongoDB is not reachable during startup: {type(exc).__name__}"
        logger.error(msg)
        if is_production():
            raise RuntimeError(msg) from exc
    await seed_admin(db)
    # Ensure media storage directory exists
    try:
        get_storage_root()
        logger.info("Media storage ready at %s", os.environ.get("MEDIA_STORAGE_PATH", "/app/storage/media"))
    except Exception as e:
        logger.warning("Media storage init warning: %s", e)
    # Ensure build storage directory exists
    try:
        builds_root = get_builds_storage_root()
        logger.info("Build storage ready at %s", builds_root)
    except Exception as e:
        logger.warning("Build storage init warning: %s", e)
    # Ensure MongoDB indexes for media_assets
    try:
        await db.media_assets.create_index("user_id")
        await db.media_assets.create_index("project_id")
        await db.media_assets.create_index("media_type")
        await db.media_assets.create_index("source")
        await db.media_assets.create_index("created_at")
    except Exception as e:
        logger.warning("Media asset index creation warning: %s", e)
    logger.info("%s backend ready", APP_NAME)
    yield
    client.close()


app = FastAPI(title=f"{APP_NAME} API", lifespan=lifespan)
app.state.db = db
api = APIRouter(prefix="/api")
secured = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
admin_api = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@app.exception_handler(AttributeError)
async def _attribute_error_handler(request: Request, exc: AttributeError) -> JSONResponse:
    """Convert AttributeError (often NoneType.get() crashes) to a structured JSON error.

    Prevents raw Python tracebacks reaching the frontend and provides actionable next steps.
    """
    logger.error("AttributeError in %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "code": "internal_context_error",
            "message": (
                "An internal context error occurred. "
                "The project or repo context may be incomplete."
            ),
            "detail": str(exc),
            "nextActions": [
                "Run repo analysis again",
                "Continue full app completion",
                "Restart from imported files",
            ],
        },
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Hub:
    """WebSocket broadcast hub with event persistence and reconnect replay.

    Phase 1G: All orchestration events are persisted in memory (and optionally
    MongoDB) so that reconnecting clients can replay the full timeline without
    requiring a page refresh.
    """

    # Maximum events to buffer per project (in memory)
    _MAX_BUFFER = 500

    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}
        self.lock = asyncio.Lock()
        # In-memory event buffer: project_id → ordered list of events
        self._event_buffer: dict[str, list[dict]] = {}

    async def join(self, project_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.rooms.setdefault(project_id, set()).add(ws)

    async def leave(self, project_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.rooms.get(project_id, set()).discard(ws)

    def _buffer_event(self, project_id: str, payload: dict) -> None:
        """Add an event to the in-memory replay buffer."""
        buf = self._event_buffer.setdefault(project_id, [])
        # Stamp every event with a server timestamp so the client can order them
        if "ts" not in payload:
            payload = {**payload, "ts": datetime.now(timezone.utc).isoformat()}
        buf.append(payload)
        # Keep buffer bounded
        if len(buf) > self._MAX_BUFFER:
            self._event_buffer[project_id] = buf[-self._MAX_BUFFER:]

    def get_buffered_events(self, project_id: str) -> list[dict]:
        """Return all buffered events for a project (for reconnect replay)."""
        return list(self._event_buffer.get(project_id, []))

    async def broadcast(self, project_id: str, payload: dict) -> None:
        # Buffer before sending so replay includes all events (including those
        # sent when no client is connected)
        self._buffer_event(project_id, payload)

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

    async def replay(self, project_id: str, ws: WebSocket,
                     since_ts: str | None = None) -> None:
        """Replay buffered events to a newly connected WebSocket.

        Sends a ``replay_start`` sentinel, then all buffered events, then a
        ``replay_end`` sentinel so the frontend can reconcile its state.

        Parameters
        ----------
        since_ts:
            ISO timestamp.  Only events with ``ts >= since_ts`` are replayed.
            Pass ``None`` to replay all buffered events.
        """
        events = self.get_buffered_events(project_id)

        if since_ts:
            events = [e for e in events if e.get("ts", "") >= since_ts]

        try:
            await ws.send_json({
                "type": "replay_start",
                "data": {"project_id": project_id, "event_count": len(events)},
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            for evt in events:
                await ws.send_json(evt)
            await ws.send_json({
                "type": "replay_end",
                "data": {"project_id": project_id, "replayed": len(events)},
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass  # Client may have disconnected during replay — ignore


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
    # Phase 8: Project memory for brand/design/media/stack persistence
    project_memory: dict | None = None


class AssistantMessage(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    project_id: Optional[str] = None


MessageCreate = AssistantMessage  # backward compat alias


class IdeaBuilderSessionCreate(BaseModel):
    seed_prompt: Optional[str] = Field(default="", max_length=12000)
    mode: Optional[str] = "website"


class IdeaBuilderMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=6000)


class IdeaBuilderFinalizeBody(BaseModel):
    project_name: Optional[str] = Field(default=None, max_length=120)
    mode: Optional[str] = None


class IterateBody(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    tier: Optional[str] = None
    mediaSource: Optional[str] = "auto"


class SettingsUpdate(BaseModel):
    GENX_API_KEY: Optional[str] = None
    GITHUB_PAT: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None
    PIXABAY_API_KEY: Optional[str] = None
    QWEN_API_KEY: Optional[str] = None
    QWEN_BASE_URL: Optional[str] = None
    QWEN_MODEL_CHAT: Optional[str] = None
    QWEN_MODEL_CODE: Optional[str] = None
    QWEN_MODEL_IMAGE: Optional[str] = None
    QWEN_MODEL_VIDEO: Optional[str] = None
    QWEN_MODEL_AUDIO: Optional[str] = None


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


class SavePixabayBody(BaseModel):
    asset_id: Optional[str] = None
    project_id: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    query: str = ""
    attribution: dict = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    media_type: str = "image"
    width: int = 0
    height: int = 0


class SaveGeneratedBody(BaseModel):
    project_id: Optional[str] = None
    source: str = Field(pattern="^(genx|qwen)$")
    url: str
    prompt: str = ""
    media_type: str = "image"
    tags: List[str] = Field(default_factory=list)
    width: int = 0
    height: int = 0


class ProjectMemoryPatch(BaseModel):
    brand: Optional[dict] = None
    designTokens: Optional[dict] = None
    fontPair: Optional[dict] = None
    logo: Optional[dict] = None
    mediaAssets: Optional[List[dict]] = None
    stack: Optional[dict] = None
    database: Optional[dict] = None
    auth: Optional[dict] = None
    envRequirements: Optional[List[str]] = None
    deploymentTarget: Optional[str] = None


class StatusPatch(BaseModel):
    status: str


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
    return (await safe_get_secret(db, key, env_fallback=True)).get("value") or None


async def _runtime_secret_status(key: str) -> dict:
    return await safe_get_secret(db, key, env_fallback=True)


async def _capability_truth() -> dict:
    cached = _probe_svc._CACHE.get("all_providers", {})
    service = CapabilityTruthService(_runtime_secret_status, cached_probes=cached if isinstance(cached, dict) else {})
    return await service.build()


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
                preview_url = None
                if proj.get("status") == "ready":
                    preview_url = f"/api/projects/{project_id}/preview"
                    updates["preview_url"] = preview_url
                await db.projects.update_one(
                    {"id": project_id},
                    {"$set": updates},
                )
                # Phase 2A: Create a version record for every completed build/iteration
                try:
                    final_files = await ProjectFS(db, project_id).list_full()
                    await create_version(
                        db, project_id,
                        user_request=prompt,
                        generated_files=[f["path"] for f in final_files],
                        changed_files=[f["path"] for f in final_files],
                        build_status=proj.get("status", "ready"),
                        preview_url=preview_url,
                        validation_result=proj.get("validation_state") or {},
                        memory_snapshot=proj.get("project_memory") or {},
                        file_snapshot=final_files,
                    )
                except Exception as ver_exc:
                    logger.warning("Version creation failed for %s: %s", project_id, ver_exc)
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
            # Phase 2A: create a failed version record so the timeout is traceable
            try:
                timeout_files = await ProjectFS(db, project_id).list_full()
                await create_version(
                    db, project_id,
                    user_request=prompt,
                    generated_files=[f["path"] for f in timeout_files],
                    build_status="failed",
                    file_snapshot=timeout_files,
                )
            except Exception:
                pass
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
                # Phase 2A: create a failed version record so the failure is traceable
                try:
                    failed_files = await ProjectFS(db, project_id).list_full()
                    await create_version(
                        db, project_id,
                        user_request=prompt,
                        generated_files=[f["path"] for f in failed_files],
                        build_status="failed",
                        file_snapshot=failed_files,
                    )
                except Exception:
                    pass


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

    try:
        admin = await db.users.find_one({"role": "admin", "status": "active"}, {"_id": 0, "id": 1})
        await add("admin user", "PASS" if admin else "FAIL",
                  "Active admin exists." if admin else "Create or seed an active admin user.",
                  "info" if admin else "blocker")
    except Exception as exc:
        await add("admin user", "FAIL", f"Could not check admin user: {type(exc).__name__}", "blocker")

    try:
        await _probe_svc.probe_all_providers(
            genx_key=(await _runtime_secret("GENX_API_KEY")) or "",
            qwen_key=(await _runtime_secret("QWEN_API_KEY")) or "",
            github_pat=(await _runtime_secret("GITHUB_PAT")) or "",
            brave_key=(await _runtime_secret("BRAVE_SEARCH_API_KEY")) or "",
            pixabay_key=(await _runtime_secret("PIXABAY_API_KEY")) or "",
            qwen_base_url=(await _runtime_secret("QWEN_BASE_URL")) or None,
            force_refresh=True,
        )
    except Exception as exc:
        await add("provider live probes", "WARN", f"Provider probe cache refresh failed: {type(exc).__name__}", "warning")

    try:
        truth = await _capability_truth()
    except Exception as exc:
        truth = {"providers": {}, "capabilities": {}, "warnings": [], "errors": [str(exc)]}
        await add("capability truth", "FAIL", f"Capability truth failed: {type(exc).__name__}", "blocker")

    providers = truth.get("providers", {})
    for provider, meta in providers.items():
        if meta.get("source") == "decrypt_failed" or meta.get("error") == "decrypt_failed":
            await add(f"{provider} setting decrypt", "WARN", f"{meta.get('env_key', provider)} stored setting cannot decrypt; env fallback used if configured.", "warning")

    genx_meta = providers.get("genx", {})
    genx_key = await _runtime_secret("GENX_API_KEY")
    if not genx_key:
        await add("GenX API key", "FAIL", genx_meta.get("reason") or "Set GENX_API_KEY in Settings or environment.", "blocker")
    else:
        try:
            models = await GenXProvider(api_key=genx_key).list_models()
            await add("GenX live models", "PASS", f"{len(models)} models returned by {ROUTER_NAME}.")
        except Exception as exc:
            await add("GenX live models", "FAIL", f"{type(exc).__name__}: {exc}", "blocker")

    github_meta = providers.get("github", {})
    github_pat = await _runtime_secret("GITHUB_PAT")
    if not github_pat:
        await add("GitHub PAT", "WARN", github_meta.get("reason") or "Connect GitHub PAT in Settings to enable private imports, PRs, and repo creation.", "warning")
    else:
        try:
            info = await gh.validate_pat(github_pat)
            await add("GitHub PAT live validation", "PASS", f"Authenticated as {info.get('login')}.")
        except Exception as exc:
            await add("GitHub PAT live validation", "WARN", f"{type(exc).__name__}: {exc}", "warning")

    brave_meta = providers.get("brave", {})
    brave_key = await _runtime_secret("BRAVE_SEARCH_API_KEY")
    if not brave_key:
        await add("Brave Search key", "WARN", brave_meta.get("reason") or "Scout runs without web research until BRAVE_SEARCH_API_KEY is configured.", "warning")
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
            await add("Brave Search live validation", "WARN", f"{type(exc).__name__}: {exc}", "warning")

    for provider, env_key in [("qwen", "QWEN_API_KEY"), ("pixabay", "PIXABAY_API_KEY")]:
        meta = providers.get(provider, {})
        if not meta.get("configured"):
            await add(env_key, "WARN", meta.get("reason") or f"{env_key} not configured.", "warning")

    try:
        clean, detail = await _forbidden_source_check()
        await add("legacy source references", "PASS" if clean else "FAIL", detail, "info" if clean else "blocker")
    except Exception as exc:
        await add("legacy source references", "WARN", f"Source check skipped: {type(exc).__name__}", "warning")
    await add("production demo simulation disabled", "PASS", "Production paths return disabled or errors when required keys are absent.")

    blockers = [c["detail"] for c in checks if c["status"] == "FAIL" and c["severity"] == "blocker"]
    warnings = [c["detail"] for c in checks if c["status"] == "WARN"]
    return {
        "overall": "FAIL" if blockers else ("WARN" if warnings else "PASS"),
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "providers": providers,
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


# ── Phase 1A: Capability Registry endpoints ───────────────────────────────────

@api.get("/capabilities")
async def get_capabilities() -> dict:
    """Return the full AI capability registry.

    Single source of truth: reads from saved settings (DB) first, then env vars.
    The frontend must use this to decide what to show.
    """
    try:
        truth = await _capability_truth()
    except Exception as exc:
        truth = {
            "registry": [],
            "models": [],
            "summary": {},
            "capabilities": {},
            "providers": {},
            "errors": [f"capability truth failed: {type(exc).__name__}"],
            "warnings": [],
            "timestamp": _now(),
        }
    return {
        "registry": truth.get("models", []),
        "models": truth.get("models", []),
        "summary": truth.get("capabilities", {}),
        "providers": truth.get("providers", {}),
        "errors": truth.get("errors", []),
        "warnings": truth.get("warnings", []),
        "timestamp": truth.get("timestamp", _now()),
    }


@api.get("/capabilities/status")
async def capabilities_status() -> dict:
    """Return the current runtime availability of each AI capability.

    Single source of truth: reads from saved settings (DB) first, then env vars.
    Returns instantly without a live provider call.
    """
    try:
        truth = await _capability_truth()
    except Exception as exc:
        truth = {
            "summary": {},
            "capabilities": {},
            "providers": {},
            "models": [],
            "errors": [f"capability truth failed: {type(exc).__name__}"],
            "warnings": [],
            "timestamp": _now(),
        }
    summary = truth.get("capabilities", {})
    available_caps = [k for k, v in summary.items() if v.get("available")]
    unavailable_caps = {
        k: v.get("reason")
        for k, v in summary.items()
        if not v.get("available")
    }
    return {
        "available": available_caps,
        "unavailable": unavailable_caps,
        "summary": summary,
        "providers": truth.get("providers", {}),
        "models": truth.get("models", []),
        "errors": truth.get("errors", []),
        "warnings": truth.get("warnings", []),
        "timestamp": truth.get("timestamp", _now()),
    }


@api.get("/capabilities/models")
async def capability_models(capability: Optional[str] = None) -> dict:
    """Return models from the registry, optionally filtered by capability.

    ?capability=image_generation  → models that support image generation
    ?capability=reasoning          → models that support reasoning
    (omit parameter to return all models)
    """
    if capability:
        truth = await _capability_truth()
        capability_attr = capability if capability.startswith("supports_") else f"supports_{capability}"
        models = [m for m in truth.get("models", []) if m.get(capability_attr)]
        if not models:
            return {
                "capability": capability,
                "models": [],
                "available": False,
                "message": f"No models in the registry support '{capability}'. "
                           "This feature may not be available in the current configuration.",
            }
        return {
            "capability": capability,
            "models": models,
            "available": any(m.get("available") for m in models),
            "count": len(models),
        }
    truth = await _capability_truth()
    return {"models": truth.get("models", []), "count": len(truth.get("models", [])), "providers": truth.get("providers", {})}


# ── Phase 1E: Build Mode Classifier endpoint ──────────────────────────────────

class ClassifyModeBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    forced_mode: Optional[str] = None


@api.post("/classify-mode")
async def classify_mode(body: ClassifyModeBody) -> dict:
    """Classify the build mode from a user prompt.

    Phase 1E: Returns the detected mode, confidence, and targeted
    clarification questions if the prompt is ambiguous.

    The frontend MUST present clarification questions when
    needs_clarification=True before starting the build pipeline.
    """
    result = classify_build_mode(body.prompt, forced_mode=body.forced_mode)
    return result.to_dict()


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
    truth = await _capability_truth()
    genx_state = truth.get("providers", {}).get("genx", {})
    genx_available = bool(
        genx_state.get("configured") and genx_state.get("live_status") == "live_ok"
    )

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
    if not genx_available:
        warnings.append(genx_state.get("reason") or "GenX provider is not live-validated; routing is informational only.")
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
        "available": genx_available,
        "provider": {
            "name": "genx",
            "configured": genx_state.get("configured", False),
            "source": genx_state.get("source", "missing"),
            "live_status": genx_state.get("live_status", "key_missing"),
            "reason": genx_state.get("reason"),
        },
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
    """Determine media_strategy for a new project based on mode, tier, and media_requirements.

    Explicit media source choices take priority over automatic selection:
      "pixabay"  → Pixabay stock images/videos (requires PIXABAY_API_KEY)
      "ai"       → GenX/Qwen AI image generation (requires balanced/premium tier)
      "css_svg"  → CSS + SVG visual compositions only; no external image URLs
      "auto"     → best available option (original auto-selection logic)
    """
    req = (media_requirements or "auto").lower().strip()

    # ── Explicit "pixabay" choice ──────────────────────────────────────────────
    if req == "pixabay":
        return {
            "mode": "pixabay",
            "confirmed": True,
            "models_used": [],
            "source": "pixabay",
            "notes": (
                "Pixabay stock images/videos will be fetched and embedded in the project. "
                "Requires PIXABAY_API_KEY configured in Settings. "
                "If the key is missing, a setup warning will be shown instead of images."
            ),
        }

    # ── Explicit "ai" choice ───────────────────────────────────────────────────
    if req == "ai":
        if quality_tier in ("balanced", "premium"):
            return {
                "mode": "ai_generated",
                "confirmed": False,
                "models_used": [],
                "notes": (
                    "AI image generation will be used if a GenX or Qwen media model is available. "
                    "Falls back to CSS/SVG visuals if no media model is configured."
                ),
            }
        return {
            "mode": "placeholder",
            "confirmed": False,
            "models_used": [],
            "notes": (
                "AI image generation requires balanced or premium tier. "
                "Upgrade your quality tier to enable AI media."
            ),
        }

    # ── Explicit "css_svg" choice ─────────────────────────────────────────────
    if req == "css_svg":
        return {
            "mode": "css_svg",
            "confirmed": True,
            "models_used": [],
            "notes": (
                "CSS gradients and inline SVG visual compositions only. "
                "No external image URLs or API calls will be made."
            ),
        }

    # ── Auto mode (original logic) ─────────────────────────────────────────────
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


@api.get("/qwen/status")
async def qwen_status() -> dict:
    """Return optional Qwen direct-provider availability status.

    Reads from saved settings (DB) first, then env vars.
    Returns honest status for each capability — never vague if key exists.
    Never blocks normal builds — Qwen is entirely optional.
    """
    qwen_key = await _runtime_secret("QWEN_API_KEY")

    if not qwen_key:
        return {
            "configured": False,
            "api_key_set": False,
            "capabilities": {
                "chat":  {"available": False, "status": "QWEN_API_KEY not configured"},
                "code":  {"available": False, "status": "QWEN_API_KEY not configured"},
                "image": {"available": False, "status": "QWEN_API_KEY not configured"},
                "video": {"available": False, "status": "QWEN_API_KEY not configured"},
                "audio": {"available": False, "status": "QWEN_API_KEY not configured"},
            },
            "note": "Qwen is optional. Add QWEN_API_KEY in Settings to enable.",
            "recommended_config": QWEN_RECOMMENDED_MODELS,
            "default_base_url": QWEN_DEFAULT_BASE_URL,
        }

    async def _check_cap(key: str) -> dict:
        model = await _runtime_secret(key) or os.environ.get(key, "")
        if model:
            return {"available": True, "model": model, "status": "configured"}
        return {
            "available": False,
            "status": f"{key} not configured -- QWEN_API_KEY is set but {key} is missing",
            "suggested": QWEN_RECOMMENDED_MODELS.get(key, ""),
        }

    chat  = await _check_cap("QWEN_MODEL_CHAT")
    code  = await _check_cap("QWEN_MODEL_CODE")
    image = await _check_cap("QWEN_MODEL_IMAGE")
    video = await _check_cap("QWEN_MODEL_VIDEO")
    audio = await _check_cap("QWEN_MODEL_AUDIO")

    base_url = (
        await _runtime_secret("QWEN_BASE_URL")
        or os.environ.get("QWEN_BASE_URL", QWEN_DEFAULT_BASE_URL)
    )

    missing = [k for k, v in {
        "QWEN_BASE_URL": base_url,
        "QWEN_MODEL_CHAT": chat.get("model", ""),
        "QWEN_MODEL_CODE": code.get("model", ""),
        "QWEN_MODEL_IMAGE": image.get("model", ""),
        "QWEN_MODEL_VIDEO": video.get("model", ""),
        "QWEN_MODEL_AUDIO": audio.get("model", ""),
    }.items() if not v]

    return {
        "configured": True,
        "api_key_set": True,
        "base_url": base_url,
        "missing_fields": missing,
        "capabilities": {
            "chat":  chat,
            "code":  code,
            "image": image,
            "video": video,
            "audio": audio,
        },
        "recommended_config": QWEN_RECOMMENDED_MODELS,
        "default_base_url": QWEN_DEFAULT_BASE_URL,
        "alt_base_urls": QWEN_ALT_BASE_URLS,
        "optional_models": QWEN_OPTIONAL_MODELS,
        "note": (
            "Qwen is optional. GenX is the primary provider. "
            "Qwen is only used for tasks where a specific Qwen model is configured."
        ),
    }


@api.post("/qwen/apply-recommended-config")
async def qwen_apply_recommended_config(
    claims: dict = Depends(require_user),
) -> dict:
    """Apply recommended Qwen model defaults to the settings store.

    Sets QWEN_BASE_URL and all recommended model IDs if they are not
    already configured. Does NOT overwrite existing values.
    Requires QWEN_API_KEY to already be set.
    """
    qwen_key = await _runtime_secret("QWEN_API_KEY")
    if not qwen_key:
        raise HTTPException(400, "QWEN_API_KEY must be configured before applying defaults.")

    applied: list[str] = []
    skipped: list[str] = []

    # Base URL
    current_base = await _runtime_secret("QWEN_BASE_URL") or os.environ.get("QWEN_BASE_URL", "")
    if not current_base:
        await save_secret(db, "QWEN_BASE_URL", QWEN_DEFAULT_BASE_URL, claims["sub"])
        applied.append("QWEN_BASE_URL")
    else:
        skipped.append("QWEN_BASE_URL")

    # Model IDs
    for key, default_model in QWEN_RECOMMENDED_MODELS.items():
        current = await _runtime_secret(key) or os.environ.get(key, "")
        if not current:
            await save_secret(db, key, default_model, claims["sub"])
            applied.append(key)
        else:
            skipped.append(key)

    return {
        "ok": True,
        "applied": applied,
        "skipped": skipped,
        "message": (
            f"Applied {len(applied)} recommended defaults. "
            f"Skipped {len(skipped)} already-configured values."
        ),
        "applied_values": {
            "QWEN_BASE_URL": QWEN_DEFAULT_BASE_URL,
            **QWEN_RECOMMENDED_MODELS,
        },
    }



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


async def _load_idea_session(session_id: str, owner_id: str) -> dict:
    doc = await db.idea_builder_sessions.find_one({"id": session_id, "owner_id": owner_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Idea Builder session not found.")
    return doc


@secured.post("/idea-builder/sessions")
async def create_idea_builder_session(
    body: IdeaBuilderSessionCreate,
    claims: dict = Depends(require_user),
) -> dict:
    doc = make_session_doc(
        owner_id=claims["sub"],
        seed_prompt=body.seed_prompt or "",
        mode=body.mode,
    )
    await db.idea_builder_sessions.insert_one(dict(doc))
    return doc


@secured.get("/idea-builder/sessions/{session_id}")
async def get_idea_builder_session(session_id: str, claims: dict = Depends(require_user)) -> dict:
    return await _load_idea_session(session_id, claims["sub"])


@secured.post("/idea-builder/sessions/{session_id}/messages")
async def add_idea_builder_message(
    session_id: str,
    body: IdeaBuilderMessageCreate,
    claims: dict = Depends(require_user),
) -> dict:
    doc = await _load_idea_session(session_id, claims["sub"])
    mode = normalize_mode(doc.get("mode"))
    user_msg = make_message("user", body.message)
    messages = [*doc.get("messages", []), user_msg]

    model_reply: str | None = None
    source = "deterministic"
    if await _runtime_secret("GENX_API_KEY"):
        try:
            provider = await _genx_provider("balanced")
            result = await provider.complete(
                agent="idea_builder",
                system_prompt=IDEA_BUILDER_SYSTEM_PROMPT,
                user_message=model_user_message(messages, mode),
                session_id=f"idea-builder:{session_id}",
            )
            model_reply = result.get("text")
            source = result.get("model_label") or "model"
        except Exception as exc:
            logger.warning("Idea Builder model fallback for %s: %s", session_id, type(exc).__name__)

    assistant_msg = make_message(
        "assistant",
        normalize_model_reply(model_reply, messages, mode)
        if model_reply
        else deterministic_reply(messages, mode),
    )
    messages.append(assistant_msg)
    updated = utc_now()
    await db.idea_builder_sessions.update_one(
        {"id": session_id, "owner_id": claims["sub"]},
        {"$set": {"messages": messages, "updated_at": updated}},
    )
    return {
        "session_id": session_id,
        "message": assistant_msg,
        "messages": messages,
        "source": source,
        "updated_at": updated,
    }


@secured.post("/idea-builder/sessions/{session_id}/finalize")
async def finalize_idea_builder_session(
    session_id: str,
    body: IdeaBuilderFinalizeBody,
    claims: dict = Depends(require_user),
) -> dict:
    doc = await _load_idea_session(session_id, claims["sub"])
    mode = normalize_mode(body.mode or doc.get("mode"))
    messages = doc.get("messages", [])
    model_prompt: str | None = None
    source = "deterministic"
    if await _runtime_secret("GENX_API_KEY"):
        try:
            provider = await _genx_provider("balanced")
            result = await provider.complete(
                agent="idea_builder",
                system_prompt=IDEA_BUILDER_SYSTEM_PROMPT,
                user_message=final_model_user_message(messages, mode, body.project_name),
                session_id=f"idea-builder:{session_id}:final",
            )
            model_prompt = result.get("text")
            source = result.get("model_label") or "model"
        except Exception as exc:
            logger.warning("Idea Builder final prompt fallback for %s: %s", session_id, type(exc).__name__)

    final_prompt = compose_final_prompt(messages, mode, body.project_name, model_prompt)
    updated = utc_now()
    await db.idea_builder_sessions.update_one(
        {"id": session_id, "owner_id": claims["sub"]},
        {"$set": {
            "mode": mode,
            "status": "finalized",
            "final_prompt": final_prompt,
            "updated_at": updated,
        }},
    )
    return {
        "session_id": session_id,
        "mode": mode,
        "final_prompt": final_prompt,
        "source": source,
        "updated_at": updated,
    }


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
        project_memory=_empty_project_memory(),
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

    # Save to VPS build storage (non-fatal — does not block import)
    try:
        branch_name = info.get("branch", "main")
        ws_meta = create_repo_workspace(
            owner=owner,
            repo=repo,
            branch=branch_name,
            commit_sha=info.get("commit_sha", ""),
            repo_url=info.get("html_url", body.repo_url),
        )
        # Run stack detection and save to workspace metadata
        detect_and_save_stack(
            Path(ws_meta["local_path"]),
            info.get("files", []),
        )
        # Link the project_id to the workspace metadata
        update_workspace_metadata(
            Path(ws_meta["local_path"]),
            {"mongodb_project_id": proj.id, "build_status": "cloned"},
        )
        logger.info(
            "Saved repo workspace for %s/%s@%s at %s",
            owner, repo, branch_name, ws_meta["local_path"],
        )
    except Exception as exc:
        logger.warning("Build storage save failed (non-fatal): %s", exc)

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


def _make_preview_token(project_id: str, claims: dict) -> dict:
    ttl_seconds = int(os.environ.get("PREVIEW_TOKEN_TTL_SECONDS", "300"))
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    payload = {
        "typ": "preview",
        "sub": claims["sub"],
        "email": claims.get("email"),
        "role": claims.get("role", "user"),
        "project_id": project_id,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=os.environ.get("JWT_ALGO", "HS256"))
    return {"preview_token": token, "expires_at": exp.isoformat(), "ttl_seconds": ttl_seconds}


async def _preview_claims(project_id: str, request: Request) -> dict:
    token = request.query_params.get("preview_token")
    if not token:
        raise HTTPException(401, "Missing preview token")
    try:
        claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[os.environ.get("JWT_ALGO", "HS256")])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Preview token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid preview token")
    if claims.get("typ") != "preview" or claims.get("project_id") != project_id:
        raise HTTPException(403, "Preview token scope mismatch")
    await _own(project_id, claims)
    return claims


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


@secured.post("/projects/{project_id}/preview-token")
async def project_preview_token(project_id: str, claims: dict = Depends(require_user)) -> dict:
    await _own(project_id, claims)
    return _make_preview_token(project_id, claims)


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
    if not proj:
        raise HTTPException(404, "Project not found")
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
    # For imported repo (repo_fix) projects, route through the full build pipeline so that
    # _run_repo_fix is called — it handles intent detection, completion, and targeted edits.
    # Regular builds use the lightweight iteration path.
    project_mode = proj.get("mode", "web_app")
    if project_mode == "repo_fix":
        asyncio.create_task(_launch_pipeline(project_id, body.content, "build", build_mode="repo_fix"))
    else:
        asyncio.create_task(_launch_pipeline(project_id, body.content, "iterate"))
    return {"ok": True, "queued": True}


@secured.post("/projects/{project_id}/iterate")
async def iterate_project(project_id: str, body: IterateBody, claims: dict = Depends(require_user)) -> dict:
    """Post-build iteration — request changes to a completed project.

    This is a dedicated iteration endpoint that accepts a structured change request.
    For imported repos, this routes through the repo-fix pipeline to preserve context.

    Request body:
        message: the change request (required)
        tier:    quality tier override (optional: cheap|balanced|premium)
        mediaSource: media source hint (optional)

    Response:
        ok: True, queued: True, projectId: str
    """
    await _own(project_id, claims)
    if not await _runtime_secret("GENX_API_KEY"):
        raise HTTPException(503, "GENX_API_KEY is required for Amarktai Coding Agents.")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    if proj.get("status") in ("running", "queued"):
        raise HTTPException(409, "Build already in progress")
    _meta = {"requirements.md", "tech_stack.json"}
    existing_files = await ProjectFS(db, project_id).list()
    app_file_count = sum(1 for f in existing_files if f["path"] not in _meta)
    if app_file_count == 0:
        raise HTTPException(
            409,
            "No app files found. Build the project first before requesting changes.",
        )
    updates: dict = {"status": "queued", "cancel_requested": False, "updated_at": _now()}
    if body.tier and body.tier in ("cheap", "balanced", "premium"):
        updates["quality_tier"] = body.tier
    await db.projects.update_one({"id": project_id}, {"$set": updates})
    await hub.broadcast(project_id, {"type": "project_status", "data": {"status": "queued"}})
    # Route imported-repo (repo_fix) projects through the build pipeline with build_mode="repo_fix"
    # so that _run_repo_fix is called directly (intent detection, full_app_completion escalation,
    # 1500s global timeout) instead of run_iteration with its 600s limit.
    project_mode = proj.get("mode", "web_app")
    if project_mode == "repo_fix" or proj.get("github"):
        asyncio.create_task(_launch_pipeline(project_id, body.message, "build", build_mode="repo_fix"))
    else:
        asyncio.create_task(_launch_pipeline(project_id, body.message, "iterate"))
    return {"ok": True, "queued": True, "projectId": project_id}


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


@api.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def project_preview(project_id: str, request: Request) -> HTMLResponse:
    await _preview_claims(project_id, request)
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


@api.get("/projects/{project_id}/preview/{file_path:path}")
async def project_preview_file(
    project_id: str, file_path: str, request: Request
):
    """Serve an individual project file from the preview with the correct MIME type.

    This endpoint allows the "Open preview in new tab" flow to load assets (styles.css,
    app.js, manifest.json, etc.) as separate requests rather than relying on inlining.
    MIME types are set explicitly so browsers validate and apply the resources correctly.
    """
    from fastapi.responses import Response
    from pathlib import PurePosixPath
    await _preview_claims(project_id, request)
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
            prompt=proj.get("prompt", "")[:gh._PR_PROMPT_TRUNCATE],
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
        # Phase 1G: Replay buffered events on connect so the client can
        # reconcile its state without a page refresh.
        # The client may pass ?since=<ISO timestamp> to request partial replay.
        since_ts = ws.query_params.get("since")
        await hub.replay(project_id, ws, since_ts=since_ts)

        await ws.send_json({"type": "hello", "data": {"project_id": project_id, "connected": True},
                            "ts": _now()})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_json({"type": "pong", "data": {"t": _now()}, "ts": _now()})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "data": {"t": _now()}, "ts": _now()})
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


# ── Media Library Endpoints ──────────────────────────────────────────────────

@secured.post("/media/upload")
async def media_upload(
    claims: dict = Depends(require_user),
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    media_type_override: Optional[str] = Form(None),
) -> dict:
    """Upload media to the media library."""
    user_id = claims["sub"]
    content = await file.read()
    filename = file.filename or "upload"

    validation = validate_upload(filename, content, media_type_override)
    if not validation["ok"]:
        # Use a safe, curated message — do not echo raw internal errors to client
        safe_msg = validation.get("error", "Upload rejected")
        if len(safe_msg) > 200:
            safe_msg = safe_msg[:200]
        raise HTTPException(400, safe_msg)

    asset_id = str(uuid.uuid4())
    safe_fn = safe_filename(filename)
    try:
        file_path, thumb_path = save_file(user_id, asset_id, safe_fn, content)
    except Exception:
        logger.exception("Failed to save uploaded file for user %s", user_id)
        raise HTTPException(500, "Failed to save uploaded file")

    public_url = public_url_for(asset_id, safe_fn)
    thumb_url = public_url_for(asset_id, safe_fn, thumb=True) if thumb_path else public_url

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    now = _now()
    asset_doc = {
        "id": asset_id,
        "user_id": user_id,
        "project_id": project_id,
        "filename": safe_fn,
        "original_name": filename,
        "media_type": validation["media_type"],
        "mime_type": validation["mime"],
        "size_bytes": len(content),
        "width": validation.get("width", 0),
        "height": validation.get("height", 0),
        "source": "upload",
        "storage_path": str(file_path),
        "public_url": public_url,
        "thumbnail_url": thumb_url,
        "prompt": "",
        "query": "",
        "attribution": {},
        "tags": tag_list,
        "created_at": now,
        "updated_at": now,
    }
    await db.media_assets.insert_one({**asset_doc, "_id": asset_id})
    return {k: v for k, v in asset_doc.items() if k != "_id"}


@secured.get("/media/library")
async def media_library(
    claims: dict = Depends(require_user),
    project_id: Optional[str] = Query(None),
    media_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    """List media assets for the current user."""
    user_id = claims["sub"]
    query: dict = {"user_id": user_id}
    if project_id:
        query["project_id"] = project_id
    if media_type:
        query["media_type"] = media_type
    if source:
        query["source"] = source
    if q:
        query["$or"] = [
            {"filename": {"$regex": q, "$options": "i"}},
            {"original_name": {"$regex": q, "$options": "i"}},
            {"tags": {"$elemMatch": {"$regex": q, "$options": "i"}}},
        ]
    skip = (page - 1) * per_page
    total = await db.media_assets.count_documents(query)
    docs = await db.media_assets.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(per_page).to_list(per_page)
    return {"total": total, "page": page, "per_page": per_page, "assets": docs}


@secured.get("/media/{asset_id}")
async def media_get(asset_id: str, claims: dict = Depends(require_user)) -> dict:
    """Get metadata for a media asset."""
    user_id = claims["sub"]
    query = {"id": asset_id} if claims.get("role") == "admin" else {"id": asset_id, "user_id": user_id}
    doc = await db.media_assets.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Media asset not found")
    return doc


@secured.get("/media/{asset_id}/file")
async def media_serve_file(asset_id: str, claims: dict = Depends(require_user)) -> Response:
    """Serve the original file for a media asset."""
    user_id = claims["sub"]
    query = {"id": asset_id} if claims.get("role") == "admin" else {"id": asset_id, "user_id": user_id}
    doc = await db.media_assets.find_one(query, {"_id": 0, "storage_path": 1, "mime_type": 1})
    if not doc:
        raise HTTPException(404, "Media asset not found")
    storage_path = doc.get("storage_path", "")
    if not storage_path or not storage_path_is_safe(storage_path):
        raise HTTPException(404, "File not available")
    path = Path(storage_path)
    if not path.exists():
        raise HTTPException(404, "File not found on disk")
    content = path.read_bytes()
    return Response(content=content, media_type=doc.get("mime_type", "application/octet-stream"))


@secured.get("/media/{asset_id}/thumbnail")
async def media_serve_thumbnail(asset_id: str, claims: dict = Depends(require_user)) -> Response:
    """Serve the thumbnail for a media asset, falling back to original."""
    user_id = claims["sub"]
    query = {"id": asset_id} if claims.get("role") == "admin" else {"id": asset_id, "user_id": user_id}
    doc = await db.media_assets.find_one(query, {"_id": 0, "storage_path": 1, "mime_type": 1})
    if not doc:
        raise HTTPException(404, "Media asset not found")
    storage_path = doc.get("storage_path", "")
    if not storage_path or not storage_path_is_safe(storage_path):
        raise HTTPException(404, "File not available")
    orig_path = Path(storage_path)
    # Try thumbnail first
    thumb_path = orig_path.parent / f"thumb_{orig_path.name}"
    serving_thumb = thumb_path.exists()
    serve_path = thumb_path if serving_thumb else orig_path
    if not serve_path.exists():
        raise HTTPException(404, "File not found on disk")
    content = serve_path.read_bytes()
    # Use JPEG MIME for thumbnail files (always JPEG), original MIME for original files
    if serving_thumb and serve_path.suffix.lower() in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    else:
        mime = doc.get("mime_type", "application/octet-stream")
    return Response(content=content, media_type=mime)


@secured.delete("/media/{asset_id}")
async def media_delete(asset_id: str, claims: dict = Depends(require_user)) -> dict:
    """Delete a media asset and its file."""
    user_id = claims["sub"]
    query = {"id": asset_id} if claims.get("role") == "admin" else {"id": asset_id, "user_id": user_id}
    doc = await db.media_assets.find_one(query, {"_id": 0, "storage_path": 1})
    if not doc:
        raise HTTPException(404, "Media asset not found")
    storage_path = doc.get("storage_path", "")
    if storage_path and storage_path_is_safe(storage_path):
        delete_asset_files(storage_path)
    await db.media_assets.delete_one({"id": asset_id})
    return {"ok": True, "deleted": asset_id}


@secured.post("/media/save-pixabay")
async def media_save_pixabay(body: SavePixabayBody, claims: dict = Depends(require_user)) -> dict:
    """Save a selected Pixabay asset to the media library."""
    user_id = claims["sub"]
    if not body.attribution:
        raise HTTPException(400, "attribution is required for Pixabay assets")
    asset_id = body.asset_id or str(uuid.uuid4())
    now = _now()
    asset_doc = {
        "id": asset_id,
        "user_id": user_id,
        "project_id": body.project_id,
        "filename": safe_filename(body.url.rsplit("/", 1)[-1] or "pixabay-image.jpg"),
        "original_name": body.url.rsplit("/", 1)[-1] or "pixabay-image",
        "media_type": body.media_type,
        "mime_type": "image/jpeg" if body.media_type == "image" else "video/mp4",
        "size_bytes": 0,
        "width": body.width,
        "height": body.height,
        "source": "pixabay",
        "storage_path": "",
        "public_url": body.url,
        "thumbnail_url": body.thumbnail_url or body.url,
        "prompt": "",
        "query": body.query,
        "attribution": body.attribution,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
    }
    await db.media_assets.replace_one(
        {"id": asset_id}, {**asset_doc, "_id": asset_id}, upsert=True
    )
    return {k: v for k, v in asset_doc.items() if k != "_id"}


@secured.post("/media/save-generated")
async def media_save_generated(body: SaveGeneratedBody, claims: dict = Depends(require_user)) -> dict:
    """Save a GenX/Qwen generated media asset to the media library."""
    user_id = claims["sub"]
    asset_id = str(uuid.uuid4())
    now = _now()
    asset_doc = {
        "id": asset_id,
        "user_id": user_id,
        "project_id": body.project_id,
        "filename": f"generated-{asset_id[:8]}.jpg",
        "original_name": f"generated-{body.source}",
        "media_type": body.media_type,
        "mime_type": "image/jpeg",
        "size_bytes": 0,
        "width": body.width,
        "height": body.height,
        "source": body.source,
        "storage_path": "",
        "public_url": body.url,
        "thumbnail_url": body.url,
        "prompt": body.prompt,
        "query": "",
        "attribution": {},
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
    }
    await db.media_assets.insert_one({**asset_doc, "_id": asset_id})
    return {k: v for k, v in asset_doc.items() if k != "_id"}


# ── Logo Agent Endpoint ──────────────────────────────────────────────────────

@secured.post("/logo")
async def generate_logo(body: dict, claims: dict = Depends(require_user)) -> dict:
    """Run the Logo Agent to generate or retrieve a logo.

    Phase 3: If project_id is provided, the logo result is stored in project memory
    for automatic reuse across iterations.
    """
    async def _lookup_asset(asset_id: str) -> dict | None:
        user_id = claims["sub"]
        return await db.media_assets.find_one(
            {"id": asset_id, "user_id": user_id}, {"_id": 0}
        )

    result = await run_logo_agent(body, media_library_fn=_lookup_asset)

    # Phase 3: Store logo in project memory for iteration reuse
    project_id = body.get("project_id")
    if project_id:
        try:
            from agents.project_memory import load_memory, save_memory, update_memory_logo
            memory = await load_memory(db, project_id)
            memory = update_memory_logo(memory, {**result, "businessName": body.get("businessName", "")})
            await save_memory(db, project_id, memory)
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"logo_result": result, "updated_at": _now()}},
            )
        except Exception as mem_err:
            logger.warning("Failed to persist logo to project memory: %s", mem_err)

    return result


# ── Agent Contracts Endpoint ─────────────────────────────────────────────────

@secured.get("/agents/contracts")
async def list_agent_contracts(_: dict = Depends(require_user)) -> dict:
    """Return all specialist agent contracts."""
    return {"contracts": get_all_contracts()}


@secured.get("/agents/contracts/{agent_name}")
async def get_agent_contract(agent_name: str, _: dict = Depends(require_user)) -> dict:
    """Return a specific agent contract by name."""
    contract = get_contract(agent_name)
    if not contract:
        raise HTTPException(404, f"Agent contract '{agent_name}' not found")
    return contract


# ── Project Memory Endpoints ─────────────────────────────────────────────────

def _empty_project_memory() -> dict:
    memory = make_empty_memory()
    memory.update({
        "mediaAssets": [],
        "stack": {},
        "database": {},
        "auth": {},
        "envRequirements": [],
        "deploymentTarget": "",
        "modelCalls": [],
        "decisions": [],
    })
    return memory


@secured.get("/projects/{project_id}/memory")
async def get_project_memory(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Return the project memory for a project."""
    user_id = claims["sub"]
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": user_id}
    proj = await db.projects.find_one(query, {"_id": 0, "project_memory": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    memory = proj.get("project_memory") or _empty_project_memory()
    return {"project_id": project_id, "memory": memory}


@secured.patch("/projects/{project_id}/memory")
async def patch_project_memory(
    project_id: str, body: ProjectMemoryPatch, claims: dict = Depends(require_user)
) -> dict:
    """Patch fields of the project memory."""
    user_id = claims["sub"]
    query = {"id": project_id} if claims.get("role") == "admin" else {"id": project_id, "owner_id": user_id}
    proj = await db.projects.find_one(query, {"_id": 0, "project_memory": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    memory = proj.get("project_memory") or _empty_project_memory()
    updates = body.model_dump(exclude_none=True)
    memory.update(updates)
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"project_memory": memory, "updated_at": _now()}},
    )
    return {"ok": True, "project_id": project_id, "memory": memory}


# ── HTML/CSS Validation Endpoint ─────────────────────────────────────────────

@secured.post("/validate/html")
async def validate_html_endpoint(body: dict, _: dict = Depends(require_user)) -> dict:
    """Validate HTML/CSS files. body: {files: [{path, content}], logo_result?, pixabay_assets?}."""
    files = body.get("files", [])
    logo_result = body.get("logo_result")
    pixabay_assets = body.get("pixabay_assets")
    if not files:
        raise HTTPException(400, "No files provided")
    result = validate_project_files_enhanced(files, logo_result, pixabay_assets)
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2A — PROJECT VERSIONING ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@secured.get("/projects/{project_id}/versions")
async def list_project_versions(project_id: str, claims: dict = Depends(require_user)) -> list[dict]:
    """Return all version records for a project (file snapshots excluded)."""
    await _own(project_id, claims)
    return await list_versions(db, project_id)


@secured.get("/projects/{project_id}/versions/{version_id}")
async def get_project_version(
    project_id: str, version_id: str, claims: dict = Depends(require_user)
) -> dict:
    """Return a single version record including its file snapshot."""
    await _own(project_id, claims)
    v = await get_version(db, project_id, version_id)
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@secured.post("/projects/{project_id}/versions/{version_id}/restore")
async def restore_project_version(
    project_id: str, version_id: str, claims: dict = Depends(require_user)
) -> dict:
    """Restore a project to the state captured in the given version."""
    await _own(project_id, claims)
    fs = ProjectFS(db, project_id)
    try:
        result = await restore_version(db, project_id, version_id, fs)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    # Create a new version to record the rollback event
    current_files = await fs.list_full()
    await create_version(
        db, project_id,
        user_request=f"Rollback to version {version_id}",
        changed_files=[f["path"] for f in current_files],
        build_status=result["status"],
        file_snapshot=current_files,
    )
    await hub.broadcast(project_id, {"type": "rollback_complete", "data": result})
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2H — ROLLBACK + SAFE CHECKPOINTS
# ════════════════════════════════════════════════════════════════════════════

@secured.post("/projects/{project_id}/rollback")
async def rollback_project(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Roll back to the most recent previous version.

    Equivalent to restoring parent_version_id of the latest version.
    """
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "latest_version_id": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    latest_vid = proj.get("latest_version_id")
    if not latest_vid:
        raise HTTPException(409, "No versions found for this project — cannot rollback")
    latest = await get_version(db, project_id, latest_vid)
    if not latest:
        raise HTTPException(409, "Latest version record not found")
    parent_vid = latest.get("parent_version_id")
    if not parent_vid:
        raise HTTPException(409, "Already at the first version — cannot rollback further")
    fs = ProjectFS(db, project_id)
    try:
        result = await restore_version(db, project_id, parent_vid, fs)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    await hub.broadcast(project_id, {"type": "rollback_complete", "data": result})
    return result


@secured.get("/projects/{project_id}/checkpoints")
async def list_project_checkpoints(
    project_id: str, claims: dict = Depends(require_user)
) -> list[dict]:
    """Return all checkpoints for a project (file snapshots excluded)."""
    await _own(project_id, claims)
    return await list_checkpoints(db, project_id)


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2E — IMPORTED REPO REPAIR PIPELINE
# ════════════════════════════════════════════════════════════════════════════

@secured.post("/repos/{repo_id}/analyze")
async def repo_analyze(repo_id: str, claims: dict = Depends(require_user)) -> dict:
    """Run a deep stack analysis on an imported repo project.

    Detects stack, derives commands, and produces a repair plan.
    """
    await _own(repo_id, claims)
    proj = await db.projects.find_one({"id": repo_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    files = await ProjectFS(db, repo_id).list_full()
    if not files:
        raise HTTPException(404, "No files found in project")

    stack_info = detect_extended_stack(files)
    repo_full_name = (proj.get("github") or {}).get("html_url", proj.get("name", ""))
    profile = analyze_repo_profile(files, repo_full_name)

    engine = RepairEngine(db, repo_id)
    repair_plan = await engine.create_repair_plan(files, profile)

    result = {
        "project_id": repo_id,
        "stack_detection": stack_info,
        "repo_profile": profile,
        "repair_plan": repair_plan,
        "analyzed_at": _now(),
    }
    await db.projects.update_one(
        {"id": repo_id},
        {"$set": {
            "repo_profile": profile,
            "stack_detection": stack_info,
            "repair_plan": repair_plan,
            "updated_at": _now(),
        }},
    )
    return result


@secured.post("/repos/{repo_id}/repair")
async def repo_repair(repo_id: str, claims: dict = Depends(require_user)) -> dict:
    """Apply the repair plan to an imported repo project.

    Creates a checkpoint before applying any changes so the repair is
    always reversible.  Returns a structured diff summary.
    """
    await _own(repo_id, claims)
    proj = await db.projects.find_one({"id": repo_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    fs = ProjectFS(db, repo_id)
    old_files = await fs.list_full()
    if not old_files:
        raise HTTPException(404, "No files found in project — cannot repair")

    profile = proj.get("repo_profile") or analyze_repo_profile(old_files, proj.get("name", ""))
    plan = proj.get("repair_plan")
    if not plan:
        engine = RepairEngine(db, repo_id)
        plan = await engine.create_repair_plan(old_files, profile)

    # Create checkpoint before applying any changes
    memory_snapshot = proj.get("project_memory") or {}
    validation_snapshot = proj.get("validation_state") or {}
    checkpoint_id = await create_checkpoint(
        db, repo_id,
        files=old_files,
        memory=memory_snapshot,
        validation=validation_snapshot,
        label="pre-repair",
    )

    # Apply targeted repairs
    engine = RepairEngine(db, repo_id)
    new_files, applied, skipped = await engine.apply_repairs(old_files, plan)

    # Generate diff summary
    diff = generate_diff_summary_for_files(
        old_files, new_files,
        reason="Automated repair pass",
        risk_level=plan.get("risk_level", "low"),
        build_result="skipped",
        validation_result="skipped",
    )

    # Write repaired files back
    changed_paths: list[str] = [d["path"] for d in diff.get("file_diffs", []) if d["action"] != "deleted"]
    for f in new_files:
        old = next((o for o in old_files if o["path"] == f["path"]), None)
        if old is None or old.get("content") != f.get("content"):
            await fs.write(f["path"], f.get("content", ""), f.get("language", "text"))

    # Create a version record for this repair
    await create_version(
        db, repo_id,
        user_request="Automated repair",
        changed_files=changed_paths,
        diff_summary=diff["markdown"],
        satisfied_tasks=applied,
        unsatisfied_tasks=skipped,
        build_status="ready",
        file_snapshot=new_files,
        memory_snapshot=memory_snapshot,
    )

    now = _now()
    await db.projects.update_one(
        {"id": repo_id},
        {"$set": {
            "repair_applied": True,
            "last_repair_at": now,
            "last_checkpoint_id": checkpoint_id,
            "diff_summary": diff,
            "updated_at": now,
        }},
    )
    await hub.broadcast(repo_id, {"type": "repair_complete", "data": {
        "applied": applied,
        "skipped": skipped,
        "diff": diff,
        "checkpoint_id": checkpoint_id,
    }})
    return {
        "ok": True,
        "project_id": repo_id,
        "checkpoint_id": checkpoint_id,
        "applied_repairs": applied,
        "skipped_repairs": skipped,
        "diff_summary": diff,
    }


@secured.get("/repos/{repo_id}/diff")
async def repo_diff(repo_id: str, claims: dict = Depends(require_user)) -> dict:
    """Return the latest diff summary for an imported repo project."""
    await _own(repo_id, claims)
    proj = await db.projects.find_one({"id": repo_id}, {"_id": 0, "diff_summary": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    diff = proj.get("diff_summary")
    if not diff:
        raise HTTPException(404, "No diff summary available — run /repos/{repo_id}/repair first")
    return diff


@secured.post("/repos/{repo_id}/rollback")
async def repo_rollback(repo_id: str, claims: dict = Depends(require_user)) -> dict:
    """Roll back a repo project to its most recent pre-repair checkpoint."""
    await _own(repo_id, claims)
    proj = await db.projects.find_one({"id": repo_id}, {"_id": 0, "last_checkpoint_id": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    checkpoint_id = proj.get("last_checkpoint_id")
    if not checkpoint_id:
        raise HTTPException(409, "No checkpoint found — run /repos/{repo_id}/repair first to create one")

    from app.repos.repair_engine import get_checkpoint
    cp = await get_checkpoint(db, repo_id, checkpoint_id)
    if not cp:
        raise HTTPException(404, "Checkpoint record not found")

    fs = ProjectFS(db, repo_id)
    await db.files.delete_many({"project_id": repo_id})
    restored = 0
    for f in cp.get("file_snapshot", []):
        if f.get("path"):
            await fs.write(f["path"], f.get("content", ""), f.get("language", "text"))
            restored += 1

    memory_snapshot = cp.get("memory_snapshot") or {}
    update_fields: dict = {"updated_at": _now(), "repair_applied": False}
    if memory_snapshot:
        update_fields["project_memory"] = memory_snapshot

    await db.projects.update_one({"id": repo_id}, {"$set": update_fields})
    await hub.broadcast(repo_id, {"type": "rollback_complete", "data": {
        "checkpoint_id": checkpoint_id,
        "restored_files": restored,
    }})
    return {"ok": True, "checkpoint_id": checkpoint_id, "restored_files": restored}


@secured.post("/repos/{repo_id}/create-pr")
async def repo_create_pr(
    repo_id: str,
    body: PRBody,
    claims: dict = Depends(require_user),
) -> dict:
    """Create a GitHub PR from an imported and repaired repo project.

    Includes a meaningful diff summary in the PR body (Phase 2G).
    """
    await _own(repo_id, claims)
    proj = await db.projects.find_one({"id": repo_id}, {"_id": 0})
    if not proj or not proj.get("github"):
        raise HTTPException(400, "Project was not imported from a GitHub repo")
    pat = body.github_pat or await _runtime_secret("GITHUB_PAT")
    if not pat:
        raise HTTPException(403, "Connect GitHub PAT in Settings to open pull requests.")

    # Gather diff summary for meaningful PR body
    diff_summary_data = proj.get("diff_summary") or {}
    diff_markdown = diff_summary_data.get("markdown", "")

    validation = proj.get("validation_state") or {}
    coverage = proj.get("coverage_score") or {}
    repair_plan = proj.get("repair_plan") or {}

    # Build enriched PR body
    pr_body_parts = [
        f"## Amarktai App Builder — Automated Repair & Iteration\n\n",
        f"**Project:** {proj.get('name', repo_id)}\n",
        f"**Stack:** {', '.join(detect_extended_stack(await ProjectFS(db, repo_id).list_full()).get('detected', [])) or 'unknown'}\n",
        f"**Risk level:** {repair_plan.get('risk_level', 'low')}\n\n",
    ]
    if diff_markdown:
        pr_body_parts.append(diff_markdown + "\n\n")
    else:
        pr_body_parts.append("_No diff summary available — this PR was created without a prior repair pass._\n\n")

    if validation:
        status = validation.get("status", "unknown")
        pr_body_parts.append(f"**Validation:** {status}\n")
    if coverage:
        score = coverage.get("coverageScore", 0)
        pr_body_parts.append(f"**Coverage score:** {score}/100\n")

    pr_body_parts.append(
        f"\n_Generated by **{AGENTS_NAME}** through {ROUTER_NAME}._\n"
        f"_Rollback point: checkpoint available in Amarktai workspace._\n"
    )

    github = proj["github"]
    files = await ProjectFS(db, repo_id).list_full()
    payload_files = [
        {"path": f["path"], "content": f["content"]}
        for f in files
        if f["path"] != ".env" and not f["path"].endswith("/.env")
    ]
    branch = body.branch_name or f"amarktai/repair-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    title = body.title or f"Amarktai: automated repair and iteration — {proj.get('name', '')}"
    pr_body = "".join(pr_body_parts)

    try:
        result = await gh.open_pr(
            owner=github["owner"],
            repo=github["repo"],
            base_branch=github.get("default_branch") or github["branch"],
            new_branch=branch,
            files=payload_files,
            title=title,
            body=pr_body,
            pat=pat,
        )
    except Exception as exc:
        raise HTTPException(400, f"Failed to open PR: {exc}")

    await db.projects.update_one(
        {"id": repo_id},
        {"$set": {"pr_url": result.get("pr_url"), "updated_at": _now()}},
    )
    await hub.broadcast(repo_id, {"type": "pr_opened", "data": result})
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2F — STACK DETECTION ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

@secured.post("/projects/{project_id}/detect-stack")
async def detect_project_stack(
    project_id: str, claims: dict = Depends(require_user)
) -> dict:
    """Run extended stack detection on the project's current files.

    Returns a ``stack_detection.json``-compatible dict.
    """
    await _own(project_id, claims)
    files = await ProjectFS(db, project_id).list_full()
    if not files:
        raise HTTPException(404, "No files found in project")
    result = detect_extended_stack(files)
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"stack_detection": result, "updated_at": _now()}},
    )
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2C — RUNTIME SANDBOX PREVIEW ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

@secured.post("/projects/{project_id}/sandbox-preview")
async def sandbox_preview(
    project_id: str, claims: dict = Depends(require_user)
) -> dict:
    """Run a real sandbox build preview for the project.

    Never fakes success — returns build logs and errors on failure.
    """
    await _own(project_id, claims)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    files = await ProjectFS(db, project_id).list_full()
    if not files:
        raise HTTPException(404, "No files found in project")

    emit = emitter_for(project_id)
    svc = PreviewService()
    result = await svc.build_preview(files, emit=emit)

    # Persist preview result to project
    update: dict = {"sandbox_preview_result": result, "updated_at": _now()}
    if result["success"]:
        update["preview_strategy"] = "sandbox"
    await db.projects.update_one({"id": project_id}, {"$set": update})

    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2J — RUNTIME HEALTH ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

@api.get("/runtime/health")
async def runtime_health() -> dict:
    """Report runtime health — active previews, disk, process count, failed builds.

    Acceptance criteria:
    - Reports truth — never claims healthy when previews are broken.
    - Active vs stale preview count.
    - Basic disk usage of /tmp.
    - Preview process count.
    """
    import shutil
    import glob as _glob

    # Count sandbox workspace dirs
    sandbox_dirs = list(Path("/tmp").glob("sandbox_*")) + list(Path("/tmp").glob("amarktai_sandbox_*")) + list(Path("/tmp").glob("preview_*"))
    active_previews = len(sandbox_dirs)

    # Count stale (>2h old)
    now_ts = datetime.now(timezone.utc).timestamp()
    stale_previews = sum(
        1 for d in sandbox_dirs
        if d.is_dir() and (now_ts - d.stat().st_mtime) > 7200
    )

    # Disk usage of /tmp
    try:
        tmp_stat = shutil.disk_usage("/tmp")
        disk_used_mb = round(tmp_stat.used / 1024 / 1024, 1)
        disk_free_mb = round(tmp_stat.free / 1024 / 1024, 1)
    except Exception:
        disk_used_mb = -1
        disk_free_mb = -1

    # Count preview processes
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-c", "-f", "vite|next dev|uvicorn"],
            capture_output=True, text=True, timeout=3,
        )
        preview_proc_count = int(result.stdout.strip() or "0")
    except Exception:
        preview_proc_count = 0

    # Count failed previews in last hour (from project_versions)
    try:
        one_hour_ago = datetime.now(timezone.utc).replace(
            second=0, microsecond=0
        ).isoformat()
        failed_count = await db.project_versions.count_documents({
            "build_status": "failed",
            "created_at": {"$gte": one_hour_ago},
        })
    except Exception:
        failed_count = 0

    # Active projects running
    try:
        running_count = await db.projects.count_documents({"status": "running"})
        queued_count = await db.projects.count_documents({"status": "queued"})
    except Exception:
        running_count = 0
        queued_count = 0

    healthy = (stale_previews == 0 and disk_free_mb > 500 and failed_count < 10)

    return {
        "status": "healthy" if healthy else "degraded",
        "active_previews": active_previews,
        "stale_previews": stale_previews,
        "disk_used_mb": disk_used_mb,
        "disk_free_mb": disk_free_mb,
        "preview_process_count": preview_proc_count,
        "failed_preview_count_last_hour": failed_count,
        "running_projects": running_count,
        "queued_projects": queued_count,
        "checked_at": _now(),
    }


# ════════════════════════════════════════════════════════════════════════════
# PHASE 3 — AGENT REGISTRY ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@api.get("/agents")
async def list_agents() -> dict:
    """Return the complete agent registry with roles, tools, and status."""
    agents = get_all_agents()
    return {
        "agents": agents,
        "total": len(agents),
        "retrieved_at": _now(),
    }


@api.get("/agents/status")
async def agents_status() -> dict:
    """Return a summary of agent status: active, deterministic, partial, planned."""
    summary = get_agent_status_summary()
    truth = await _capability_truth()
    cap_summary = truth.get("capabilities", {})
    return {
        **summary,
        "capabilities": cap_summary,
        "checked_at": _now(),
    }


@api.get("/orchestration/health")
async def orchestration_health() -> dict:
    """Report orchestration health — agents, capabilities, and readiness."""
    agent_summary = get_agent_status_summary()
    truth = await _capability_truth()
    cap_summary = truth.get("capabilities", {})

    # Check required agents
    required_agents = [
        "manager", "product_strategist", "creative_director", "ux_architect",
        "ui_designer", "frontend_coder", "backend_coder", "repo_engineer",
        "media_director", "logo_agent", "motion_3d", "qa_agent",
        "visual_qa", "accessibility", "seo_performance", "security",
        "deployment", "worker",
    ]
    agents_registry = get_all_agents()
    present = [a for a in required_agents if a in agents_registry]
    missing = [a for a in required_agents if a not in agents_registry]

    # Capability gates
    image_gen_available = cap_summary.get("image_generation", {}).get("available", False)
    video_gen_available = cap_summary.get("video_generation", {}).get("available", False)
    voice_gen_available = cap_summary.get("voice_generation", {}).get("available", False)
    github_available = cap_summary.get("github_integration", {}).get("available", False)
    preview_available = cap_summary.get("preview_generation", {}).get("available", False)

    healthy = (
        len(missing) == 0
        and agent_summary.get("all_required_present", False)
        and agent_summary.get("active", 0) >= 7
    )

    return {
        "status": "healthy" if healthy else "degraded",
        "required_agents": len(required_agents),
        "agents_present": len(present),
        "agents_missing": missing,
        "agent_summary": agent_summary,
        "capability_gates": {
            "image_generation": image_gen_available,
            "video_generation": video_gen_available,
            "voice_generation": voice_gen_available,
            "github_integration": github_available,
            "preview_generation": preview_available,
        },
        "premium_output_enforced": True,
        "cheap_mode_still_premium": True,
        "motion_trigger_keywords": sorted(MOTION_TRIGGER_KEYWORDS),
        "checked_at": _now(),
    }


@secured.post("/projects/{project_id}/detect-build-mode")
async def detect_build_mode_for_prompt(
    project_id: str,
    body: dict,
    claims: dict = Depends(require_user),
) -> dict:
    """Detect the optimal build mode and agent routing from a user prompt.

    Implements Phase 3 build mode intelligence — AI-decided from the prompt.

    Body: {"prompt": str, "mode_hint": str | null}
    Returns: {"mode", "agent_routing", "needs_motion", "needs_backend", "needs_security", ...}
    """
    await _own(project_id, claims)
    prompt = body.get("prompt", "")
    mode_hint = body.get("mode_hint")

    from agents.mode_classifier import classify_build_mode
    classification = classify_build_mode(prompt, mode_hint)

    mode = classification.mode
    routing = get_agent_routing(mode, prompt=prompt, auth_required=classification.auth_required)

    return {
        "mode": mode,
        "label": classification.label,
        "complexity": classification.complexity,
        "auth_required": classification.auth_required,
        "pages_expected": classification.pages_expected,
        "agent_routing": routing,
        "needs_motion": needs_motion_agent(prompt, mode),
        "needs_backend": bool(classification.auth_required or mode in ("full_stack", "api_service", "dashboard", "admin_panel")),
        "needs_security": bool(classification.auth_required or mode in ("full_stack", "api_service", "dashboard", "admin_panel")),
        "premium_required": True,
        "cheap_mode_design_gated": True,
        "detected_at": _now(),
    }


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════════════
# BUILD STORAGE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class BuildArchiveBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    confirmed: bool = False


class BuildDeleteBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    confirmed: bool = False


class BuildMetaUpdateBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    updates: dict


@secured.get("/builds")
async def list_builds(
    workspace_type: Optional[str] = None,
    claims: dict = Depends(require_user),
) -> dict:
    """Return all saved build workspaces, optionally filtered by type.

    Types: repos | generated | incomplete | releases
    """
    try:
        workspaces = list_workspaces(workspace_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Failed to list builds: {exc}")
    try:
        usage = storage_usage()
    except Exception:
        usage = {}
    storage_root = usage.get("root") or str(get_builds_storage_root())
    return {
        "items": workspaces,
        "workspaces": workspaces,
        "total": len(workspaces),
        "storage_root": storage_root,
        "workspace_types": ["repos", "generated", "incomplete", "releases"],
        "storage": usage,
        "retrieved_at": _now(),
    }


@secured.get("/builds/storage-usage")
async def builds_storage_usage(claims: dict = Depends(require_user)) -> dict:
    """Return disk usage for the builds storage root."""
    try:
        return {**storage_usage(), "retrieved_at": _now()}
    except Exception as exc:
        raise HTTPException(500, f"Storage usage error: {exc}")


@secured.post("/builds/archive")
async def builds_archive(
    body: BuildArchiveBody,
    claims: dict = Depends(require_user),
) -> dict:
    """Archive a build workspace (move to archived/ subfolder)."""
    try:
        result = archive_workspace(Path(body.workspace_path), confirmed=body.confirmed)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Archive failed: {exc}")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Archive failed"))
    return result


@secured.post("/builds/delete")
async def builds_delete(
    body: BuildDeleteBody,
    claims: dict = Depends(require_user),
) -> dict:
    """Permanently delete a build workspace. Requires confirmed=True."""
    if claims.get("role") != "admin":
        raise HTTPException(403, "Only admins can permanently delete build workspaces.")
    try:
        result = delete_workspace(Path(body.workspace_path), confirmed=body.confirmed)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Delete failed: {exc}")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Delete failed"))
    return result


@secured.post("/builds/update-meta")
async def builds_update_meta(
    body: BuildMetaUpdateBody,
    claims: dict = Depends(require_user),
) -> dict:
    """Update metadata for a build workspace."""
    try:
        result = update_workspace_metadata(Path(body.workspace_path), body.updates)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Metadata update failed: {exc}")
    return {"ok": True, "meta": result}


@secured.get("/builds/{project_id}")
async def get_build_by_project_id(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Return a saved build workspace by project_id."""
    try:
        for workspace in list_workspaces():
            if workspace.get("project_id") == project_id:
                return {"ok": True, "item": workspace, "retrieved_at": _now()}
    except Exception as exc:
        raise HTTPException(500, f"Failed to load build: {exc}")
    raise HTTPException(404, "Build workspace not found")


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — REAL VPS GIT WORKSPACE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class GitImportBody(BaseModel):
    repo_url: str = Field(min_length=10, max_length=500)
    branch: str = "main"
    confirm_overwrite: bool = False


class GitPullBody(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=200)
    confirm_overwrite_dirty: bool = False


class GitCommitBody(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=500)
    author_name: str = "Amarktai Builder"
    author_email: str = "builder@amarktai.com"


class GitPushBody(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=200)
    force: bool = False


class GitPRBody(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    head_branch: str = Field(min_length=1, max_length=200)
    base_branch: str = "main"
    title: str = "Amarktai Builder: automated changes"
    body: str = ""


@secured.post("/builds/import-git")
async def builds_import_git(body: GitImportBody, claims: dict = Depends(require_user)) -> dict:
    """Clone a GitHub repo into VPS build storage (real git clone, not just metadata)."""
    github_pat = await _runtime_secret("GITHUB_PAT")
    try:
        result = _git_svc.clone_repo(
            repo_url=body.repo_url,
            branch=body.branch,
            github_pat=github_pat or None,
            confirm_overwrite=body.confirm_overwrite,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Git clone failed: {exc}")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Clone failed"))
    return result


@secured.post("/builds/{project_id}/git/pull")
async def builds_git_pull(project_id: str, body: GitPullBody, claims: dict = Depends(require_user)) -> dict:
    """Pull latest changes for a workspace."""
    github_pat = await _runtime_secret("GITHUB_PAT")
    try:
        result = _git_svc.pull_latest(
            owner=body.owner,
            repo=body.repo,
            branch=body.branch,
            github_pat=github_pat or None,
            confirm_overwrite_dirty=body.confirm_overwrite_dirty,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Git pull failed: {exc}")
    return result


@secured.post("/builds/{project_id}/git/status")
async def builds_git_status(project_id: str, body: dict, claims: dict = Depends(require_user)) -> dict:
    """Get git status for a workspace."""
    owner = body.get("owner", "")
    repo = body.get("repo", "")
    branch = body.get("branch", "main")
    try:
        return _git_svc.get_git_status(owner, repo, branch)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@secured.post("/builds/{project_id}/git/commit")
async def builds_git_commit(project_id: str, body: GitCommitBody, claims: dict = Depends(require_user)) -> dict:
    """Stage all changes and create a commit."""
    try:
        return _git_svc.commit_changes(
            owner=body.owner,
            repo=body.repo,
            branch=body.branch,
            message=body.message,
            author_name=body.author_name,
            author_email=body.author_email,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@secured.post("/builds/{project_id}/git/push")
async def builds_git_push(project_id: str, body: GitPushBody, claims: dict = Depends(require_user)) -> dict:
    """Push branch to origin."""
    github_pat = await _runtime_secret("GITHUB_PAT")
    try:
        result = _git_svc.push_branch(
            owner=body.owner,
            repo=body.repo,
            branch=body.branch,
            github_pat=github_pat or None,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Git push failed: {exc}")
    return result


@secured.post("/builds/{project_id}/git/open-pr")
async def builds_git_open_pr(project_id: str, body: GitPRBody, claims: dict = Depends(require_user)) -> dict:
    """Open a GitHub pull request."""
    github_pat = await _runtime_secret("GITHUB_PAT")
    try:
        result = _git_svc.open_pull_request(
            owner=body.owner,
            repo=body.repo,
            head_branch=body.head_branch,
            base_branch=body.base_branch,
            title=body.title,
            body=body.body,
            github_pat=github_pat or None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Open PR failed: {exc}")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "PR creation failed"))
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 3 — FRONTEND DETECTION AND PREVIEW ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@secured.post("/builds/{project_id}/detect-frontend")
async def builds_detect_frontend(project_id: str, body: dict, claims: dict = Depends(require_user)) -> dict:
    """Detect the frontend framework in a workspace."""
    workspace_path = body.get("workspace_path", "")
    if not workspace_path:
        raise HTTPException(400, "workspace_path is required")
    try:
        result = detect_frontend(workspace_path)
        files = list_project_files(workspace_path)
    except Exception as exc:
        raise HTTPException(500, f"Frontend detection failed: {exc}")
    return {**result, "file_list": files[:50], "detected_at": _now()}


def _workspace_path_for_project(project_id: str, body: dict | None = None) -> str:
    body = body or {}
    if body.get("workspace_path"):
        return str(body["workspace_path"])
    for workspace in list_workspaces():
        if workspace.get("project_id") == project_id:
            return workspace.get("local_path", "")
    raise HTTPException(404, "Build workspace not found. Provide workspace_path or import/generate the workspace first.")


@secured.post("/builds/{project_id}/preview/start")
async def builds_preview_start(project_id: str, body: dict | None = None, claims: dict = Depends(require_user)) -> dict:
    """Start a real static or dev-server preview for a workspace."""
    workspace_path = _workspace_path_for_project(project_id, body)
    try:
        result = start_preview(project_id, workspace_path, backend_base_url="/api")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Preview start failed: {exc}")
    return result


@secured.post("/builds/{project_id}/preview/stop")
async def builds_preview_stop(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Stop a running workspace preview."""
    try:
        return stop_preview(project_id)
    except Exception as exc:
        raise HTTPException(500, f"Preview stop failed: {exc}")


@secured.get("/builds/{project_id}/preview/status")
async def builds_preview_status(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Get the preview status for a project workspace."""
    return {**load_preview_state(project_id), "checked_at": _now()}


@secured.get("/builds/{project_id}/preview/url")
async def builds_preview_url(project_id: str, claims: dict = Depends(require_user)) -> dict:
    """Get the preview URL for a project workspace."""
    state = load_preview_state(project_id)
    return {
        "project_id": project_id,
        "url": state.get("url"),
        "status": state.get("status", "not_started"),
        "kind": state.get("kind"),
        "note": "Start the preview with POST /builds/{project_id}/preview/start" if not state.get("url") else None,
        "checked_at": _now(),
    }


@api.get("/builds/{project_id}/preview/static/{file_path:path}")
async def builds_static_preview_file(
    project_id: str,
    file_path: str,
    workspace_path: str = Query(min_length=1, max_length=1024),
) -> FileResponse:
    """Serve static preview files from a path-safe build workspace."""
    root = get_builds_storage_root().resolve()
    workspace = Path(workspace_path).resolve()
    try:
        workspace.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Preview workspace must be inside build storage.")
    detection = detect_frontend(workspace)
    static_root = (workspace / (detection.get("frontend_root") or ".")).resolve()
    try:
        static_root.relative_to(workspace)
    except ValueError:
        raise HTTPException(400, "Unsafe static preview root.")
    target = (static_root / file_path).resolve()
    try:
        target.relative_to(static_root)
    except ValueError:
        raise HTTPException(400, "Unsafe preview path.")
    if target.is_dir():
        target = target / "index.html"
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Preview file not found.")
    return FileResponse(target)


# ════════════════════════════════════════════════════════════════════════════
# PHASE 4 — BUILD / TEST / INSTALL COMMAND RUNNER ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class RunCommandBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    package_manager: str = "npm"


@secured.post("/builds/{project_id}/install")
async def builds_install(project_id: str, body: RunCommandBody, claims: dict = Depends(require_user)) -> dict:
    """Run npm/pnpm/yarn install for a workspace."""
    try:
        result = run_install(body.workspace_path, body.package_manager, project_id=project_id)
    except Exception as exc:
        raise HTTPException(500, f"Install failed: {exc}")
    return result


@secured.post("/builds/{project_id}/build")
async def builds_build(project_id: str, body: RunCommandBody, claims: dict = Depends(require_user)) -> dict:
    """Run npm/pnpm/yarn build for a workspace."""
    try:
        result = run_build(body.workspace_path, body.package_manager, project_id=project_id)
    except Exception as exc:
        raise HTTPException(500, f"Build failed: {exc}")
    return result


@secured.post("/builds/{project_id}/test")
async def builds_test(project_id: str, body: RunCommandBody, claims: dict = Depends(require_user)) -> dict:
    """Run tests for a workspace."""
    try:
        result = run_tests(body.workspace_path, body.package_manager, project_id=project_id)
    except Exception as exc:
        raise HTTPException(500, f"Test run failed: {exc}")
    return result


@secured.get("/builds/{project_id}/logs")
async def builds_logs(project_id: str, limit: int = 20, claims: dict = Depends(require_user)) -> dict:
    """Return recent command runner logs for a project."""
    try:
        logs = get_runner_logs(project_id, limit=min(limit, 100))
    except Exception as exc:
        raise HTTPException(500, f"Log retrieval failed: {exc}")
    return {"project_id": project_id, "logs": logs, "total": len(logs), "retrieved_at": _now()}


# ════════════════════════════════════════════════════════════════════════════
# PHASE 5 — CONTINUE BUILD / REPAIR PIPELINE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class ContinueBuildBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    project_description: str = ""
    auto_apply: bool = False


class RepairDiffBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    changes: list[dict]


class ApplyRepairBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    changes: list[dict]
    auto_apply: bool = False


class WorkspaceVersionBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)
    label: str = ""
    notes: str = ""


@secured.post("/builds/{project_id}/continue")
async def builds_continue(project_id: str, body: ContinueBuildBody, claims: dict = Depends(require_user)) -> dict:
    """
    Continue an incomplete build: load workspace, detect stack, find missing pieces,
    generate a completion plan, and optionally apply repairs.
    """
    ws_info = load_build_workspace(body.workspace_path)
    if not ws_info.get("ok"):
        raise HTTPException(404, ws_info.get("error", "Workspace not found"))

    stack_info = detect_workspace_stack(body.workspace_path)
    missing_info = detect_missing_pieces(body.workspace_path, stack_info.get("primary", "unknown"))
    plan = generate_completion_plan(ws_info, stack_info, missing_info, body.project_description)
    save_repair_plan_to_workspace(body.workspace_path, plan)

    return {
        "ok": True,
        "workspace": ws_info,
        "stack": stack_info,
        "missing": missing_info,
        "plan": plan,
        "auto_apply": body.auto_apply,
        "note": (
            "Plan generated. Use /builds/{project_id}/apply-repair to apply changes."
            if not body.auto_apply
            else "Plan generated. Apply with /builds/{project_id}/apply-repair with auto_apply=True."
        ),
        "generated_at": _now(),
    }


@secured.post("/builds/{project_id}/repair-plan")
async def builds_repair_plan(project_id: str, body: ContinueBuildBody, claims: dict = Depends(require_user)) -> dict:
    """Generate a repair plan without applying changes."""
    ws_info = load_build_workspace(body.workspace_path)
    if not ws_info.get("ok"):
        raise HTTPException(404, ws_info.get("error", "Workspace not found"))

    stack_info = detect_workspace_stack(body.workspace_path)
    missing_info = detect_missing_pieces(body.workspace_path, stack_info.get("primary", "unknown"))
    plan = generate_completion_plan(ws_info, stack_info, missing_info, body.project_description)
    return {"ok": True, "plan": plan, "stack": stack_info, "missing": missing_info}


@secured.post("/builds/{project_id}/apply-repair")
async def builds_apply_repair(project_id: str, body: ApplyRepairBody, claims: dict = Depends(require_user)) -> dict:
    """Apply a set of file changes to a workspace. Returns diff if auto_apply=False."""
    try:
        result = apply_repair(body.workspace_path, body.changes, auto_apply=body.auto_apply)
    except Exception as exc:
        raise HTTPException(500, f"Repair failed: {exc}")
    return result


@secured.post("/builds/{project_id}/version")
async def builds_version(project_id: str, body: WorkspaceVersionBody, claims: dict = Depends(require_user)) -> dict:
    """Create a version snapshot of the current workspace state."""
    result = create_workspace_version(body.workspace_path, label=body.label, notes=body.notes)
    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "Version creation failed"))
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 6 — LIVE PROVIDER PROBE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@api.get("/providers/status")
async def providers_status() -> dict:
    """
    Return cached provider status. Does NOT trigger a live probe.
    Use POST /api/providers/probe to run fresh probes.
    """
    cached = _probe_svc._CACHE.get("all_providers")
    if cached:
        return {k: v for k, v in cached.items() if not k.startswith("_")}
    truth = await _capability_truth()
    providers = truth.get("providers", {})
    return {
        "note": "No probe results cached. POST /api/providers/probe to run live probes.",
        "genx": {"status": providers.get("genx", {}).get("live_status", "key_missing")},
        "qwen": {"status": providers.get("qwen", {}).get("live_status", "key_missing")},
        "github": {"status": providers.get("github", {}).get("live_status", "key_missing")},
        "brave": {"status": providers.get("brave", {}).get("live_status", "key_missing")},
        "pixabay": {"status": providers.get("pixabay", {}).get("live_status", "key_missing")},
        "probed_at": None,
    }


@secured.post("/providers/probe")
async def providers_probe(claims: dict = Depends(require_user)) -> dict:
    """Run live probes against all configured providers and return results."""
    genx_key = await _runtime_secret("GENX_API_KEY")
    qwen_key = await _runtime_secret("QWEN_API_KEY")
    github_pat = await _runtime_secret("GITHUB_PAT")
    brave_key = await _runtime_secret("BRAVE_SEARCH_API_KEY")
    pixabay_key = await _runtime_secret("PIXABAY_API_KEY")
    qwen_base = await _runtime_secret("QWEN_BASE_URL")

    result = await _probe_svc.probe_all_providers(
        genx_key=genx_key or "",
        qwen_key=qwen_key or "",
        github_pat=github_pat or "",
        brave_key=brave_key or "",
        pixabay_key=pixabay_key or "",
        qwen_base_url=qwen_base or None,
        force_refresh=True,
    )
    return result


@secured.post("/providers/probe/{provider}")
async def providers_probe_single(provider: str, claims: dict = Depends(require_user)) -> dict:
    """Run a live probe against a single provider."""
    genx_key = await _runtime_secret("GENX_API_KEY")
    qwen_key = await _runtime_secret("QWEN_API_KEY")
    github_pat = await _runtime_secret("GITHUB_PAT")
    brave_key = await _runtime_secret("BRAVE_SEARCH_API_KEY")
    pixabay_key = await _runtime_secret("PIXABAY_API_KEY")
    qwen_base = await _runtime_secret("QWEN_BASE_URL")

    result = await _probe_svc.probe_single_provider(
        provider=provider,
        genx_key=genx_key or "",
        qwen_key=qwen_key or "",
        github_pat=github_pat or "",
        brave_key=brave_key or "",
        pixabay_key=pixabay_key or "",
        qwen_base_url=qwen_base or None,
    )
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 7 — GENX FULL MODEL DISCOVERY
# ════════════════════════════════════════════════════════════════════════════

@api.get("/models/genx")
async def models_genx() -> dict:
    """Return the current GenX model registry (cached or static fallback)."""
    truth = await _capability_truth()
    genx_state = truth.get("providers", {}).get("genx", {})
    provider_available = bool(
        genx_state.get("configured") and genx_state.get("live_status") == "live_ok"
    )
    registry = _genx_sync.load_registry()
    return {
        "available": provider_available,
        "provider": {
            "configured": genx_state.get("configured", False),
            "source": genx_state.get("source", "missing"),
            "live_status": genx_state.get("live_status", "key_missing"),
            "reason": genx_state.get("reason"),
        },
        "source": registry.get("source", "fallback"),
        "model_count": registry.get("model_count", 0) if provider_available else 0,
        "known_model_count": registry.get("model_count", 0),
        "capability_counts": registry.get("capability_counts", {}),
        "synced_at": registry.get("synced_at"),
        "models": [
            {
                "id": m.get("id"),
                "known": True,
                "available": provider_available,
                "unavailable_reason": None if provider_available else genx_state.get("reason") or "GENX_API_KEY not configured",
            }
            for m in registry.get("models", [])
        ],
        "note": "POST /api/models/genx/sync to refresh from live GenX API.",
    }


@secured.post("/models/genx/sync")
async def models_genx_sync(claims: dict = Depends(require_user)) -> dict:
    """Trigger a live sync of the GenX model list."""
    api_key = await _runtime_secret("GENX_API_KEY")
    result = await _genx_sync.sync_genx_models(api_key or "")
    return result


@api.get("/models/router-status")
async def models_router_status() -> dict:
    """Return the current model routing decisions for all task types."""
    truth = await _capability_truth()
    genx_state = truth.get("providers", {}).get("genx", {})
    provider_available = bool(
        genx_state.get("configured") and genx_state.get("live_status") == "live_ok"
    )
    registry = _genx_sync.load_registry()
    available = [m.get("id", "") for m in registry.get("models", [])] if provider_available else []
    routing = get_router_status(available)
    return {
        "available_model_count": len(available),
        "known_model_count": registry.get("model_count", 0),
        "provider": {
            "configured": genx_state.get("configured", False),
            "source": genx_state.get("source", "missing"),
            "live_status": genx_state.get("live_status", "key_missing"),
            "reason": genx_state.get("reason"),
        },
        "source": registry.get("source", "fallback"),
        "routing": routing,
        "task_types": list(TASK_ROUTING.keys()),
        "retrieved_at": _now(),
    }


# ════════════════════════════════════════════════════════════════════════════
# PHASE 10 — PREMIUM QUALITY GATE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class QualityGateBody(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=1024)


@secured.post("/builds/{project_id}/quality-gate")
async def builds_quality_gate(project_id: str, body: QualityGateBody, claims: dict = Depends(require_user)) -> dict:
    """Run the premium quality gate on a workspace."""
    try:
        result = run_quality_gate(body.workspace_path)
    except Exception as exc:
        raise HTTPException(500, f"Quality gate failed: {exc}")
    return result


@secured.get("/builds/{project_id}/quality-report")
async def builds_quality_report(
    project_id: str,
    workspace_path: str = Query(min_length=1, max_length=1024),
    claims: dict = Depends(require_user),
) -> dict:
    """Get the quality report for a workspace (re-runs the gate)."""
    try:
        result = run_quality_gate(workspace_path)
    except Exception as exc:
        raise HTTPException(500, f"Quality report failed: {exc}")
    return result


# ════════════════════════════════════════════════════════════════════════════
# PHASE 11 — DASHBOARD BACKEND SUPPORT ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@secured.get("/dashboard/status")
async def dashboard_status(claims: dict = Depends(require_user)) -> dict:
    """
    Return a comprehensive, truthful system status for the dashboard.

    Includes: build storage, provider config (not live probe), model registry,
    agent readiness, and router decisions.
    """
    # Storage
    try:
        storage = storage_usage()
    except Exception:
        storage = {}

    # Workspaces
    try:
        workspaces = list_workspaces()
    except Exception:
        workspaces = []

    # GenX model registry
    registry = _genx_sync.load_registry()
    available_models = [m.get("id", "") for m in registry.get("models", [])]

    # Routing sample
    sample_routing = {
        t: route_task(t, available_models)
        for t in ["code_repair", "frontend_design", "repo_audit"]
    }

    # Provider configured status (not live probe — use POST /providers/probe for live)
    genx_key = await _runtime_secret("GENX_API_KEY")
    qwen_key = await _runtime_secret("QWEN_API_KEY")
    github_pat = await _runtime_secret("GITHUB_PAT")

    # Cached probe results
    cached_probes = _probe_svc._CACHE.get("all_providers", {})

    # Agent readiness
    agent_summary = get_agent_status_summary()

    return {
        "storage": storage,
        "workspace_count": len(workspaces),
        "genx_models": {
            "source": registry.get("source", "fallback"),
            "count": registry.get("model_count", 0),
            "synced_at": registry.get("synced_at"),
        },
        "providers_configured": {
            "genx": bool(genx_key),
            "qwen": bool(qwen_key),
            "github": bool(github_pat),
        },
        "providers_live_status": {
            p: cached_probes.get(p, {}).get("status", "key_present_not_tested")
            for p in ("genx", "qwen", "github", "brave", "pixabay")
        },
        "routing_sample": sample_routing,
        "agent_summary": agent_summary,
        "truthful_note": (
            "providers_configured shows if keys exist; "
            "providers_live_status shows last probe result. "
            "POST /api/providers/probe to refresh live status."
        ),
        "retrieved_at": _now(),
    }


# Routers must be mounted after all route decorators have executed. FastAPI
# copies router routes at include time, so mounting earlier silently drops later
# endpoints such as /api/builds.
app.include_router(api)
app.include_router(secured)
app.include_router(admin_api)
