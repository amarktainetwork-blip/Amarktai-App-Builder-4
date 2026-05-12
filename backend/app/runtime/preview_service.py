"""Runtime preview service for Amarktai App Builder — Phase 2C.

Wraps the sandbox manager to provide:
- Honest preview results (never fakes success)
- Structured build logs
- Stack detection output
- Repair trigger on failure

This module exposes a high-level ``PreviewService`` class that coordinates
the sandbox lifecycle and surfaces real build outcomes to the API layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

# Import from the existing sandbox manager location
from runtime.sandbox_manager import SandboxManager, SandboxResult, detect_stack

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PreviewService:
    """High-level preview coordination service.

    Provides a single ``build_preview`` coroutine that:
    1. Detects the project stack.
    2. Runs the sandbox build.
    3. Returns a structured ``PreviewResult`` — never a fake success.
    4. Surfaces actionable repair suggestions when the build fails.
    """

    async def build_preview(
        self,
        files: list[dict],
        *,
        stack_hint: str | None = None,
        emit=None,
    ) -> dict:
        """Build a preview for the given file set.

        Args:
            files:      Project files as ``[{path, content}]``.
            stack_hint: Optional stack override (e.g. ``"vite"``).
            emit:       Optional async callable to stream log events to the
                        WebSocket hub.  Receives ``{"type": str, "data": dict}``.

        Returns:
            A ``PreviewResult`` dict with keys:
            - ``success`` (bool)  — True only if the build actually worked.
            - ``stack`` (str)     — detected or hinted stack.
            - ``preview_html`` (str|None) — for static stacks only.
            - ``preview_url`` (str|None)  — URL when a dev server is running.
            - ``runtime_status`` (str)    — idle|installing|building|running|error.
            - ``install_ok`` (bool)
            - ``build_ok`` (bool)
            - ``logs`` (list[str])        — raw build log lines.
            - ``errors`` (list[dict])     — structured error entries.
            - ``repair_needed`` (bool)    — True when build failed and repair may help.
            - ``repair_hints`` (list[str]) — actionable suggestions.
            - ``build_at`` (str)          — ISO timestamp.
        """
        async def _maybe_emit(payload: dict) -> None:
            if emit:
                try:
                    await emit(payload)
                except Exception:
                    pass

        await _maybe_emit({"type": "build_log", "data": {"line": "[preview] Starting build…", "ts": _now()}})

        detected = stack_hint or detect_stack(files)
        await _maybe_emit({"type": "build_log", "data": {"line": f"[preview] Stack detected: {detected}", "ts": _now()}})

        async with SandboxManager() as mgr:
            result: SandboxResult = await mgr.run_preview(files, stack_hint=stack_hint)

        # Stream all captured log lines
        for line in result.logs:
            await _maybe_emit({"type": "build_log", "data": {"line": line, "ts": _now()}})

        repair_needed = not result.success
        repair_hints = self._repair_hints(result)

        if result.success:
            await _maybe_emit({"type": "preview_ready", "data": {"stack": result.stack, "ts": _now()}})
        else:
            await _maybe_emit({
                "type": "preview_failed",
                "data": {
                    "stack": result.stack,
                    "errors": [{"category": e.category, "repairTask": e.repair_task} for e in result.errors],
                    "logs": result.logs[-50:],
                    "ts": _now(),
                },
            })

        return {
            "success": result.success,
            "stack": result.stack,
            "preview_html": result.preview_html,
            "preview_url": result.preview_url,
            "runtime_status": result.runtime_status,
            "install_ok": result.install_ok,
            "build_ok": result.build_ok,
            "logs": result.logs,
            "errors": [
                {"category": e.category, "repairTask": e.repair_task}
                for e in result.errors
            ],
            "repair_needed": repair_needed,
            "repair_hints": repair_hints,
            "build_at": _now(),
        }

    @staticmethod
    def _repair_hints(result: SandboxResult) -> list[str]:
        """Derive actionable repair hints from a failed SandboxResult."""
        hints: list[str] = []
        for err in result.errors:
            task = err.repair_task
            if task and task not in hints:
                hints.append(task)
        if not result.install_ok:
            hints.append("Check package.json / requirements.txt for typos or incompatible versions.")
        if result.install_ok and not result.build_ok:
            hints.append("Build failed after install — check for TypeScript errors or missing imports.")
        if not hints:
            hints.append("Inspect build logs above for the root cause.")
        return hints

    def detect_stack(self, files: list[dict], stack_hint: str | None = None) -> str:
        """Return the detected stack for the given file set."""
        return stack_hint or detect_stack(files)
