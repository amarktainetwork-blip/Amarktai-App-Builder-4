"""
Multi-agent orchestrator: Scout → Architect → Coder → Reviewer (mode-aware).

The orchestrator reads/writes everything through MongoDB and emits real-time events to a
WebSocket hub so the dashboard can render the timeline live.

Modes supported:
  research, landing_page, website, media_page, web_app, pwa, full_stack,
  dashboard, admin_panel, api_service, automation_bot, trading_bot_scaffold,
  repo_fix
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .genx_provider import GenXProvider
from .mcp_tools import ProjectFS
from .prompts import (
    ARCHITECT_PROMPT,
    CODER_PROMPT,
    ITERATION_PROMPT,
    REPO_FIX_PROMPT,
    RESEARCH_PROMPT,
    REVIEWER_PROMPT,
    SCOUT_PROMPT,
)

# Per-agent timeout in seconds
AGENT_TIMEOUTS = {
    "scout": 180,
    "architect": 240,
    "coder": 480,
    "reviewer": 240,
    "iteration": 300,
    "research": 240,
    "repo_fix": 480,
}

# App files that indicate the project has a previewable entry point
_PREVIEW_ENTRY_FILES = {"index.html", "index.htm"}
# Files that are metadata, not app output
_META_FILES = {"requirements.md", "tech_stack.json"}

# Modes that do not require index.html to be "ready"
_NO_PREVIEW_MODES = {
    "research", "full_stack", "dashboard", "admin_panel",
    "api_service", "automation_bot", "trading_bot_scaffold", "repo_fix",
}
# Modes that must have app files to be considered ready
_REQUIRES_APP_FILES_MODES = {
    "landing_page", "website", "media_page", "web_app", "pwa",
}

# JSON repair prompt
_JSON_REPAIR_PROMPT = (
    "Repair this response into valid JSON matching the required schema. "
    "Do not invent new content. Do not summarize. "
    "Preserve file contents, escaping strings correctly. Return JSON only."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_fences(text: str) -> str:
    """Strip ```json ... ``` fences if a model accidentally wraps its JSON output."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _parse_json(text: str) -> dict:
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract the first {...} block.
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            return json.loads(m.group(0))
        raise


def _has_app_files(files: list[dict]) -> bool:
    """Return True if there are generated app files (not just metadata)."""
    return any(f["path"] not in _META_FILES for f in files)


def _has_preview_entry(files: list[dict]) -> bool:
    """Return True if the project has a previewable entry file."""
    return any(f["path"] in _PREVIEW_ENTRY_FILES for f in files)


EmitFn = Callable[[dict], Awaitable[None]]


class BuildCancelled(Exception):
    """Raised when the build is cancelled by the user."""


class Orchestrator:
    def __init__(self, db, provider: GenXProvider, project_id: str, emit: EmitFn):
        self.db = db
        self.provider = provider
        self.project_id = project_id
        self.fs = ProjectFS(db, project_id)
        self.emit = emit
        # Tracks repair attempts within a single build run.
        # A new Orchestrator is created for each build/retry, so this resets naturally.
        self._repair_attempts: int = 0

    # ---------- shared helpers ----------

    async def _load_project(self) -> dict:
        """Load the current project document (shared context source)."""
        doc = await self.db.projects.find_one({"id": self.project_id}, {"_id": 0})
        return doc or {}

    async def _shared_context(self) -> dict:
        """Build the shared context object passed to agents (Phase 2 spec)."""
        proj = await self._load_project()
        return {
            "project_id": self.project_id,
            "prompt": proj.get("prompt", ""),
            "mode": proj.get("mode", "web_app"),
            "quality_tier": proj.get("quality_tier", "balanced"),
            "recommended_tier": proj.get("recommended_tier"),
            "stack_decision": proj.get("selected_stack", {}),
            "preview_strategy": proj.get("preview_strategy", "iframe"),
            "media_strategy": proj.get("media_strategy", {}),
            "github_context": proj.get("github", {}),
            "validation_state": proj.get("validation_state", {}),
            "repair_attempts": self._repair_attempts,
        }

    async def _is_cancelled(self) -> bool:
        doc = await self.db.projects.find_one(
            {"id": self.project_id}, {"_id": 0, "cancel_requested": 1}
        )
        return bool(doc and doc.get("cancel_requested"))

    async def _check_cancel(self) -> None:
        """Raise BuildCancelled if a stop was requested."""
        if await self._is_cancelled():
            raise BuildCancelled("Build cancelled by user.")

    async def _record_message(self, role: str, agent: str | None, content: str, meta: dict | None = None) -> dict:
        msg = {
            "id": str(uuid.uuid4()),
            "project_id": self.project_id,
            "role": role,
            "agent": agent,
            "content": content,
            "meta": meta or {},
            "created_at": _now(),
        }
        await self.db.messages.insert_one(dict(msg))
        msg.pop("_id", None)
        await self.emit({"type": "message", "data": msg})
        return msg

    async def _record_event(self, agent: str, status: str, detail: str = "", meta: dict | None = None) -> dict:
        evt = {
            "id": str(uuid.uuid4()),
            "project_id": self.project_id,
            "agent": agent,
            "status": status,  # "started" | "thinking" | "completed" | "failed" | "skipped" | "cancelled"
            "detail": detail,
            "meta": meta or {},
            "created_at": _now(),
        }
        await self.db.agent_events.insert_one(dict(evt))
        evt.pop("_id", None)
        await self.emit({"type": "agent_event", "data": evt})
        return evt

    async def _set_status(self, status: str, extra: dict | None = None) -> None:
        updates: dict = {"status": status, "updated_at": _now()}
        if extra:
            updates.update(extra)
        await self.db.projects.update_one(
            {"id": self.project_id}, {"$set": updates}
        )
        payload = {"status": status}
        if extra:
            payload.update({k: v for k, v in extra.items() if k in ("error", "failed_agent")})
        await self.emit({"type": "project_status", "data": payload})

    async def _fail_project(self, failed_agent: str, error: str) -> None:
        now = _now()
        await self.db.projects.update_one(
            {"id": self.project_id},
            {"$set": {
                "status": "failed",
                "failed_agent": failed_agent,
                "error": error,
                "completed_at": now,
                "updated_at": now,
            }},
        )
        await self.emit({"type": "project_status", "data": {
            "status": "failed", "failed_agent": failed_agent, "error": error,
        }})
        await self.emit({"type": "error", "data": {"message": error}})

    async def _track_usage(self, model_label: str, prompt_chars: int, response_chars: int) -> None:
        # Rough character-based estimate (~4 chars/token) — good enough for a UI counter.
        tokens = (prompt_chars + response_chars) // 4
        cost_usd = round(tokens * 0.000003, 6)
        await self.db.projects.update_one(
            {"id": self.project_id},
            {"$inc": {"usage.tokens": tokens, "usage.cost_usd": cost_usd},
             "$set": {"usage.last_model": model_label, "updated_at": _now()}},
        )
        await self.emit({"type": "usage", "data": {
            "delta_tokens": tokens, "delta_cost": cost_usd, "model": model_label,
        }})

    async def _repair_json(self, agent: str, raw_text: str, parse_error: str) -> dict:
        """Attempt a single JSON repair using a cheap model. Returns parsed dict or raises."""
        await self._record_event(agent, "repairing",
                                 f"JSON parse failed ({parse_error}). Attempting auto-repair.")
        repair_model = "gpt-5-nano"  # cheapest available; fallback handled in provider
        user_msg = f"{_JSON_REPAIR_PROMPT}\n\nOriginal response:\n{raw_text}"
        result = await self.provider.complete(
            agent="repair",
            system_prompt=_JSON_REPAIR_PROMPT,
            user_message=user_msg,
            session_id=f"{self.project_id}:{agent}:repair",
            preferred_model=repair_model,
        )
        await self._track_usage(result["model_label"], len(user_msg), len(result["text"]))
        return _parse_json(result["text"])

    async def _run_agent(self, agent: str, system: str, user: str) -> dict:
        timeout = AGENT_TIMEOUTS.get(agent, 300)
        await self._record_event(agent, "started", f"{agent.title()} engaged.")
        await self._record_event(agent, "thinking", "Calling model...")
        try:
            result = await asyncio.wait_for(
                self.provider.complete(
                    agent=agent, system_prompt=system, user_message=user,
                    session_id=f"{self.project_id}:{agent}",
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            msg = f"Build timed out during {agent} after {timeout}s."
            await self._record_event(agent, "failed", msg)
            raise TimeoutError(msg)
        await self._track_usage(result["model_label"], len(system) + len(user), len(result["text"]))
        try:
            data = _parse_json(result["text"])
        except Exception as e:
            parse_err = str(e)
            await self._record_event(agent, "failed",
                                     f"JSON parse failed: {parse_err}",
                                     meta={"raw": result["text"][:2000]})
            # Attempt exactly one repair
            try:
                data = await self._repair_json(agent, result["text"], parse_err)
                await self._record_event(agent, "repaired",
                                         f"JSON repair succeeded for {agent}.")
            except Exception as repair_err:
                if agent == "coder":
                    err_msg = "Coder returned invalid JSON and automatic repair failed."
                else:
                    err_msg = f"{agent.title()} returned invalid JSON and automatic repair failed."
                await self._record_event(agent, "failed",
                                         f"Repair also failed: {repair_err}",
                                         meta={"repair_error": str(repair_err)})
                raise ValueError(err_msg) from repair_err
        await self._record_event(agent, "completed", f"{agent.title()} done.",
                                 meta={"model": result["model_label"]})
        return {"data": data, "model_label": result["model_label"]}

    # ---------- full build pipeline ----------

    async def run_full_build(self, user_prompt: str, mode: str = "web_app",
                              stack_decision: dict | None = None) -> None:
        """Mode-aware full build pipeline.

        Dispatches to the appropriate sub-pipeline based on mode.
        """
        await self._set_status("running")
        await self._record_message("user", None, user_prompt)

        # Store mode on project for downstream use
        if mode:
            await self.db.projects.update_one(
                {"id": self.project_id}, {"$set": {"mode": mode}}
            )

        try:
            if mode == "research":
                await self._run_research(user_prompt, stack_decision)
            elif mode == "repo_fix":
                await self._run_repo_fix(user_prompt, stack_decision)
            else:
                await self._run_build_pipeline(user_prompt, mode, stack_decision)

        except BuildCancelled as e:
            msg = str(e)
            now = _now()
            await self.db.projects.update_one(
                {"id": self.project_id},
                {"$set": {"status": "cancelled", "error": msg, "completed_at": now, "updated_at": now}},
            )
            await self.emit({"type": "project_status", "data": {"status": "cancelled", "error": msg}})
            await self._record_message("system", None, msg, meta={"cancelled": True})
        except Exception as e:
            err = str(e)
            await self._fail_project("pipeline", err)
            await self._record_message("system", None, f"Build failed: {err}", meta={"error": err})
            raise

    async def _run_build_pipeline(self, user_prompt: str, mode: str,
                                   stack_decision: dict | None) -> None:
        """Standard Scout → Architect → Coder → Reviewer pipeline."""
        sd = stack_decision or {}

        # 1) Scout
        await self._check_cancel()
        shared_ctx = await self._shared_context()
        scout_user = json.dumps({
            "prompt": user_prompt,
            "mode": mode,
            "stack": sd.get("stack", {}),
            "shared_context": shared_ctx,
        })
        scout = await self._run_agent("scout", SCOUT_PROMPT, scout_user)
        await self._check_cancel()
        scout_data = scout["data"]
        await self.fs.write("requirements.md", scout_data.get("requirements_md", ""), "markdown")
        await self.emit({"type": "file_written", "data": {"path": "requirements.md"}})
        await self._record_message(
            "agent", "scout",
            f"**Brief:** {scout_data.get('summary', '')}\n\n"
            f"**Audience:** {scout_data.get('audience', '')}\n\n"
            f"**Core features:**\n" + "\n".join(f"- {f}" for f in scout_data.get("core_features", [])),
            meta={"model": scout["model_label"]},
        )

        # 2) Architect
        await self._check_cancel()
        arch_input = json.dumps({
            "requirements": scout_data,
            "mode": mode,
            "stack_decision": sd,
            "required_files": sd.get("required_files", []),
            "shared_context": shared_ctx,
        }, indent=2)
        arch = await self._run_agent("architect", ARCHITECT_PROMPT, arch_input)
        await self._check_cancel()
        arch_data = arch["data"]
        await self.fs.write("tech_stack.json", json.dumps(arch_data, indent=2), "json")
        await self.emit({"type": "file_written", "data": {"path": "tech_stack.json"}})
        await self._record_message(
            "agent", "architect",
            f"**Stack:** {arch_data.get('tech_stack', {}).get('frontend', '?')}"
            f" + {arch_data.get('tech_stack', {}).get('styling', '?')}\n\n"
            f"**Files planned:** {len(arch_data.get('file_plan', []))}",
            meta={"model": arch["model_label"]},
        )

        # 3) Coder
        await self._check_cancel()
        coder_input = json.dumps({
            "requirements": scout_data,
            "plan": arch_data,
            "mode": mode,
            "stack_decision": sd,
            "required_files": sd.get("required_files", []),
            "safety_notes": sd.get("safety_notes", []),
            "media_strategy": shared_ctx.get("media_strategy", {}),
            "shared_context": shared_ctx,
        }, indent=2)
        coder = await self._run_agent("coder", CODER_PROMPT, coder_input)
        await self._check_cancel()
        coder_data = coder["data"]
        generated_files = coder_data.get("files", [])

        # Verify coder produced actual app files
        if not generated_files:
            err = "Coder produced zero app files. Build cannot be marked ready."
            await self._record_event("coder", "failed", err)
            await self._record_event("reviewer", "skipped",
                                     "Reviewer skipped because Coder produced no files.")
            await self._fail_project("coder", err)
            await self._record_message("system", None, err, meta={"error": err})
            return

        for f in generated_files:
            await self.fs.write(f["path"], f["content"], f.get("language", "text"))
            await self.emit({"type": "file_written", "data": {"path": f["path"]}})
        await self._record_message(
            "agent", "coder",
            coder_data.get("summary", "Files generated."),
            meta={"model": coder["model_label"], "files": [f["path"] for f in generated_files]},
        )

        # 4) Reviewer
        await self._check_cancel()
        current_files = await self.fs.list_full()
        review_input = json.dumps({
            "mode": mode,
            "required_files": sd.get("required_files", []),
            "files": [{"path": f["path"], "content": f["content"]} for f in current_files
                      if f["path"] not in _META_FILES],
            "shared_context": shared_ctx,
        }, indent=2)
        rev = await self._run_agent("reviewer", REVIEWER_PROMPT, review_input)
        await self._check_cancel()
        rev_data = rev["data"]
        for f in rev_data.get("patched_files", []):
            await self.fs.write(f["path"], f["content"], f.get("language", "text"))
            await self.emit({"type": "file_written", "data": {"path": f["path"]}})
        await self._record_message(
            "agent", "reviewer",
            f"**Verdict:** {rev_data.get('verdict', 'pass')}\n\n"
            + (("**Issues:**\n" + "\n".join(f"- {i}" for i in rev_data.get("issues", [])))
               if rev_data.get("issues") else "_No issues found._"),
            meta={"model": rev["model_label"], "patched": [f["path"] for f in rev_data.get("patched_files", [])]},
        )

        # 5) Validate required files
        final_files = await self.fs.list_full()
        final_paths = {f["path"] for f in final_files}
        required = sd.get("required_files", [])
        missing = [r for r in required if r not in final_paths]
        present = [r for r in required if r in final_paths]
        validation_state = {
            "status": "passed" if not missing else "failed",
            "required_files_present": present,
            "required_files_missing": missing,
            "warnings": rev_data.get("issues", []),
            "errors": [f"Missing required file: {m}" for m in missing] if missing else [],
        }
        await self.db.projects.update_one(
            {"id": self.project_id},
            {"$set": {"validation_state": validation_state, "repair_attempts": self._repair_attempts}},
        )
        await self.emit({"type": "validation_state", "data": validation_state})

        # Readiness check: modes that output HTML need app files
        if mode in _REQUIRES_APP_FILES_MODES and not _has_app_files(final_files):
            err = "Build completed but no app files were generated."
            await self._fail_project("coder", err)
            await self._record_message("system", None, err, meta={"error": err})
            return

        # For no-preview modes, require at least README.md
        if mode in _NO_PREVIEW_MODES:
            has_readme = any(f["path"] == "README.md" for f in final_files)
            if not has_readme:
                err = "Build completed but required README.md was not generated."
                await self._fail_project("coder", err)
                await self._record_message("system", None, err, meta={"error": err})
                return

        preview_strategy = sd.get("preview_strategy", "iframe")
        await self._set_status("ready", {
            "completed_at": _now(),
            "preview_strategy": preview_strategy,
        })
        await self.emit({"type": "build_complete", "data": {"preview_strategy": preview_strategy}})

    async def _run_research(self, user_prompt: str, stack_decision: dict | None) -> None:
        """Research mode: produce a research brief and build prompt, no code files."""
        await self._check_cancel()
        await self._record_event("scout", "started", "Scout engaged in research mode.")
        research = await self._run_agent("research", RESEARCH_PROMPT, user_prompt)
        await self._check_cancel()
        rd = research["data"]
        # Store research brief as requirements.md
        brief = rd.get("research_brief", "No research brief returned.")
        build_prompt = rd.get("build_prompt", "")
        await self.fs.write("requirements.md", brief, "markdown")
        await self.emit({"type": "file_written", "data": {"path": "requirements.md"}})
        # Store build prompt as a message
        await self._record_message(
            "agent", "scout",
            f"**Research Complete**\n\n{rd.get('summary', '')}\n\n"
            f"**Recommended mode:** {rd.get('recommended_mode', 'web_app')}\n\n"
            f"**Build prompt ready:**\n```\n{build_prompt}\n```",
            meta={"model": research["model_label"],
                  "recommended_mode": rd.get("recommended_mode"),
                  "build_prompt": build_prompt},
        )
        await self._set_status("ready", {
            "completed_at": _now(),
            "preview_strategy": "brief_only",
        })
        await self.emit({"type": "build_complete", "data": {"preview_strategy": "brief_only"}})

    async def _run_repo_fix(self, user_prompt: str, stack_decision: dict | None) -> None:
        """Repo fix mode: targeted edits to an imported repo."""
        await self._check_cancel()
        current_files = await self.fs.list_full()
        app_files = [f for f in current_files if f["path"] not in _META_FILES]
        if not app_files:
            err = "No imported repo files found. Import a GitHub repo before requesting fixes."
            await self._fail_project("scout", err)
            await self._record_message("system", None, err, meta={"error": err})
            return
        await self._record_event("coder", "started", "Coder engaged in repo-fix mode.")
        fix_input = json.dumps({
            "request": user_prompt,
            "files": [{"path": f["path"], "content": f["content"]} for f in app_files],
        }, indent=2)
        fix = await self._run_agent("repo_fix", REPO_FIX_PROMPT, fix_input)
        await self._check_cancel()
        fix_data = fix["data"]
        for f in fix_data.get("files", []):
            await self.fs.write(f["path"], f["content"], f.get("language", "text"))
            await self.emit({"type": "file_written", "data": {"path": f["path"]}})
        await self._record_message(
            "agent", "coder",
            fix_data.get("summary", "Repo updated."),
            meta={"model": fix["model_label"],
                  "changes": fix_data.get("changes_made", []),
                  "files": [f["path"] for f in fix_data.get("files", [])]},
        )
        await self._set_status("ready", {
            "completed_at": _now(),
            "preview_strategy": "repo_structure",
        })
        await self.emit({"type": "build_complete", "data": {"preview_strategy": "repo_structure"}})


    # ---------- iteration ----------

    async def run_iteration(self, user_prompt: str) -> None:
        await self._set_status("running")
        await self._record_message("user", None, user_prompt)
        try:
            current_files = await self.fs.list_full()
            app_files = [f for f in current_files if f["path"] not in _META_FILES]

            # Guard: do not iterate when no app files exist
            if not app_files:
                msg = (
                    "The build failed before app files were generated. "
                    "Retry Coder or restart the build before sending iteration requests."
                )
                await self._set_status("failed", {"error": msg})
                await self._record_message("system", None, msg, meta={"iteration_blocked": True})
                return

            payload: dict[str, Any] = {
                "request": user_prompt,
                "files": [{"path": f["path"], "content": f["content"]} for f in app_files],
            }
            iter_res = await self._run_agent("iteration", ITERATION_PROMPT, json.dumps(payload, indent=2))
            data = iter_res["data"]
            for f in data.get("files", []):
                await self.fs.write(f["path"], f["content"], f.get("language", "text"))
                await self.emit({"type": "file_written", "data": {"path": f["path"]}})
            await self._record_message(
                "agent", "iteration",
                data.get("summary", "Updated."),
                meta={"model": iter_res["model_label"],
                      "files": [f["path"] for f in data.get("files", [])]},
            )
            await self._set_status("ready")
            await self.emit({"type": "build_complete", "data": {}})
        except Exception as e:
            err = str(e)
            await self._fail_project("iteration", err)
            await self._record_message("system", None, f"Iteration failed: {err}", meta={"error": err})
            raise

    # ---------- retry ----------

    async def run_retry(self, target: str, quality_tier: str | None = None) -> None:
        """Retry a specific agent or the full pipeline.

        target: "coder" | "reviewer" | "pipeline"
        """
        await self._set_status("running")
        try:
            if target == "pipeline":
                proj = await self.db.projects.find_one(
                    {"id": self.project_id}, {"_id": 0, "prompt": 1, "mode": 1}
                )
                if not proj or not proj.get("prompt"):
                    raise ValueError("Cannot retry: original project prompt is missing.")
                # Clear cancel flag for retry
                await self.db.projects.update_one(
                    {"id": self.project_id},
                    {"$set": {"cancel_requested": False, "failed_agent": None, "error": None}},
                )
                await self.run_full_build(proj["prompt"], mode=proj.get("mode", "web_app"))
                return

            if target == "coder":
                # Re-run coder using stored scout/architect outputs
                req_file = await self.fs.read("requirements.md")
                stack_file = await self.fs.read("tech_stack.json")
                if not req_file or not stack_file:
                    raise ValueError(
                        "Cannot retry Coder: Scout or Architect output is missing. "
                        "Use 'Restart Build' to run the full pipeline again."
                    )
                scout_data = {"requirements_md": req_file["content"]}
                try:
                    arch_data = json.loads(stack_file["content"])
                except Exception:
                    arch_data = {}
                await self._record_event("coder", "retry", "Retrying Coder with stored context.")
                coder_input = json.dumps({"requirements": scout_data, "plan": arch_data}, indent=2)
                coder = await self._run_agent("coder", CODER_PROMPT, coder_input)
                coder_data = coder["data"]
                generated_files = coder_data.get("files", [])
                if not generated_files:
                    err = "Coder retry produced zero app files."
                    await self._fail_project("coder", err)
                    await self._record_message("system", None, err, meta={"error": err})
                    return
                for f in generated_files:
                    await self.fs.write(f["path"], f["content"], f.get("language", "text"))
                    await self.emit({"type": "file_written", "data": {"path": f["path"]}})
                await self._record_message(
                    "agent", "coder",
                    coder_data.get("summary", "Files regenerated."),
                    meta={"model": coder["model_label"],
                          "files": [f["path"] for f in generated_files],
                          "retry": True},
                )
                await self._set_status("ready", {"completed_at": _now(), "failed_agent": None, "error": None})
                await self.emit({"type": "build_complete", "data": {}})
                return

            if target == "reviewer":
                current_files = await self.fs.list_full()
                app_files = [f for f in current_files if f["path"] not in _META_FILES]
                if not app_files:
                    raise ValueError(
                        "Cannot retry Reviewer: no app files exist. Retry Coder first."
                    )
                await self._record_event("reviewer", "retry", "Retrying Reviewer.")
                review_input = json.dumps(
                    {"files": [{"path": f["path"], "content": f["content"]} for f in app_files]},
                    indent=2,
                )
                rev = await self._run_agent("reviewer", REVIEWER_PROMPT, review_input)
                rev_data = rev["data"]
                for f in rev_data.get("patched_files", []):
                    await self.fs.write(f["path"], f["content"], f.get("language", "text"))
                    await self.emit({"type": "file_written", "data": {"path": f["path"]}})
                await self._record_message(
                    "agent", "reviewer",
                    f"**Verdict:** {rev_data.get('verdict', 'pass')}\n\n"
                    + (("**Issues:**\n" + "\n".join(f"- {i}" for i in rev_data.get("issues", [])))
                       if rev_data.get("issues") else "_No issues found._"),
                    meta={"model": rev["model_label"],
                          "patched": [f["path"] for f in rev_data.get("patched_files", [])],
                          "retry": True},
                )
                await self._set_status("ready", {"completed_at": _now(), "failed_agent": None, "error": None})
                await self.emit({"type": "build_complete", "data": {}})
                return

            raise ValueError(f"Unknown retry target: {target}")

        except (BuildCancelled, ValueError):
            raise
        except Exception as e:
            err = str(e)
            await self._fail_project(target, err)
            await self._record_message("system", None, f"Retry failed: {err}", meta={"error": err})
            raise
