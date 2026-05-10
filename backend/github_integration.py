"""GitHub integration — pull public repo contents, open a PR with our edits.

We talk to the GitHub REST API directly (no PyGithub dep). Only HTTPS, no git CLI.

Two flows:
  - `import_repo(owner, repo, branch, pat)` → returns list of files
  - `open_pr(owner, repo, base_branch, new_branch, files, title, body, pat)` → PR URL
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("amarktai.github")
GH = "https://api.github.com"

# We only mirror text-y files into our sandbox. Binary blobs are skipped.
TEXT_EXTS = {
    ".html", ".htm", ".css", ".scss", ".sass",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".json", ".yml", ".yaml", ".toml", ".ini", ".env.example",
    ".md", ".mdx", ".txt", ".rst",
    ".py", ".rb", ".go", ".rs", ".java", ".kt", ".swift",
    ".sh", ".bash", ".zsh",
    ".vue", ".svelte", ".astro",
    ".sql", ".graphql",
}
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", ".cache", "__pycache__", ".venv", "venv", "target"}
MAX_FILES = 200
MAX_BYTES = 256_000  # per file


def parse_repo_url(url: str) -> tuple[str, str]:
    """github.com/owner/repo[.git][/...] → (owner, repo)."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?\s.]+)(?:\.git)?", url.strip())
    if not m:
        raise ValueError(f"Not a GitHub repo URL: {url}")
    return m.group(1), m.group(2)


def _is_text(path: str) -> bool:
    p = path.lower()
    if any(p.endswith(ext) for ext in TEXT_EXTS):
        return True
    return "/" not in p and "." not in p  # tolerate config files like Dockerfile


async def _gh(cx: httpx.AsyncClient, method: str, path: str, pat: str | None = None,
              json: dict | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if pat:
        headers["Authorization"] = f"Bearer {pat}"
    r = await cx.request(method, f"{GH}{path}", headers=headers, json=json)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub {method} {path} → {r.status_code}: {r.text[:300]}")
    return r.json()


async def import_repo(owner: str, repo: str, branch: str | None = None,
                      pat: str | None = None) -> dict:
    """Pull tree + text-file contents from a public (or PAT-accessible) repo."""
    async with httpx.AsyncClient(timeout=30.0) as cx:
        # Resolve default branch if not given.
        info = await _gh(cx, "GET", f"/repos/{owner}/{repo}", pat)
        default_branch = info.get("default_branch", "main")
        ref = branch or default_branch

        # Get tree (recursive).
        ref_info = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{ref}", pat)
        commit_sha = ref_info["object"]["sha"]
        commit = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/commits/{commit_sha}", pat)
        tree_sha = commit["tree"]["sha"]
        tree = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1", pat)

        files = []
        skipped = 0
        for entry in tree.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry["path"]
            if any(seg in SKIP_DIRS for seg in path.split("/")):
                skipped += 1
                continue
            if not _is_text(path):
                skipped += 1
                continue
            if entry.get("size", 0) > MAX_BYTES:
                skipped += 1
                continue
            if len(files) >= MAX_FILES:
                skipped += 1
                continue
            blob = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/blobs/{entry['sha']}", pat)
            try:
                content = base64.b64decode(blob["content"]).decode("utf-8")
            except UnicodeDecodeError:
                skipped += 1
                continue
            files.append({"path": path, "content": content})

    return {
        "owner": owner, "repo": repo, "branch": ref,
        "default_branch": default_branch,
        "commit_sha": commit_sha,
        "files": files,
        "skipped": skipped,
        "html_url": f"https://github.com/{owner}/{repo}",
    }


async def open_pr(*, owner: str, repo: str, base_branch: str, new_branch: str,
                  files: list[dict], title: str, body: str, pat: str) -> dict:
    """Create branch from base, commit all files, open a PR. PAT must be able to push."""
    if not pat:
        raise ValueError("GitHub PAT required to open a PR")

    async with httpx.AsyncClient(timeout=60.0) as cx:
        # 1) Get base ref SHA
        base_ref = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}", pat)
        base_sha = base_ref["object"]["sha"]

        # 2) Create new branch from base (if it doesn't already exist)
        try:
            await _gh(cx, "POST", f"/repos/{owner}/{repo}/git/refs", pat,
                      json={"ref": f"refs/heads/{new_branch}", "sha": base_sha})
        except RuntimeError as e:
            if "Reference already exists" not in str(e):
                raise

        # 3) Build a tree off the base commit's tree, layering our changed files
        base_commit = await _gh(cx, "GET", f"/repos/{owner}/{repo}/git/commits/{base_sha}", pat)
        base_tree_sha = base_commit["tree"]["sha"]

        tree_items = []
        for f in files:
            blob = await _gh(cx, "POST", f"/repos/{owner}/{repo}/git/blobs", pat,
                             json={"content": f["content"], "encoding": "utf-8"})
            tree_items.append({"path": f["path"], "mode": "100644", "type": "blob",
                               "sha": blob["sha"]})

        new_tree = await _gh(cx, "POST", f"/repos/{owner}/{repo}/git/trees", pat,
                             json={"base_tree": base_tree_sha, "tree": tree_items})

        # 4) Commit on new branch
        new_commit = await _gh(cx, "POST", f"/repos/{owner}/{repo}/git/commits", pat,
                               json={"message": title, "tree": new_tree["sha"],
                                     "parents": [base_sha]})
        await _gh(cx, "PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{new_branch}", pat,
                  json={"sha": new_commit["sha"], "force": False})

        # 5) Open PR
        pr = await _gh(cx, "POST", f"/repos/{owner}/{repo}/pulls", pat,
                       json={"title": title, "head": new_branch, "base": base_branch,
                             "body": body or "", "maintainer_can_modify": True})

    return {
        "pr_number": pr["number"],
        "pr_url": pr["html_url"],
        "branch": new_branch,
        "commit_sha": new_commit["sha"],
    }
