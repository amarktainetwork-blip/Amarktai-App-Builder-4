"""
Amarktai App Builder — Safe Command Runner Service.

Provides a strictly allow-listed command runner for project workspaces.
All commands run inside BUILDS_STORAGE_ROOT. No arbitrary shell execution.

Supported commands:
  npm install / npm run build / npm run dev / npm test / npm run lint
  pnpm install / pnpm run build / pnpm test
  yarn install / yarn build / yarn test
  python -m pytest / python -m unittest
  git status / git diff / git log / git branch
  (docker commands require explicit confirmation)

Security:
  - Allowlist only — command not in list → rejected immediately.
  - Working directory must be inside BUILDS_STORAGE_ROOT.
  - Timeouts enforced per command type.
  - Output capped at MAX_LOG_BYTES.
  - Logs stored to /var/www/amarktai/builds/logs/{project_id}/.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.command_runner")

DEFAULT_BUILDS_ROOT = "/var/www/amarktai/builds"
MAX_LOG_BYTES = 128 * 1024  # 128 KB per run
LOGS_SUB = "logs"

# ── Timeouts (seconds) ────────────────────────────────────────────────────────

TIMEOUTS = {
    "install": int(os.environ.get("RUNNER_INSTALL_TIMEOUT", "300")),
    "build":   int(os.environ.get("RUNNER_BUILD_TIMEOUT", "300")),
    "test":    int(os.environ.get("RUNNER_TEST_TIMEOUT", "180")),
    "lint":    int(os.environ.get("RUNNER_LINT_TIMEOUT", "60")),
    "git":     int(os.environ.get("RUNNER_GIT_TIMEOUT", "60")),
    "docker":  int(os.environ.get("RUNNER_DOCKER_TIMEOUT", "300")),
    "default": int(os.environ.get("RUNNER_DEFAULT_TIMEOUT", "120")),
}

# ── Allowed commands (args list prefix) ──────────────────────────────────────
# Each entry is (command_type, args_prefix_as_tuple)

ALLOWED_COMMANDS: list[tuple[str, tuple[str, ...]]] = [
    # npm
    ("install", ("npm", "install")),
    ("install", ("npm", "ci")),
    ("build",   ("npm", "run", "build")),
    ("build",   ("npm", "run", "compile")),
    ("test",    ("npm", "test")),
    ("test",    ("npm", "run", "test")),
    ("lint",    ("npm", "run", "lint")),
    ("build",   ("npm", "run", "start")),   # CRA: npm run start starts the dev server for building/serving
    # pnpm
    ("install", ("pnpm", "install")),
    ("build",   ("pnpm", "run", "build")),
    ("test",    ("pnpm", "test")),
    ("test",    ("pnpm", "run", "test")),
    ("lint",    ("pnpm", "run", "lint")),
    # yarn
    ("install", ("yarn", "install")),
    ("install", ("yarn",)),
    ("build",   ("yarn", "build")),
    ("build",   ("yarn", "run", "build")),
    ("test",    ("yarn", "test")),
    ("lint",    ("yarn", "lint")),
    # python
    ("test",    ("python", "-m", "pytest")),
    ("test",    ("python3", "-m", "pytest")),
    ("test",    ("python", "-m", "unittest")),
    ("test",    ("python3", "-m", "unittest")),
    # pip (install only, inside workspace)
    ("install", ("pip", "install", "-r")),
    ("install", ("pip3", "install", "-r")),
    # git read-only / branch inspection
    ("git",     ("git", "status")),
    ("git",     ("git", "status", "--porcelain")),
    ("git",     ("git", "diff")),
    ("git",     ("git", "diff", "--stat")),
    ("git",     ("git", "diff", "--name-status")),
    ("git",     ("git", "log")),
    ("git",     ("git", "branch")),
    # docker compose validation/build: gated by ALLOW_DOCKER_COMMANDS=true
    ("docker",  ("docker", "compose", "config")),
    ("docker",  ("docker", "compose", "build")),
    ("docker",  ("docker-compose", "config")),
    ("docker",  ("docker-compose", "build")),
]

_SAFE_EXTRA_ARG_RE = re.compile(r"^[a-zA-Z0-9_\-\./=:]{1,200}$")


def _builds_root() -> Path:
    raw = os.environ.get("BUILDS_STORAGE_ROOT", DEFAULT_BUILDS_ROOT)
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _logs_dir(project_id: str) -> Path:
    root = _builds_root()
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", project_id)[:64]
    d = root / LOGS_SUB / safe_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_inside_root(path: Path) -> None:
    root = _builds_root()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal denied: {path} is not inside {root}")


def _match_allowed(cmd_args: list[str]) -> tuple[str, int] | None:
    """Return (command_type, timeout_seconds) if the command is allowed, else None."""
    for cmd_type, prefix in ALLOWED_COMMANDS:
        if tuple(cmd_args[: len(prefix)]) == prefix:
            # Validate any extra args
            extra = cmd_args[len(prefix):]
            if all(_SAFE_EXTRA_ARG_RE.match(a) for a in extra):
                return cmd_type, TIMEOUTS.get(cmd_type, TIMEOUTS["default"])
    return None


def run_command(
    workspace_path: str | Path,
    cmd_args: list[str],
    project_id: str = "unknown",
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Run an allow-listed command in the workspace.

    Returns a structured status dict with stdout, stderr, exit_code, and log_path.
    """
    ws = Path(workspace_path).resolve()

    # Security: path must be inside builds root
    try:
        _assert_inside_root(ws)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "exit_code": -1}

    if not ws.exists():
        return {"ok": False, "error": f"Workspace not found: {ws}", "exit_code": -1}

    # Command allowlist check
    match = _match_allowed(cmd_args)
    if match is None:
        return {
            "ok": False,
            "error": f"Command not allowed: {cmd_args!r}",
            "exit_code": -1,
            "allowed_commands": [list(p) for _, p in ALLOWED_COMMANDS],
        }

    cmd_type, timeout = match
    if cmd_type == "docker" and os.environ.get("ALLOW_DOCKER_COMMANDS", "").lower() not in {"1", "true", "yes"}:
        return {
            "ok": False,
            "error": "Docker command requires ALLOW_DOCKER_COMMANDS=true",
            "exit_code": -1,
            "command": cmd_args,
            "command_type": cmd_type,
        }

    # Build environment
    env = {**os.environ}
    env["CI"] = "true"
    env["NODE_ENV"] = "production" if cmd_type == "build" else "test"
    env.pop("DISPLAY", None)  # no X11
    if env_extra:
        for k, v in env_extra.items():
            if re.match(r"^[A-Z_][A-Z0-9_]{0,100}$", k):
                env[k] = str(v)[:500]

    start_ts = time.monotonic()
    try:
        # Security: shell=False (default for list args). All cmd_args values are
        # validated against ALLOWED_COMMANDS allowlist by _match_allowed() above.
        # workspace_path is validated by _assert_inside_root() above.
        result = subprocess.run(
            cmd_args,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            shell=False,  # explicit: never use shell expansion
        )
        elapsed = time.monotonic() - start_ts
        stdout = result.stdout[:MAX_LOG_BYTES]
        stderr = result.stderr[:MAX_LOG_BYTES]
        exit_code = result.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        elapsed = timeout
        stdout = ""
        stderr = f"Command timed out after {timeout}s"
        exit_code = -1
        timed_out = True
    except FileNotFoundError:
        return {
            "ok": False,
            "error": f"Command not found: {cmd_args[0]}",
            "exit_code": -1,
        }

    ok = exit_code == 0

    # Save logs
    log_path = _save_log(project_id, cmd_args, stdout, stderr, exit_code, elapsed)

    return {
        "ok": ok,
        "exit_code": exit_code,
        "command": cmd_args,
        "command_type": cmd_type,
        "stdout": stdout,
        "stderr": stderr,
        "elapsed_seconds": round(elapsed, 2),
        "timed_out": timed_out,
        "log_path": log_path,
        "ran_at": _now(),
    }


def run_install(workspace_path: str | Path, package_manager: str = "npm", project_id: str = "unknown") -> dict[str, Any]:
    """Run the install command for the detected package manager."""
    pm = package_manager if package_manager in ("npm", "pnpm", "yarn") else "npm"
    cmd = [pm, "install"]
    return run_command(workspace_path, cmd, project_id=project_id)


def run_build(workspace_path: str | Path, package_manager: str = "npm", project_id: str = "unknown") -> dict[str, Any]:
    """Run the build command."""
    pm = package_manager if package_manager in ("npm", "pnpm", "yarn") else "npm"
    if pm == "yarn":
        cmd = ["yarn", "build"]
    else:
        cmd = [pm, "run", "build"]
    return run_command(workspace_path, cmd, project_id=project_id)


def run_tests(workspace_path: str | Path, package_manager: str = "npm", project_id: str = "unknown") -> dict[str, Any]:
    """Run tests."""
    pm = package_manager if package_manager in ("npm", "pnpm", "yarn") else "npm"
    if pm == "yarn":
        cmd = ["yarn", "test"]
    else:
        cmd = [pm, "test"]
    return run_command(workspace_path, cmd, project_id=project_id)


def get_logs(project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent log entries for a project."""
    logs_dir = _logs_dir(project_id)
    entries = []
    for log_file in sorted(logs_dir.glob("*.json"), reverse=True)[:limit]:
        try:
            import json
            entry = json.loads(log_file.read_text())
            entry["log_file"] = log_file.name
            entries.append(entry)
        except Exception:
            pass
    return entries


def _save_log(
    project_id: str,
    cmd_args: list[str],
    stdout: str,
    stderr: str,
    exit_code: int,
    elapsed: float,
) -> str:
    """Save command output to a timestamped JSON file. Returns the path."""
    import json

    logs_dir = _logs_dir(project_id)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cmd_slug = re.sub(r"[^a-z0-9]", "_", "_".join(cmd_args[:3]).lower())[:40]
    log_path = logs_dir / f"{ts}_{cmd_slug}.json"

    entry = {
        "project_id": project_id,
        "command": cmd_args,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed, 2),
        "stdout": stdout[:MAX_LOG_BYTES],
        "stderr": stderr[:MAX_LOG_BYTES],
        "logged_at": _now(),
    }
    try:
        log_path.write_text(json.dumps(entry, indent=2))
    except Exception as exc:
        logger.warning("Could not write log: %s", exc)
    return str(log_path)
