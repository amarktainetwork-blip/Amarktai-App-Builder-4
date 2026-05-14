"""
Amarktai App Builder — Real VPS Git Workspace Service.

Provides safe git clone/fetch/checkout/commit/push/PR operations against
GitHub HTTPS URLs only. All operations run inside BUILDS_STORAGE_ROOT.

Security contract:
- Only GitHub HTTPS URLs are accepted.
- owner/repo/branch are sanitised with strict allow-lists.
- subprocess is called with list args (never shell=True).
- Tokens are masked in logged output.
- Working directory is always verified to be inside BUILDS_STORAGE_ROOT.
- Destructive operations (overwrite dirty) require confirm=True.
- All git commands have a configurable timeout (default 60 s).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("amarktai.git_workspace")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BUILDS_ROOT = "/var/www/amarktai/builds"
_GITHUB_HTTPS_RE = re.compile(
    r"^https://github\.com/([a-zA-Z0-9_\-\.]{1,100})/([a-zA-Z0-9_\-\.]{1,100}?)(?:\.git)?/?$"
)
_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_\-\./]{1,200}$")
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,100}$")

GIT_CMD_TIMEOUT = int(os.environ.get("GIT_CMD_TIMEOUT", "120"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _builds_root() -> Path:
    raw = os.environ.get("BUILDS_STORAGE_ROOT", DEFAULT_BUILDS_ROOT)
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _mask_token(url: str) -> str:
    """Replace any token in the URL before logging."""
    return re.sub(r"https://[^@]+@", "https://***@", url)


def _assert_inside_root(path: Path) -> None:
    root = _builds_root()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal denied: {path} is not inside {root}")


def _run_git(args: list[str], cwd: Path, env: dict | None = None,
             timeout: int = GIT_CMD_TIMEOUT) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr).

    Security: all caller-supplied URL args must be validated by _parse_github_url()
    before reaching this function. Shell=True is never used. The cmd list is always
    ["git", <fixed-subcmd>, ...validated-args...], so no shell injection is possible.
    cwd is validated to be inside BUILDS_STORAGE_ROOT by _assert_inside_root().
    """
    _assert_inside_root(cwd)
    # cmd is constructed as a list (not a string) — shell=False is the default for
    # subprocess.run when passed a list, ensuring no shell injection.
    cmd = ["git"] + args
    base_env = {**os.environ}
    if env:
        base_env.update(env)
    # Never prompt for credentials
    base_env["GIT_TERMINAL_PROMPT"] = "0"
    base_env["GIT_ASKPASS"] = "echo"

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=base_env,
            shell=False,  # explicit: never use shell expansion
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"git {args[0]} timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", "git binary not found on PATH"


def _parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from a GitHub HTTPS URL. Raises ValueError if invalid."""
    m = _GITHUB_HTTPS_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Only HTTPS GitHub URLs (https://github.com/owner/repo) are accepted."
        )
    owner, repo = m.group(1), m.group(2)
    if not _SAFE_NAME_RE.match(owner) or not _SAFE_NAME_RE.match(repo):
        raise ValueError(f"Unsafe owner or repo name in URL: {url!r}")
    return owner, repo


def _sanitise_branch(branch: str) -> str:
    if not branch or not _SAFE_REF_RE.match(branch):
        raise ValueError(f"Unsafe branch name: {branch!r}")
    return branch


def _workspace_path(owner: str, repo: str, branch: str) -> Path:
    root = _builds_root()
    ws = (root / "repos" / owner / repo / branch).resolve()
    _assert_inside_root(ws)
    return ws


def _inject_token(url: str, token: str) -> str:
    """Inject a PAT into a GitHub HTTPS URL for authenticated operations."""
    if token and url.startswith("https://github.com/"):
        return url.replace("https://github.com/", f"https://{token}@github.com/")
    return url


def _git_env_with_token(token: str | None) -> dict:
    env: dict[str, str] = {}
    if token:
        env["GITHUB_TOKEN"] = token
    return env


# ── Public API ────────────────────────────────────────────────────────────────

def clone_repo(
    repo_url: str,
    branch: str = "main",
    github_pat: str | None = None,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    """
    Clone a GitHub repo into BUILDS_STORAGE_ROOT/repos/{owner}/{repo}/{branch}.

    Returns a status dict with local_path, logs, and ok flag.
    """
    try:
        owner, repo = _parse_github_url(repo_url)
        branch = _sanitise_branch(branch)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "logs": []}
    ws = _workspace_path(owner, repo, branch)

    logs: list[str] = []

    if ws.exists() and any(ws.iterdir()):
        if not confirm_overwrite:
            return {
                "ok": False,
                "error": f"Workspace already exists at {ws}. Set confirm_overwrite=True to re-clone.",
                "local_path": str(ws),
                "logs": logs,
            }
        shutil.rmtree(ws)
        logs.append(f"Removed existing workspace at {ws}")

    ws.mkdir(parents=True, exist_ok=True)

    auth_url = _inject_token(repo_url.rstrip("/") + ".git", github_pat or "")
    log_url = _mask_token(auth_url)
    logs.append(f"Cloning {log_url} branch={branch}")

    rc, stdout, stderr = _run_git(
        ["clone", "--depth=50", "--branch", branch, auth_url, "."],
        cwd=ws,
        timeout=GIT_CMD_TIMEOUT,
    )
    logs.append(stdout[:2000] if stdout else "")
    if stderr:
        logs.append(_mask_token(stderr[:2000]))

    if rc != 0:
        # Try cloning default branch then checking out the requested branch
        logs.append(f"Direct branch clone failed (rc={rc}), trying default branch then checkout…")
        shutil.rmtree(ws)
        ws.mkdir(parents=True, exist_ok=True)
        rc2, so2, se2 = _run_git(
            ["clone", "--depth=50", auth_url, "."],
            cwd=ws,
            timeout=GIT_CMD_TIMEOUT,
        )
        logs.append(so2[:1000] if so2 else "")
        if se2:
            logs.append(_mask_token(se2[:1000]))
        if rc2 != 0:
            return {
                "ok": False,
                "error": f"git clone failed (rc={rc2}): {_mask_token(se2[:300])}",
                "local_path": str(ws),
                "logs": logs,
            }
        # Checkout branch
        rc3, _, se3 = _run_git(["checkout", branch], cwd=ws)
        if rc3 != 0:
            logs.append(f"Branch {branch!r} not found; staying on default branch.")

    _save_workspace_meta(ws, owner, repo, branch, repo_url)
    return {
        "ok": True,
        "local_path": str(ws),
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "cloned_at": _now(),
        "logs": logs,
    }


def pull_latest(
    owner: str,
    repo: str,
    branch: str,
    github_pat: str | None = None,
    confirm_overwrite_dirty: bool = False,
) -> dict[str, Any]:
    """Fetch and pull the latest changes into the workspace."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"ok": False, "error": f"Workspace not found: {ws}", "logs": []}

    logs: list[str] = []

    # Check dirty state
    status_info = get_git_status(owner, repo, branch)
    if status_info.get("is_dirty") and not confirm_overwrite_dirty:
        return {
            "ok": False,
            "error": "Workspace has uncommitted changes. Set confirm_overwrite_dirty=True to force pull.",
            "dirty_files": status_info.get("changed_files", []),
            "logs": logs,
        }

    rc, so, se = _run_git(["fetch", "origin"], cwd=ws)
    logs.append(f"fetch: rc={rc} {_mask_token(se[:200])}")

    rc2, so2, se2 = _run_git(["pull", "origin", branch], cwd=ws)
    logs.append(f"pull: rc={rc2} {so2[:200]} {_mask_token(se2[:200])}")

    return {
        "ok": rc2 == 0,
        "error": _mask_token(se2[:300]) if rc2 != 0 else None,
        "local_path": str(ws),
        "logs": logs,
    }


def get_git_status(owner: str, repo: str, branch: str) -> dict[str, Any]:
    """Return the current git status of the workspace."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"ok": False, "error": "Workspace not found", "exists": False}

    rc, so, se = _run_git(["status", "--porcelain"], cwd=ws)
    if rc != 0:
        return {"ok": False, "error": se[:200], "exists": True}

    changed_files = [line.strip() for line in so.splitlines() if line.strip()]

    rc2, so2, _ = _run_git(["rev-parse", "HEAD"], cwd=ws)
    commit_sha = so2.strip() if rc2 == 0 else ""

    rc3, so3, _ = _run_git(["log", "--oneline", "-5"], cwd=ws)
    recent_commits = so3.strip().splitlines() if rc3 == 0 else []

    return {
        "ok": True,
        "exists": True,
        "local_path": str(ws),
        "is_dirty": bool(changed_files),
        "changed_files": changed_files,
        "commit_sha": commit_sha,
        "recent_commits": recent_commits,
        "checked_at": _now(),
    }


def create_branch(
    owner: str, repo: str, source_branch: str, new_branch: str
) -> dict[str, Any]:
    """Create a new local branch from source_branch."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    source_branch = _sanitise_branch(source_branch)
    new_branch = _sanitise_branch(new_branch)
    ws = _workspace_path(owner, repo, source_branch)

    if not ws.exists():
        return {"ok": False, "error": "Source workspace not found"}

    rc, _, se = _run_git(["checkout", "-b", new_branch], cwd=ws)
    return {
        "ok": rc == 0,
        "error": se[:200] if rc != 0 else None,
        "branch": new_branch,
        "local_path": str(ws),
    }


def commit_changes(
    owner: str,
    repo: str,
    branch: str,
    message: str,
    author_name: str = "Amarktai Builder",
    author_email: str = "builder@amarktai.com",
) -> dict[str, Any]:
    """Stage all changes and create a commit."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"ok": False, "error": "Workspace not found"}

    # Sanitise commit message
    safe_message = message[:500].replace("\x00", "")

    env = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    rc1, _, se1 = _run_git(["add", "-A"], cwd=ws)
    if rc1 != 0:
        return {"ok": False, "error": f"git add failed: {se1[:200]}"}

    rc2, so2, se2 = _run_git(
        ["commit", "-m", safe_message], cwd=ws, env=env
    )
    if rc2 != 0 and "nothing to commit" in se2 + so2:
        return {"ok": True, "skipped": True, "reason": "nothing to commit"}

    rc3, so3, _ = _run_git(["rev-parse", "HEAD"], cwd=ws)
    commit_sha = so3.strip() if rc3 == 0 else ""

    return {
        "ok": rc2 == 0,
        "error": se2[:200] if rc2 != 0 else None,
        "commit_sha": commit_sha,
        "message": safe_message,
    }


def push_branch(
    owner: str,
    repo: str,
    branch: str,
    github_pat: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Push the local branch to origin."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"ok": False, "error": "Workspace not found"}

    if github_pat:
        # Inject token into remote URL for this push only
        rc_r, so_r, _ = _run_git(["remote", "get-url", "origin"], cwd=ws)
        if rc_r == 0:
            auth_url = _inject_token(so_r.strip(), github_pat)
            _run_git(["remote", "set-url", "origin", auth_url], cwd=ws)

    push_args = ["push", "origin", branch]
    if force:
        push_args.append("--force-with-lease")

    rc, so, se = _run_git(push_args, cwd=ws)
    logs = [_mask_token(so[:500]), _mask_token(se[:500])]

    # Reset remote URL to non-authenticated form to avoid storing token
    if github_pat:
        clean_url = f"https://github.com/{owner}/{repo}.git"
        _run_git(["remote", "set-url", "origin", clean_url], cwd=ws)

    return {
        "ok": rc == 0,
        "error": _mask_token(se[:300]) if rc != 0 else None,
        "branch": branch,
        "logs": logs,
    }


def get_branch_diff(
    owner: str,
    repo: str,
    branch: str,
    base_branch: str = "main",
) -> dict[str, Any]:
    """Return changed files between base_branch and branch for PR gating."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    base_branch = _sanitise_branch(base_branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"ok": False, "error": "Workspace not found", "changed_files": []}

    # Fetch base refs first. If that fails, still try local refs so a user gets
    # a useful deterministic response in offline/dev workspaces.
    _run_git(["fetch", "origin", base_branch], cwd=ws)
    candidates = [
        f"origin/{base_branch}...HEAD",
        f"{base_branch}...HEAD",
    ]
    last_error = ""
    for revision_range in candidates:
        rc, so, se = _run_git(["diff", "--name-status", revision_range], cwd=ws)
        if rc == 0:
            changed_files = [line.strip() for line in so.splitlines() if line.strip()]
            rc_stat, stat, _ = _run_git(["diff", "--stat", revision_range], cwd=ws)
            return {
                "ok": True,
                "base_branch": base_branch,
                "head_branch": branch,
                "has_changes": bool(changed_files),
                "changed_files": changed_files,
                "diff_stat": stat.strip() if rc_stat == 0 else "",
                "checked_at": _now(),
            }
        last_error = se[:300]

    return {
        "ok": False,
        "error": last_error or "Could not compare branch diff",
        "base_branch": base_branch,
        "head_branch": branch,
        "changed_files": [],
        "has_changes": False,
    }


def open_pull_request(
    owner: str,
    repo: str,
    head_branch: str,
    base_branch: str = "main",
    title: str = "Amarktai Builder: automated changes",
    body: str = "",
    github_pat: str | None = None,
) -> dict[str, Any]:
    """Open a GitHub pull request via the REST API."""
    import httpx

    if not github_pat:
        return {"ok": False, "error": "GITHUB_PAT is required to open a pull request."}

    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    head_branch = _sanitise_branch(head_branch)
    base_branch = _sanitise_branch(base_branch)

    payload = {
        "title": title[:256],
        "body": body[:65536],
        "head": head_branch,
        "base": base_branch,
    }

    try:
        r = httpx.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            json=payload,
            headers={
                "Authorization": f"token {github_pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        )
        if r.status_code in (200, 201):
            data = r.json()
            return {
                "ok": True,
                "pr_number": data.get("number"),
                "pr_url": data.get("html_url"),
                "pr_title": data.get("title"),
            }
        return {
            "ok": False,
            "error": f"GitHub API returned {r.status_code}: {r.text[:300]}",
        }
    except Exception as exc:
        return {"ok": False, "error": f"PR request failed: {exc}"}


def get_workspace_info(owner: str, repo: str, branch: str) -> dict[str, Any]:
    """Return metadata for an existing workspace."""
    owner = _sanitise_ref_name(owner)
    repo = _sanitise_ref_name(repo)
    branch = _sanitise_branch(branch)
    ws = _workspace_path(owner, repo, branch)

    if not ws.exists():
        return {"exists": False, "local_path": str(ws)}

    meta_path = ws / "build.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass

    status = get_git_status(owner, repo, branch)
    return {
        "exists": True,
        "local_path": str(ws),
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "meta": meta,
        "git_status": status,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sanitise_ref_name(name: str) -> str:
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Unsafe name: {name!r}")
    return name


def _save_workspace_meta(
    ws: Path, owner: str, repo: str, branch: str, repo_url: str
) -> None:
    meta = {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "repo_url": repo_url,
        "cloned_at": _now(),
        "workspace_type": "repos",
        "build_status": "cloned",
    }
    try:
        (ws / "build.json").write_text(json.dumps(meta, indent=2))
    except Exception as exc:
        logger.warning("Could not write build.json: %s", exc)
