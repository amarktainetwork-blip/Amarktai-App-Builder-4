"""GitHub repository browsing helpers for the Repo Workbench.

The functions in this module intentionally return small, sanitized payloads for
dashboard selection. They never expose tokens and they keep GitHub API responses
out of persistent logs.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

_SAFE_OWNER_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
_SAFE_REPO_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def validate_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    if not _SAFE_OWNER_RE.match(owner):
        raise ValueError("Unsafe GitHub owner")
    if not _SAFE_REPO_RE.match(repo):
        raise ValueError("Unsafe GitHub repo")
    return owner, repo


def normalize_repo(item: dict[str, Any]) -> dict[str, Any]:
    owner = (item.get("owner") or {}).get("login") or ""
    name = item.get("name") or ""
    full_name = item.get("full_name") or f"{owner}/{name}"
    return {
        "id": item.get("id"),
        "owner": owner,
        "name": name,
        "full_name": full_name,
        "html_url": item.get("html_url") or f"https://github.com/{full_name}",
        "clone_url": item.get("clone_url") or f"https://github.com/{full_name}.git",
        "default_branch": item.get("default_branch") or "main",
        "private": bool(item.get("private")),
        "description": item.get("description") or "",
        "updated_at": item.get("updated_at") or "",
        "pushed_at": item.get("pushed_at") or "",
        "archived": bool(item.get("archived")),
        "disabled": bool(item.get("disabled")),
    }


def normalize_branch(item: dict[str, Any]) -> dict[str, Any]:
    commit = item.get("commit") or {}
    return {
        "name": item.get("name") or "",
        "commit_sha": commit.get("sha") or "",
        "protected": bool(item.get("protected")),
    }


async def list_repositories(
    token: str,
    visibility: str = "all",
    per_page: int = 100,
) -> dict[str, Any]:
    if not token:
        return {"ok": False, "configured": False, "items": [], "error": "GITHUB_PAT is not configured"}
    visibility = visibility if visibility in {"all", "public", "private"} else "all"
    per_page = min(max(int(per_page or 100), 1), 100)
    params = {
        "affiliation": "owner,collaborator,organization_member",
        "sort": "updated",
        "direction": "desc",
        "visibility": visibility,
        "per_page": per_page,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers=_headers(token),
            params=params,
        )
    if response.status_code != 200:
        return {
            "ok": False,
            "configured": True,
            "items": [],
            "error": f"GitHub repo listing failed with HTTP {response.status_code}",
        }
    repos = [normalize_repo(item) for item in response.json()]
    return {"ok": True, "configured": True, "items": repos, "total": len(repos)}


async def list_branches(token: str, owner: str, repo: str, per_page: int = 100) -> dict[str, Any]:
    if not token:
        return {"ok": False, "configured": False, "items": [], "error": "GITHUB_PAT is not configured"}
    owner, repo = validate_owner_repo(owner, repo)
    per_page = min(max(int(per_page or 100), 1), 100)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            headers=_headers(token),
            params={"per_page": per_page},
        )
    if response.status_code != 200:
        return {
            "ok": False,
            "configured": True,
            "items": [],
            "error": f"GitHub branch listing failed with HTTP {response.status_code}",
        }
    branches = [normalize_branch(item) for item in response.json()]
    return {"ok": True, "configured": True, "items": branches, "total": len(branches)}
