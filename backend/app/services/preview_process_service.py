from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from app.services.build_storage_service import get_storage_root
from app.services.frontend_detection_service import detect_frontend


_PROCESSES: dict[str, subprocess.Popen] = {}
_SAFE_PROJECT_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_inside_root(path: Path) -> None:
    root = get_storage_root().resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"Workspace path must be inside build storage: {root}")


def _state_path(project_id: str) -> Path:
    safe_id = _SAFE_PROJECT_RE.sub("_", project_id)[:80]
    path = get_storage_root() / "logs" / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path / "preview_state.json"


def _log_path(project_id: str) -> Path:
    safe_id = _SAFE_PROJECT_RE.sub("_", project_id)[:80]
    path = get_storage_root() / "logs" / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path / "preview.log"


def _write_state(project_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state = {**state, "updated_at": _now()}
    _state_path(project_id).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def load_preview_state(project_id: str) -> dict[str, Any]:
    path = _state_path(project_id)
    if not path.exists():
        return {"project_id": project_id, "status": "not_started", "url": None}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"project_id": project_id, "status": "unknown", "url": None}
    proc = _PROCESSES.get(project_id)
    if proc and proc.poll() is not None and state.get("status") == "running":
        state = _write_state(project_id, {**state, "status": "stopped", "exit_code": proc.returncode})
    return state


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _frontend_root(workspace: Path, detection: dict[str, Any]) -> Path:
    rel = detection.get("frontend_root") or "."
    root = (workspace / rel).resolve()
    root.relative_to(workspace.resolve())
    return root


def _dev_command(package_manager: str, framework: str, port: int) -> tuple[list[str], dict[str, str]]:
    pm = package_manager if package_manager in {"npm", "pnpm", "yarn"} else "npm"
    if pm == "yarn":
        base = ["yarn"]
        run = []
    else:
        base = [pm, "run"]
        run = []
    env = {"PORT": str(port), "HOST": "0.0.0.0", "BROWSER": "none"}

    if framework in {"cra"}:
        return (["yarn", "start"] if pm == "yarn" else [pm, "run", "start"]), env
    if framework in {"nextjs", "nuxt"}:
        script = "dev"
        args = ["--", "-H", "0.0.0.0", "-p", str(port)] if framework == "nextjs" else ["--", "--host", "0.0.0.0", "--port", str(port)]
        return (base + [script] + run + args), env
    if framework in {"vite", "vue", "react", "svelte", "sveltekit", "astro", "generic_js"}:
        return (base + ["dev"] + run + ["--", "--host", "0.0.0.0", "--port", str(port)]), env
    raise ValueError(f"Preview is not supported for framework: {framework}")


def _wait_for_http(url: str, timeout_seconds: int = 20) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def start_preview(project_id: str, workspace_path: str | Path, backend_base_url: str = "/api") -> dict[str, Any]:
    workspace = Path(workspace_path).resolve()
    _assert_inside_root(workspace)
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace}")

    stop_preview(project_id)
    detection = detect_frontend(workspace)
    if not detection.get("detected"):
        state = {
            "project_id": project_id,
            "status": "failed",
            "url": None,
            "logs": detection.get("detection_notes", []),
            "repair_suggestion": "Import or generate a supported frontend before starting preview.",
            "detection": detection,
        }
        return _write_state(project_id, state)

    if detection.get("static_html"):
        rel_root = detection.get("frontend_root") or "."
        url = f"{backend_base_url}/builds/{project_id}/preview/static/index.html?workspace_path={quote(str(workspace))}"
        state = {
            "project_id": project_id,
            "status": "running",
            "kind": "static",
            "url": url,
            "workspace_path": str(workspace),
            "static_root": rel_root,
            "detection": detection,
            "logs": ["Static preview ready."],
        }
        return _write_state(project_id, state)

    port = _free_port()
    frontend_root = _frontend_root(workspace, detection)
    cmd, env_extra = _dev_command(detection.get("package_manager", "npm"), detection.get("framework", "unknown"), port)
    log_path = _log_path(project_id)
    env = {**os.environ, **env_extra, "CI": "true"}
    log_file = log_path.open("ab")
    proc = subprocess.Popen(cmd, cwd=str(frontend_root), stdout=log_file, stderr=subprocess.STDOUT, env=env, shell=False)
    _PROCESSES[project_id] = proc
    url = f"http://127.0.0.1:{port}"
    ready = _wait_for_http(url)
    if not ready:
        exit_code = proc.poll()
        if exit_code is None:
            proc.terminate()
        logs = log_path.read_text(encoding="utf-8", errors="replace")[-6000:] if log_path.exists() else ""
        state = {
            "project_id": project_id,
            "status": "failed",
            "url": None,
            "exit_code": exit_code,
            "command": cmd,
            "log_path": str(log_path),
            "logs": logs.splitlines()[-80:],
            "repair_suggestion": "Preview dev server did not become healthy before timeout. Check install/build logs and package scripts.",
            "detection": detection,
        }
        return _write_state(project_id, state)

    state = {
        "project_id": project_id,
        "status": "running",
        "kind": "dev_server",
        "url": url,
        "port": port,
        "pid": proc.pid,
        "workspace_path": str(workspace),
        "frontend_root": str(frontend_root),
        "command": cmd,
        "log_path": str(log_path),
        "detection": detection,
        "logs": ["Preview dev server started."],
    }
    return _write_state(project_id, state)


def stop_preview(project_id: str) -> dict[str, Any]:
    proc = _PROCESSES.pop(project_id, None)
    state = load_preview_state(project_id)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    return _write_state(project_id, {**state, "status": "stopped", "url": None})
