"""
Multi-agent orchestrator: Scout → Architect → Coder → Reviewer.

The orchestrator reads/writes everything through MongoDB and emits real-time events to a
WebSocket hub so the dashboard can render the timeline live.
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
    REVIEWER_PROMPT,
    SCOUT_PROMPT,
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


EmitFn = Callable[[dict], Awaitable[None]]


class Orchestrator:
    def __init__(self, db, provider: GenXProvider, project_id: str, emit: EmitFn):
        self.db = db
        self.provider = provider
        self.project_id = project_id
        self.fs = ProjectFS(db, project_id)
        self.emit = emit

    # ---------- shared helpers ----------

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
            "status": status,  # "started" | "thinking" | "completed" | "failed"
            "detail": detail,
            "meta": meta or {},
            "created_at": _now(),
        }
        await self.db.agent_events.insert_one(dict(evt))
        evt.pop("_id", None)
        await self.emit({"type": "agent_event", "data": evt})
        return evt

    async def _set_status(self, status: str) -> None:
        await self.db.projects.update_one(
            {"id": self.project_id}, {"$set": {"status": status, "updated_at": _now()}}
        )
        await self.emit({"type": "project_status", "data": {"status": status}})

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

    async def _run_agent(self, agent: str, system: str, user: str) -> dict:
        await self._record_event(agent, "started", f"{agent.title()} engaged.")
        await self._record_event(agent, "thinking", "Calling model...")
        result = await self.provider.complete(
            agent=agent, system_prompt=system, user_message=user,
            session_id=f"{self.project_id}:{agent}",
        )
        await self._track_usage(result["model_label"], len(system) + len(user), len(result["text"]))
        try:
            data = _parse_json(result["text"])
        except Exception as e:
            await self._record_event(agent, "failed", f"Could not parse JSON: {e}",
                                     meta={"raw": result["text"][:2000]})
            raise
        await self._record_event(agent, "completed", f"{agent.title()} done.",
                                 meta={"model": result["model_label"]})
        return {"data": data, "model_label": result["model_label"]}

    # ---------- full build pipeline ----------

    async def run_full_build(self, user_prompt: str) -> None:
        await self._set_status("running")
        await self._record_message("user", None, user_prompt)
        try:
            # 1) Scout
            scout = await self._run_agent("scout", SCOUT_PROMPT, user_prompt)
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
            arch_input = json.dumps(scout_data, indent=2)
            arch = await self._run_agent("architect", ARCHITECT_PROMPT, arch_input)
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
            coder_input = json.dumps({"requirements": scout_data, "plan": arch_data}, indent=2)
            coder = await self._run_agent("coder", CODER_PROMPT, coder_input)
            coder_data = coder["data"]
            for f in coder_data.get("files", []):
                await self.fs.write(f["path"], f["content"], f.get("language", "text"))
                await self.emit({"type": "file_written", "data": {"path": f["path"]}})
            await self._record_message(
                "agent", "coder",
                coder_data.get("summary", "Files generated."),
                meta={"model": coder["model_label"], "files": [f["path"] for f in coder_data.get("files", [])]},
            )

            # 4) Reviewer
            current_files = await self.fs.list_full()
            review_input = json.dumps(
                {"files": [{"path": f["path"], "content": f["content"]} for f in current_files
                           if f["path"] not in ("requirements.md", "tech_stack.json")]},
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
                meta={"model": rev["model_label"], "patched": [f["path"] for f in rev_data.get("patched_files", [])]},
            )
            await self._set_status("ready")
            await self.emit({"type": "build_complete", "data": {}})
        except Exception as e:
            await self._set_status("failed")
            await self._record_message("system", None, f"Build failed: {e}", meta={"error": str(e)})
            raise

    # ---------- iteration ----------

    async def run_iteration(self, user_prompt: str) -> None:
        await self._set_status("running")
        await self._record_message("user", None, user_prompt)
        try:
            current_files = await self.fs.list_full()
            payload: dict[str, Any] = {
                "request": user_prompt,
                "files": [{"path": f["path"], "content": f["content"]} for f in current_files
                          if f["path"] not in ("requirements.md", "tech_stack.json")],
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
            await self._set_status("failed")
            await self._record_message("system", None, f"Iteration failed: {e}", meta={"error": str(e)})
            raise
