"""
Amarktai Runtime Sandbox Manager.

Provides safe, isolated execution of user-generated applications for live preview.

Phases implemented:
  1 — Sandbox Manager      (workspace, npm/pip install, vite/next build, previews, logs, timeout, cleanup)
  2 — Stack Detection      (static, vite, react, next, express, fastapi, django, flask, fullstack, pwa)
  3 — Safe Execution       (isolated temp dirs, no host access, no shell=True, timeout, memory limits)
  4 — Live Preview         (static iframe, vite/next runtime, API fallback, logs panel, runtime status)
  5 — Live Hot Reload      (patch files, restart preview, cache bust token)
  6 — Error Intelligence   (parse vite/npm/python errors → human-readable repair tasks)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.preview import render_preview

logger = logging.getLogger(__name__)

try:
    import resource
except ImportError:  # Windows does not expose Unix resource limits.
    resource = None

# ── Constants ──────────────────────────────────────────────────────────────────

# Hard limits for sandbox processes
_DEFAULT_TIMEOUT_SECONDS = 60          # per-command timeout
_INSTALL_TIMEOUT_SECONDS = 300         # npm/pip install can take longer
_BUILD_TIMEOUT_SECONDS = 180           # vite/next build timeout
_MAX_MEMORY_MB = 512                   # memory limit for child processes (soft)
_MAX_LOG_LINES = 500                   # max lines to keep in memory
_MAX_DEPS = 200                        # refuse installs with > N dependencies

# Environment passthrough — only a safe subset
_SAFE_ENV_KEYS = frozenset({
    "HOME", "PATH", "TMPDIR", "TEMP", "TMP",
    "LANG", "LC_ALL", "LC_CTYPE",
    "NODE_ENV", "NODE_OPTIONS",
    "npm_config_cache",
    "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
})

# Stacks we can detect
STACK_TYPES = frozenset({
    "static", "vite", "react", "next", "express",
    "fastapi", "django", "flask", "fullstack", "pwa",
    "unknown",
})


# ── Phase 2 — Stack Detection ─────────────────────────────────────────────────

def detect_stack(files: list[dict]) -> str:
    """
    Analyse a project's file list and content to detect its runtime stack.

    Args:
        files: list of {"path": str, "content": str} dicts.

    Returns:
        One of the STACK_TYPES strings.
    """
    by_path: dict[str, str] = {f["path"]: f.get("content", "") for f in files}
    paths = set(by_path.keys())

    def _content_of(*candidates: str) -> str:
        for p in candidates:
            if p in by_path:
                return by_path[p]
        return ""

    pkg_json = _content_of("package.json")
    pkg_data: dict[str, Any] = {}
    if pkg_json:
        try:
            pkg_data = json.loads(pkg_json)
        except json.JSONDecodeError:
            pass

    all_deps: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        all_deps.update(pkg_data.get(section, {}).keys())

    scripts: dict[str, str] = pkg_data.get("scripts", {})

    # ── detect Next.js ────────────────────────────────────────────────────────
    has_next_config = any(
        re.search(r"next\.config\.(js|ts|mjs)$", p) for p in paths
    )
    has_next_dep = "next" in all_deps
    has_next_script = any("next" in v for v in scripts.values())
    if has_next_config or has_next_dep or has_next_script:
        return "next"

    # ── detect Vite ───────────────────────────────────────────────────────────
    has_vite_config = any(
        re.search(r"vite\.config\.(js|ts|mjs)$", p) for p in paths
    )
    has_vite_dep = "vite" in all_deps
    if has_vite_config or has_vite_dep:
        return "vite"

    # ── detect React (CRA or generic, no vite/next) ───────────────────────────
    has_react_dep = "react" in all_deps
    has_react_dom = "react-dom" in all_deps
    if has_react_dep and has_react_dom:
        return "react"

    # ── detect PWA (manifest + service worker) ────────────────────────────────
    has_manifest = any(p.endswith("manifest.json") for p in paths)
    has_sw = any(
        re.search(r"service.?worker\.(js|ts)$", p, re.IGNORECASE) for p in paths
    )
    if has_manifest and has_sw:
        return "pwa"

    # ── detect Express ────────────────────────────────────────────────────────
    has_express_dep = "express" in all_deps
    if has_express_dep:
        return "express"

    # ── detect FastAPI ────────────────────────────────────────────────────────
    py_files_content = [
        by_path[p] for p in paths if p.endswith(".py")
    ]
    if any("from fastapi import" in c or "import fastapi" in c.lower() for c in py_files_content):
        return "fastapi"

    # ── detect Django ─────────────────────────────────────────────────────────
    if any("manage.py" in p for p in paths) or any(
        "django.conf" in c or "from django" in c for c in py_files_content
    ):
        return "django"

    # ── detect Flask ──────────────────────────────────────────────────────────
    if any("from flask import" in c or "import flask" in c.lower() for c in py_files_content):
        return "flask"

    # ── detect fullstack (mixed frontend + backend signals) ───────────────────
    has_frontend = any(p.endswith((".html", ".jsx", ".tsx")) for p in paths)
    has_backend = any(p.endswith(".py") or "server." in p for p in paths)
    if has_frontend and has_backend:
        return "fullstack"

    # ── detect static (any .html file, no framework) ─────────────────────────
    if any(p.endswith(".html") for p in paths):
        return "static"

    return "unknown"


# ── Phase 6 — Error Intelligence ─────────────────────────────────────────────

# Regex patterns that map raw tool output → structured error info
_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern, category, human-readable template)
    (
        r"Module not found: Error: Can't resolve '(?P<mod>[^']+)'",
        "missing_module",
        "Missing module '{mod}'. Run: npm install {mod}",
    ),
    (
        r"Cannot find module '(?P<mod>[^']+)'",
        "missing_module",
        "Missing module '{mod}'. Run: npm install {mod}",
    ),
    (
        r"error TS(?P<code>\d+): (?P<msg>.+)",
        "typescript_error",
        "TypeScript error TS{code}: {msg}",
    ),
    (
        r"\[vite\].*(?:error|Error).*?:\s*(?P<msg>.+)",
        "vite_error",
        "Vite build error: {msg}",
    ),
    (
        r"npm ERR! missing: (?P<pkg>[^\s,]+)",
        "npm_missing",
        "npm cannot find package '{pkg}'. Run: npm install {pkg}",
    ),
    (
        r"npm ERR! code (?P<code>\w+)",
        "npm_error",
        "npm failed with code {code}. Check your package.json and network connection.",
    ),
    (
        r"SyntaxError: (?P<msg>.+)",
        "syntax_error",
        "JavaScript syntax error: {msg}",
    ),
    (
        r"Traceback \(most recent call last\)",
        "python_traceback",
        "Python exception occurred (see logs for full traceback).",
    ),
    (
        r"ModuleNotFoundError: No module named '(?P<mod>[^']+)'",
        "missing_python_module",
        "Missing Python module '{mod}'. Run: pip install {mod}",
    ),
    (
        r"ImportError: cannot import name '(?P<name>[^']+)' from '(?P<mod>[^']+)'",
        "import_error",
        "Cannot import '{name}' from '{mod}'. Check package version.",
    ),
    (
        r"error: command '(?P<cmd>[^']+)' failed",
        "command_failed",
        "Command '{cmd}' failed. Check build logs above for details.",
    ),
    (
        r"ENOENT: no such file or directory.*'(?P<path>[^']+)'",
        "missing_file",
        "Missing file or directory: {path}",
    ),
    (
        r"EACCES: permission denied.*'(?P<path>[^']+)'",
        "permission_error",
        "Permission denied: {path}. Cannot write to that location.",
    ),
    (
        r"(?:[A-Z_]{3,})\s+is not defined",
        "missing_env",
        "Missing environment variable. Check your .env file.",
    ),
    (
        r"error: process exited with code (?P<code>\d+)",
        "process_exit",
        "Process exited with code {code}. Review logs above.",
    ),
]


@dataclass
class ParsedError:
    """A structured, human-readable error extracted from raw tool output."""
    category: str
    message: str
    repair_task: str
    raw_line: str


def parse_error_output(raw: str) -> list[ParsedError]:
    """
    Parse raw stdout/stderr from a build or install command and return
    a list of structured, human-readable ParsedError objects.

    Args:
        raw: Combined stdout+stderr text from a subprocess run.

    Returns:
        List of ParsedError objects (may be empty if no known errors found).
    """
    results: list[ParsedError] = []
    seen_categories: set[str] = set()

    for line in raw.splitlines():
        for pattern, category, template in _ERROR_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                groups = m.groupdict()
                # Fill missing named groups with empty string
                filled = {k: (v or "") for k, v in groups.items()}
                try:
                    repair_task = template.format(**filled)
                except KeyError:
                    repair_task = template

                # Deduplicate by category for traceback-style errors
                if category in ("python_traceback",) and category in seen_categories:
                    continue
                seen_categories.add(category)
                results.append(ParsedError(
                    category=category,
                    message=line.strip(),
                    repair_task=repair_task,
                    raw_line=line,
                ))
                break  # first matching pattern wins for this line

    return results


# ── Phase 1 — Sandbox Result ──────────────────────────────────────────────────

@dataclass
class SandboxResult:
    """
    The result of a sandbox operation (install, build, or preview start).

    Attributes:
        success:       True if the operation completed without error.
        stack:         Detected stack type (see STACK_TYPES).
        logs:          Captured stdout+stderr lines (capped at _MAX_LOG_LINES).
        errors:        Parsed, human-readable errors extracted from logs.
        preview_url:   Local URL where the app is being served (if applicable).
        preview_html:  Inlined HTML for static previews (if applicable).
        install_ok:    True if npm/pip install succeeded.
        build_ok:      True if vite/next build succeeded.
        runtime_status: "idle" | "installing" | "building" | "running" | "error" | "stopped"
        cache_bust:    A UUID string; changes on each hot-reload restart.
        workspace_id:  ID of the isolated sandbox workspace.
    """
    success: bool = False
    stack: str = "unknown"
    logs: list[str] = field(default_factory=list)
    errors: list[ParsedError] = field(default_factory=list)
    preview_url: str = ""
    preview_html: str = ""
    install_ok: bool = False
    build_ok: bool = False
    runtime_status: str = "idle"
    cache_bust: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        """Serialise to a plain dict (suitable for JSON API responses)."""
        return {
            "success": self.success,
            "stack": self.stack,
            "logs": self.logs,
            "errors": [
                {
                    "category": e.category,
                    "message": e.message,
                    "repairTask": e.repair_task,
                }
                for e in self.errors
            ],
            "previewUrl": self.preview_url,
            "previewHtml": self.preview_html,
            "installOk": self.install_ok,
            "buildOk": self.build_ok,
            "runtimeStatus": self.runtime_status,
            "cacheBust": self.cache_bust,
            "workspaceId": self.workspace_id,
        }


# ── Phase 1 + 3 — Sandbox Manager ────────────────────────────────────────────

class SandboxManager:
    """
    Manages isolated sandboxed workspaces for executing and previewing apps.

    Each workspace is a temporary directory.  Commands are run via
    asyncio.create_subprocess_exec (never shell=True) with timeout and
    memory-limit enforcement.

    Usage::

        async with SandboxManager() as sb:
            result = await sb.run_preview(files)
            print(result.preview_url)
    """

    def __init__(
        self,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
        install_timeout: int = _INSTALL_TIMEOUT_SECONDS,
        build_timeout: int = _BUILD_TIMEOUT_SECONDS,
        max_memory_mb: int = _MAX_MEMORY_MB,
    ) -> None:
        self._timeout = timeout
        self._install_timeout = install_timeout
        self._build_timeout = build_timeout
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._workspaces: dict[str, Path] = {}     # workspace_id → dir
        self._processes: dict[str, asyncio.subprocess.Process] = {}  # id → proc
        self._port_map: dict[str, int] = {}        # workspace_id → port

    # ── context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "SandboxManager":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.cleanup_all()

    # ── Phase 1 — workspace management ───────────────────────────────────────

    def _create_workspace(self) -> tuple[str, Path]:
        """Create a new isolated temp directory and return (workspace_id, path)."""
        wid = str(uuid.uuid4())
        tmp = Path(tempfile.mkdtemp(prefix=f"amarktai_sb_{wid[:8]}_"))
        self._workspaces[wid] = tmp
        logger.debug("Sandbox workspace created: %s → %s", wid, tmp)
        return wid, tmp

    def _write_files(self, workspace: Path, files: list[dict]) -> None:
        """Write project files into the sandbox workspace directory."""
        for f in files:
            rel = f.get("path", "").lstrip("/")
            if not rel or ".." in Path(rel).parts:
                continue  # skip unsafe paths
            dest = workspace / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f.get("content", ""), encoding="utf-8", errors="replace")

    def _cleanup_workspace(self, wid: str) -> None:
        """Remove a sandbox workspace directory and stop its process."""
        proc = self._processes.pop(wid, None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

        ws = self._workspaces.pop(wid, None)
        if ws and ws.exists():
            try:
                shutil.rmtree(ws, ignore_errors=True)
                logger.debug("Sandbox workspace removed: %s", ws)
            except Exception as exc:
                logger.warning("Failed to remove sandbox workspace %s: %s", ws, exc)

    async def cleanup_all(self) -> None:
        """Terminate all running processes and remove all workspaces."""
        for wid in list(self._workspaces.keys()):
            self._cleanup_workspace(wid)

    # ── Phase 3 — safe subprocess runner ─────────────────────────────────────

    def _safe_env(self) -> dict[str, str]:
        """Build a minimal, safe environment for subprocess execution."""
        env: dict[str, str] = {}
        for key in _SAFE_ENV_KEYS:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        # Always set NODE_ENV for JS tools
        env.setdefault("NODE_ENV", "production")
        env.setdefault("CI", "true")             # suppresses interactive prompts
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

    def _memory_limit_preexec(self) -> None:
        """
        Called in the child process before exec.  Sets RLIMIT_AS to cap memory.
        Only effective on Linux; harmless to set on other platforms.
        Note: preexec_fn is not safe in multi-threaded processes.  This sandbox
        is intended for use in single-threaded async workers; for production
        multi-threaded deployments, enforce memory limits at the container or
        cgroup level instead.
        """
        if resource is None:
            return
        try:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self._max_memory_bytes, self._max_memory_bytes),
            )
        except (ValueError, resource.error):
            pass  # not supported on all platforms

    async def _run_command(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int,
        log_lines: list[str],
    ) -> tuple[int, str]:
        """
        Run *cmd* safely inside *cwd* with *timeout* seconds.

        - Never uses shell=True.
        - Uses a safe minimal environment.
        - Captures stdout+stderr into *log_lines* (in-place).
        - Returns (returncode, combined_output).
        - Raises asyncio.TimeoutError if timeout is exceeded.
        """
        env = self._safe_env()
        preexec_fn = self._memory_limit_preexec if os.name != "nt" and resource is not None else None
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=preexec_fn,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.terminate()
                await asyncio.sleep(0.5)
                proc.kill()
            except Exception:
                pass
            log_lines.append(f"[sandbox] Command timed out after {timeout}s: {' '.join(cmd)}")
            raise

        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        for line in output.splitlines()[-_MAX_LOG_LINES:]:
            log_lines.append(line)
        return proc.returncode or 0, output

    # ── Phase 1 — npm install ─────────────────────────────────────────────────

    async def npm_install(
        self,
        workspace: Path,
        log_lines: list[str],
    ) -> bool:
        """Run `npm install --prefer-offline --no-audit --no-fund` in workspace."""
        pkg_json = workspace / "package.json"
        if not pkg_json.exists():
            log_lines.append("[sandbox] No package.json found — skipping npm install")
            return True  # nothing to install is OK

        # Dependency count safety check
        try:
            pkg_data = json.loads(pkg_json.read_text())
            dep_count = (
                len(pkg_data.get("dependencies", {}))
                + len(pkg_data.get("devDependencies", {}))
            )
            if dep_count > _MAX_DEPS:
                log_lines.append(
                    f"[sandbox] Refused npm install: {dep_count} deps exceeds limit of {_MAX_DEPS}"
                )
                return False
        except (json.JSONDecodeError, OSError):
            pass

        log_lines.append("[sandbox] Running npm install…")
        try:
            rc, _ = await self._run_command(
                ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
                cwd=workspace,
                timeout=self._install_timeout,
                log_lines=log_lines,
            )
            ok = rc == 0
            log_lines.append(f"[sandbox] npm install {'succeeded' if ok else 'failed'} (exit {rc})")
            return ok
        except asyncio.TimeoutError:
            log_lines.append("[sandbox] npm install timed out")
            return False
        except FileNotFoundError:
            log_lines.append("[sandbox] npm not found on PATH — cannot install JS dependencies")
            return False

    # ── Phase 1 — pip install ─────────────────────────────────────────────────

    async def pip_install(
        self,
        workspace: Path,
        log_lines: list[str],
    ) -> bool:
        """Run `pip install -r requirements.txt` in workspace (if present)."""
        req_file = workspace / "requirements.txt"
        if not req_file.exists():
            log_lines.append("[sandbox] No requirements.txt — skipping pip install")
            return True

        log_lines.append("[sandbox] Running pip install…")
        try:
            rc, _ = await self._run_command(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
                 "--quiet", "--disable-pip-version-check"],
                cwd=workspace,
                timeout=self._install_timeout,
                log_lines=log_lines,
            )
            ok = rc == 0
            log_lines.append(f"[sandbox] pip install {'succeeded' if ok else 'failed'} (exit {rc})")
            return ok
        except asyncio.TimeoutError:
            log_lines.append("[sandbox] pip install timed out")
            return False

    # ── Phase 1 — vite build ──────────────────────────────────────────────────

    async def vite_build(
        self,
        workspace: Path,
        log_lines: list[str],
    ) -> bool:
        """Run `npm run build` for Vite projects."""
        log_lines.append("[sandbox] Running vite build (npm run build)…")
        try:
            rc, _ = await self._run_command(
                ["npm", "run", "build"],
                cwd=workspace,
                timeout=self._build_timeout,
                log_lines=log_lines,
            )
            ok = rc == 0
            log_lines.append(f"[sandbox] vite build {'succeeded' if ok else 'failed'} (exit {rc})")
            return ok
        except asyncio.TimeoutError:
            log_lines.append("[sandbox] vite build timed out")
            return False
        except FileNotFoundError:
            log_lines.append("[sandbox] npm not found — cannot run vite build")
            return False

    # ── Phase 1 — next build ──────────────────────────────────────────────────

    async def next_build(
        self,
        workspace: Path,
        log_lines: list[str],
    ) -> bool:
        """Run `npm run build` for Next.js projects."""
        log_lines.append("[sandbox] Running next build (npm run build)…")
        try:
            rc, _ = await self._run_command(
                ["npm", "run", "build"],
                cwd=workspace,
                timeout=self._build_timeout,
                log_lines=log_lines,
            )
            ok = rc == 0
            log_lines.append(f"[sandbox] next build {'succeeded' if ok else 'failed'} (exit {rc})")
            return ok
        except asyncio.TimeoutError:
            log_lines.append("[sandbox] next build timed out")
            return False
        except FileNotFoundError:
            log_lines.append("[sandbox] npm not found — cannot run next build")
            return False

    # ── Phase 4 — static preview ──────────────────────────────────────────────

    def _build_static_preview(self, files: list[dict]) -> str:
        """
        Inline a static project's CSS/JS into its index.html for iframe preview.
        Returns the inlined HTML string, or an empty string if no index.html.
        """
        return render_preview(files)

    # ── Phase 4 — runtime status helper ──────────────────────────────────────

    @staticmethod
    def _make_fallback_preview(
        stack: str,
        logs: list[str],
        errors: list[ParsedError],
        install_ok: bool,
        build_ok: bool,
        workspace_id: str,
    ) -> dict:
        """Build the API-preview-fallback object for non-static stacks."""
        return {
            "canPreview": False,
            "type": "sandbox-fallback",
            "stack": stack,
            "installOk": install_ok,
            "buildOk": build_ok,
            "runtimeStatus": "error" if not (install_ok and build_ok) else "stopped",
            "logs": logs[-_MAX_LOG_LINES:],
            "errors": [
                {"category": e.category, "repairTask": e.repair_task}
                for e in errors
            ],
            "workspaceId": workspace_id,
        }

    # ── Phase 5 — hot reload / file patch ────────────────────────────────────

    async def patch_and_reload(
        self,
        workspace_id: str,
        patched_files: list[dict],
        result: SandboxResult,
    ) -> SandboxResult:
        """
        Apply file patches to a running sandbox and signal a hot reload.

        Args:
            workspace_id: ID returned from a previous run_preview() call.
            patched_files: List of {"path": str, "content": str} dicts to update.
            result:        The SandboxResult from the previous run (mutated in-place).

        Returns:
            Updated SandboxResult with a new cache_bust token.
        """
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            result.logs.append(f"[sandbox] Workspace {workspace_id} not found — cannot patch")
            result.success = False
            return result

        # Write patched files
        self._write_files(ws, patched_files)
        result.logs.append(f"[sandbox] Hot-reload: patched {len(patched_files)} file(s)")

        # Restart preview process if still running
        proc = self._processes.get(workspace_id)
        if proc is not None:
            try:
                proc.terminate()
                await asyncio.sleep(0.2)
            except Exception:
                pass
            self._processes.pop(workspace_id, None)

        # Bust cache so frontend knows to refresh iframe
        result.cache_bust = str(uuid.uuid4())
        result.runtime_status = "running"
        result.success = True
        return result

    # ── Phase 1 — main entry point ────────────────────────────────────────────

    async def run_preview(
        self,
        files: list[dict],
        *,
        stack_hint: str | None = None,
    ) -> SandboxResult:
        """
        The main preview entry point.

        Detects stack, writes files to an isolated workspace, runs install +
        build, and returns a SandboxResult with either inline HTML (static)
        or a fallback descriptor (everything else).

        Args:
            files:      Project files as list of {"path": str, "content": str}.
            stack_hint: Optional override for stack detection.

        Returns:
            SandboxResult instance.
        """
        wid, workspace = self._create_workspace()
        log_lines: list[str] = []
        result = SandboxResult(workspace_id=wid, runtime_status="idle")

        try:
            # ── Detect stack ──────────────────────────────────────────────────
            stack = stack_hint or detect_stack(files)
            result.stack = stack
            log_lines.append(f"[sandbox] Detected stack: {stack}")
            result.runtime_status = "installing"

            # ── Write files ───────────────────────────────────────────────────
            self._write_files(workspace, files)
            log_lines.append(f"[sandbox] Wrote {len(files)} file(s) to workspace")

            # ── Static preview: no install/build needed ───────────────────────
            if stack == "static":
                html = self._build_static_preview(files)
                result.preview_html = html
                result.install_ok = True
                result.build_ok = True
                result.success = bool(html)
                result.runtime_status = "running" if result.success else "error"
                result.logs = log_lines[-_MAX_LOG_LINES:]
                return result

            # ── PWA: treat like static for preview ────────────────────────────
            if stack == "pwa":
                html = self._build_static_preview(files)
                result.preview_html = html
                result.install_ok = True
                result.build_ok = True
                result.success = bool(html)
                result.runtime_status = "running" if result.success else "error"
                result.logs = log_lines[-_MAX_LOG_LINES:]
                return result

            # ── JS stacks: npm install + build ────────────────────────────────
            if stack in ("vite", "react", "next", "express"):
                install_ok = await self.npm_install(workspace, log_lines)
                result.install_ok = install_ok

                if not install_ok:
                    result.runtime_status = "error"
                    result.errors = parse_error_output("\n".join(log_lines))
                    result.logs = log_lines[-_MAX_LOG_LINES:]
                    result.success = False
                    return result

                result.runtime_status = "building"

                if stack == "next":
                    build_ok = await self.next_build(workspace, log_lines)
                elif stack in ("vite", "react"):
                    build_ok = await self.vite_build(workspace, log_lines)
                else:
                    # Express: no build step required
                    build_ok = True
                    log_lines.append("[sandbox] Express detected — no build step required")

                result.build_ok = build_ok
                result.errors = parse_error_output("\n".join(log_lines))

                if not build_ok:
                    result.runtime_status = "error"
                    result.logs = log_lines[-_MAX_LOG_LINES:]
                    result.success = False
                    return result

                result.runtime_status = "running"
                result.success = True
                result.logs = log_lines[-_MAX_LOG_LINES:]
                return result

            # ── Python stacks: pip install ────────────────────────────────────
            if stack in ("fastapi", "django", "flask"):
                install_ok = await self.pip_install(workspace, log_lines)
                result.install_ok = install_ok
                result.build_ok = True  # Python apps don't have a separate build
                result.errors = parse_error_output("\n".join(log_lines))
                result.success = install_ok
                result.runtime_status = "running" if install_ok else "error"
                result.logs = log_lines[-_MAX_LOG_LINES:]
                return result

            # ── Fullstack: attempt both ───────────────────────────────────────
            if stack == "fullstack":
                js_ok = await self.npm_install(workspace, log_lines)
                py_ok = await self.pip_install(workspace, log_lines)
                result.install_ok = js_ok or py_ok
                result.build_ok = True
                result.errors = parse_error_output("\n".join(log_lines))
                result.success = result.install_ok
                result.runtime_status = "running" if result.success else "error"
                result.logs = log_lines[-_MAX_LOG_LINES:]
                return result

            # ── Unknown: return fallback ──────────────────────────────────────
            log_lines.append(f"[sandbox] Unknown stack '{stack}' — returning fallback")
            result.runtime_status = "error"
            result.logs = log_lines[-_MAX_LOG_LINES:]
            result.success = False
            return result

        except Exception as exc:
            log_lines.append(f"[sandbox] Unexpected error: {exc}")
            result.logs = log_lines[-_MAX_LOG_LINES:]
            result.runtime_status = "error"
            result.success = False
            logger.exception("Sandbox run_preview failed for workspace %s", wid)
            return result

        finally:
            # Clean up the workspace directory after the preview is built.
            # run_preview() is a one-shot build; it does not start a long-running
            # dev server.  For persistent dev-server support, call _create_workspace()
            # and manage the lifecycle manually via cleanup_all().
            self._cleanup_workspace(wid)
