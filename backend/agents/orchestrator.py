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


# Extension → language mapping for AMARKTAI block parsing
_EXT_LANG: dict[str, str] = {
    "html": "html", "htm": "html",
    "css": "css",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "json": "json",
    "md": "markdown", "markdown": "markdown",
    "py": "python",
    "sh": "bash", "bash": "bash",
    "yaml": "yaml", "yml": "yaml",
    "toml": "toml",
    "env": "dotenv",
    "txt": "text",
    "dockerfile": "dockerfile",
}

# Pre-compiled patterns for AMARKTAI block parsing
_AMARKTAI_FILE_PAT = re.compile(
    r"===AMARKTAI_FILE\[(?P<path>[^\]]+)\]===\n(?P<content>.*?)===END_AMARKTAI_FILE\[(?P=path)\]===",
    re.DOTALL,
)
_AMARKTAI_SUMMARY_PAT = re.compile(
    r"===AMARKTAI_SUMMARY===\n(?P<s>.*?)(?:\n===END_AMARKTAI_SUMMARY===|$)",
    re.DOTALL,
)


def _parse_amarktai_blocks(text: str) -> dict:
    """Parse AMARKTAI file block format output from Coder/Iteration/RepoFix agents.

    Expected format::

        ===AMARKTAI_FILE[index.html]===
        ...verbatim file content...
        ===END_AMARKTAI_FILE[index.html]===

        ===AMARKTAI_SUMMARY===
        2-3 line summary.
        ===END_AMARKTAI_SUMMARY===

    Returns a dict compatible with the old JSON protocol::

        {"files": [{"path": ..., "language": ..., "content": ...}], "summary": ...}
    """
    files = []
    for m in _AMARKTAI_FILE_PAT.finditer(text):
        path = m.group("path").strip()
        content = m.group("content")
        # Preserve content verbatim.  The regex already excludes the newline
        # immediately after the opening delimiter; any trailing newlines in the
        # captured group are part of the file's actual content (e.g. the
        # conventional POSIX trailing newline) and must not be stripped.
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        language = _EXT_LANG.get(ext, "text")
        files.append({"path": path, "language": language, "content": content})

    summary_m = _AMARKTAI_SUMMARY_PAT.search(text)
    summary = summary_m.group("s").strip() if summary_m else ""

    return {"files": files, "summary": summary}


def _has_app_files(files: list[dict]) -> bool:
    """Return True if there are generated app files (not just metadata)."""
    return any(f["path"] not in _META_FILES for f in files)


def _has_preview_entry(files: list[dict]) -> bool:
    """Return True if the project has a previewable entry file."""
    return any(f["path"] in _PREVIEW_ENTRY_FILES for f in files)


# Pre-compiled patterns for form accessibility validation
_FORM_INPUT_PAT = re.compile(
    r"<(input|textarea|select)[^>]*>",
    re.IGNORECASE,
)
_HAS_ID_PAT = re.compile(r'\bid=["\'][^"\']+["\']', re.IGNORECASE)
_HAS_NAME_PAT = re.compile(r'\bname=["\'][^"\']+["\']', re.IGNORECASE)
_HAS_ARIA_LABEL_PAT = re.compile(r'\baria-label=["\'][^"\']+["\']', re.IGNORECASE)
_HAS_TYPE_HIDDEN_PAT = re.compile(r'\btype=["\']hidden["\']', re.IGNORECASE)
_HAS_TYPE_SUBMIT_PAT = re.compile(r'\btype=["\']submit["\']', re.IGNORECASE)
_HAS_TYPE_BUTTON_PAT = re.compile(r'\btype=["\']button["\']', re.IGNORECASE)
_LABEL_FOR_PAT = re.compile(r'<label[^>]*\bfor=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)


def _validate_form_accessibility(html_content: str) -> list[str]:
    """Return a list of form accessibility issues found in HTML content.

    Checks:
    - Every <input>/<textarea>/<select> has id and name (unless hidden/submit/button).
    - Every such field has a <label for="..."> matching its id, or an aria-label.
    Only runs when form fields are present (non-form pages are not blocked).
    """
    issues: list[str] = []
    inputs = _FORM_INPUT_PAT.findall(html_content)
    if not inputs:
        return issues  # No form fields — nothing to check

    # Collect all label for="" values
    label_fors = set(_LABEL_FOR_PAT.findall(html_content))

    for m in _FORM_INPUT_PAT.finditer(html_content):
        tag_html = m.group(0)
        tag_name = m.group(1).lower()

        # Skip hidden, submit, and button inputs — they don't need labels
        if _HAS_TYPE_HIDDEN_PAT.search(tag_html):
            continue
        if tag_name == "input" and (
            _HAS_TYPE_SUBMIT_PAT.search(tag_html) or _HAS_TYPE_BUTTON_PAT.search(tag_html)
        ):
            continue

        has_id = _HAS_ID_PAT.search(tag_html)
        has_name = _HAS_NAME_PAT.search(tag_html)
        has_aria = _HAS_ARIA_LABEL_PAT.search(tag_html)

        if not has_id:
            issues.append(f"Form field <{tag_name}> is missing id attribute: {tag_html[:80]}")
        if not has_name:
            issues.append(f"Form field <{tag_name}> is missing name attribute: {tag_html[:80]}")
        if has_id and not has_aria:
            # Extract id value and check for matching label
            id_match = re.search(r'\bid=["\']([^"\']+)["\']', tag_html, re.IGNORECASE)
            if id_match:
                field_id = id_match.group(1)
                if field_id not in label_fors:
                    issues.append(
                        f"Form field id=\"{field_id}\" has no associated <label for=\"{field_id}\"> "
                        f"and no aria-label attribute"
                    )

    return issues


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

    async def _run_agent_blocks(self, agent: str, system: str, user: str) -> dict:
        """Like _run_agent but parses AMARKTAI file blocks instead of JSON.

        Tries AMARKTAI block format first. Falls back to JSON parsing when no
        blocks are found so that test mocks returning the old JSON format still
        work without modification.

        Returns the same ``{"data": {...}, "model_label": ...}`` dict as
        ``_run_agent``, where ``data`` contains ``{"files": [...], "summary": "..."}``.
        """
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

        raw = result["text"]

        # Try AMARKTAI block parsing first
        data = _parse_amarktai_blocks(raw)
        if data["files"]:
            await self._record_event(
                agent, "completed",
                f"{agent.title()} done (AMARKTAI block format).",
                meta={"model": result["model_label"]},
            )
            return {"data": data, "model_label": result["model_label"]}

        # Fallback: JSON parsing (backward-compat / model did not follow new format)
        await self._record_event(
            agent, "thinking",
            "No AMARKTAI file blocks detected; attempting JSON fallback.",
        )
        try:
            data = _parse_json(raw)
        except Exception as e:
            parse_err = str(e)
            await self._record_event(agent, "failed",
                                     f"JSON fallback parse failed: {parse_err}",
                                     meta={"raw": raw[:2000]})
            try:
                data = await self._repair_json(agent, raw, parse_err)
                await self._record_event(agent, "repaired",
                                         f"JSON repair succeeded for {agent}.")
            except Exception as repair_err:
                err_msg = (
                    f"{agent.title()} returned neither valid AMARKTAI file blocks "
                    f"nor valid JSON, and automatic repair failed."
                )
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

    # ---------- repair limit by tier ----------

    _REPAIR_LIMITS: dict[str, int] = {"cheap": 1, "balanced": 2, "premium": 3}

    async def _repair_limit(self) -> int:
        """Return the max allowed file-content repair attempts for the current quality tier."""
        proj = await self._load_project()
        tier = proj.get("quality_tier", "balanced")
        return self._REPAIR_LIMITS.get(tier, 2)

    async def _emit_validation_event(self, event_type: str, detail: str, meta: dict | None = None) -> None:
        """Emit a validation lifecycle event to the WebSocket hub and record as agent_event."""
        evt = {
            "id": str(uuid.uuid4()),
            "project_id": self.project_id,
            "agent": "validator",
            "status": event_type,
            "detail": detail,
            "meta": meta or {},
            "created_at": _now(),
        }
        await self.db.agent_events.insert_one(dict(evt))
        evt.pop("_id", None)
        await self.emit({"type": "agent_event", "data": evt})
        await self.emit({"type": event_type, "data": {"detail": detail, **(meta or {})}})

    async def _run_build_pipeline(self, user_prompt: str, mode: str,
                                   stack_decision: dict | None) -> None:
        """Standard Scout → Architect → Coder → Reviewer → Validate → Repair loop pipeline."""
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
        # Include enriched scout fields in the message if present
        make_better = scout_data.get("make_it_better", [])
        pain_points = scout_data.get("pain_points", [])
        scout_msg = (
            f"**Brief:** {scout_data.get('summary', '')}\n\n"
            f"**Audience:** {scout_data.get('audience', '')}\n\n"
            f"**Core features:**\n" + "\n".join(f"- {f}" for f in scout_data.get("core_features", []))
        )
        if pain_points:
            scout_msg += "\n\n**Pain points:**\n" + "\n".join(f"- {p}" for p in pain_points)
        if make_better:
            scout_msg += "\n\n**Make it better:**\n" + "\n".join(f"- {m}" for m in make_better)
        await self._record_message(
            "agent", "scout", scout_msg,
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
        coder = await self._run_agent_blocks("coder", CODER_PROMPT, coder_input)
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

        # 4) Reviewer (first pass) — non-fatal: if the Reviewer returns invalid JSON and
        #    repair also fails, record the event but continue to deterministic validation.
        #    The project is only failed if the required files are actually missing.
        await self._check_cancel()
        current_files = await self.fs.list_full()
        review_input = json.dumps({
            "mode": mode,
            "required_files": sd.get("required_files", []),
            "files": [{"path": f["path"], "content": f["content"]} for f in current_files
                      if f["path"] not in _META_FILES],
            "shared_context": shared_ctx,
        }, indent=2)
        review_issues: list[str] = []
        try:
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
            review_issues = rev_data.get("issues", [])
        except (ValueError, json.JSONDecodeError, Exception) as reviewer_err:
            # Reviewer failure is non-fatal: record and proceed to deterministic validation.
            err_detail = f"Reviewer returned invalid output; skipping reviewer patches. Proceeding to validation. Detail: {reviewer_err}"
            await self._record_event("reviewer", "failed", err_detail,
                                     meta={"reviewer_error": str(reviewer_err)})
            await self._record_message("system", None, err_detail,
                                       meta={"reviewer_nonfatal": True})

        # 5) Validation + bounded repair loop
        required = sd.get("required_files", [])
        max_repairs = await self._repair_limit()

        await self._emit_validation_event(
            "validation_started",
            f"Validating {len(required)} required files for {mode} mode.",
            {"required_files": required},
        )

        for repair_pass in range(max_repairs + 1):
            await self._check_cancel()
            final_files = await self.fs.list_full()
            final_paths = {f["path"] for f in final_files}
            missing = [r for r in required if r not in final_paths]
            present = [r for r in required if r in final_paths]

            # Run form accessibility check on HTML files (warnings only — added to review_issues)
            if repair_pass == 0:
                for ff in final_files:
                    if ff["path"].endswith((".html", ".htm")):
                        acc_issues = _validate_form_accessibility(ff["content"])
                        for ai in acc_issues:
                            if ai not in review_issues:
                                review_issues.append(ai)

            validation_state = {
                "status": "passed" if not missing else "failed",
                "required_files_present": present,
                "required_files_missing": missing,
                "warnings": review_issues,
                "errors": [f"Missing required file: {m}" for m in missing] if missing else [],
                "repair_pass": repair_pass,
            }
            await self.db.projects.update_one(
                {"id": self.project_id},
                {"$set": {"validation_state": validation_state, "repair_attempts": repair_pass}},
            )
            await self.emit({"type": "validation_state", "data": validation_state})

            if not missing:
                await self._emit_validation_event(
                    "validation_passed",
                    "All required files present. Validation passed." if repair_pass == 0
                    else f"Validation passed after {repair_pass} repair attempt(s).",
                    {"repair_pass": repair_pass},
                )
                break

            # Validation failed — attempt repair if within limit
            await self._emit_validation_event(
                "validation_failed",
                f"Missing required files: {', '.join(missing)}",
                {"missing": missing, "repair_pass": repair_pass},
            )

            if repair_pass >= max_repairs:
                # Exhausted all repair attempts
                await self._emit_validation_event(
                    "validation_exhausted",
                    f"Repair limit reached ({max_repairs} attempt(s)). "
                    f"Still missing: {', '.join(missing)}",
                    {"missing": missing, "max_repairs": max_repairs},
                )
                err = (
                    f"Build completed but required files are still missing after {repair_pass} "
                    f"repair attempt(s): {', '.join(missing)}"
                )
                await self._fail_project("validator", err)
                await self._record_message("system", None, err, meta={"error": err})
                return

            # Run a repair pass
            self._repair_attempts = repair_pass + 1
            await self._emit_validation_event(
                "repair_started",
                f"Repair attempt {repair_pass + 1}/{max_repairs}: "
                f"asking Reviewer to add missing files: {', '.join(missing)}",
                {"missing": missing, "attempt": repair_pass + 1},
            )
            await self._check_cancel()
            repair_files = await self.fs.list_full()
            repair_input = json.dumps({
                "mode": mode,
                "required_files": required,
                "missing_files": missing,
                "repair_attempt": repair_pass + 1,
                "files": [{"path": f["path"], "content": f["content"]} for f in repair_files
                          if f["path"] not in _META_FILES],
                "shared_context": shared_ctx,
            }, indent=2)
            repair_prompt = (
                REVIEWER_PROMPT
                + f"\n\nCRITICAL: The following required files are MISSING and MUST be generated now: "
                + json.dumps(missing)
                + "\nYou MUST include all missing files in patched_files with complete content."
            )
            try:
                repair_res = await self._run_agent("reviewer", repair_prompt, repair_input)
                repair_data = repair_res["data"]
                patched = repair_data.get("patched_files", [])
                for f in patched:
                    await self.fs.write(f["path"], f["content"], f.get("language", "text"))
                    await self.emit({"type": "file_written", "data": {"path": f["path"]}})
                await self._emit_validation_event(
                    "repair_applied",
                    f"Repair applied {len(patched)} file(s).",
                    {"patched": [f["path"] for f in patched]},
                )
                review_issues = repair_data.get("issues", review_issues)
            except Exception as repair_err:
                await self._emit_validation_event(
                    "repair_failed",
                    f"Repair attempt {repair_pass + 1} failed: {repair_err}",
                    {"error": str(repair_err)},
                )
                # Continue to next iteration — will hit exhaustion check

        # Post-validation readiness checks
        final_files = await self.fs.list_full()

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

        # Compose a rich research message with all Phase 4 fields
        msg_parts = [f"**Research Complete**\n\n{rd.get('summary', '')}"]
        if rd.get("target_audience"):
            msg_parts.append(f"\n**Target audience:** {rd['target_audience']}")
        if rd.get("user_pain_points"):
            msg_parts.append("\n**User pain points:**\n" + "\n".join(f"- {p}" for p in rd["user_pain_points"]))
        if rd.get("competing_approaches"):
            msg_parts.append(f"\n**Competing approaches:** {rd['competing_approaches']}")
        if rd.get("mvp_recommendation"):
            msg_parts.append(f"\n**MVP recommendation:** {rd['mvp_recommendation']}")
        if rd.get("make_it_better"):
            msg_parts.append("\n**Make it better:**\n" + "\n".join(f"- {m}" for m in rd["make_it_better"]))
        if rd.get("monetization_ideas"):
            msg_parts.append("\n**Monetization ideas:**\n" + "\n".join(f"- {m}" for m in rd["monetization_ideas"]))
        if rd.get("risk_assumption_list"):
            msg_parts.append("\n**Risks & assumptions:**\n" + "\n".join(f"- {r}" for r in rd["risk_assumption_list"]))
        if rd.get("recommended_stack"):
            msg_parts.append(f"\n**Recommended stack:** {rd['recommended_stack']}")
        msg_parts.append(
            f"\n**Recommended mode:** {rd.get('recommended_mode', 'web_app')}"
            f" · **Recommended tier:** {rd.get('recommended_tier', 'balanced')}"
        )
        if build_prompt:
            msg_parts.append(f"\n**Build prompt ready:**\n```\n{build_prompt}\n```")

        await self._record_message(
            "agent", "scout",
            "\n".join(msg_parts),
            meta={"model": research["model_label"],
                  "recommended_mode": rd.get("recommended_mode"),
                  "recommended_tier": rd.get("recommended_tier"),
                  "recommended_stack": rd.get("recommended_stack"),
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
        fix = await self._run_agent_blocks("repo_fix", REPO_FIX_PROMPT, fix_input)
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
            iter_res = await self._run_agent_blocks("iteration", ITERATION_PROMPT, json.dumps(payload, indent=2))
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

        target: "coder" | "reviewer" | "repair" | "pipeline"
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
                coder = await self._run_agent_blocks("coder", CODER_PROMPT, coder_input)
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

            if target in ("reviewer", "repair"):
                # "repair" is an alias for reviewer retry — re-runs Reviewer to patch/fix missing files
                current_files = await self.fs.list_full()
                app_files = [f for f in current_files if f["path"] not in _META_FILES]
                if not app_files:
                    raise ValueError(
                        "Cannot retry Reviewer/Repair: no app files exist. Retry Coder first."
                    )
                label = "Repair" if target == "repair" else "Reviewer"
                await self._record_event("reviewer", "retry", f"Retrying {label}.")
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
