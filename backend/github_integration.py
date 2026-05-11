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


async def validate_pat(pat: str | None) -> dict:
    if not pat:
        return {"configured": False, "valid": False, "login": None}
    async with httpx.AsyncClient(timeout=20.0) as cx:
        user = await _gh(cx, "GET", "/user", pat)
    return {"configured": True, "valid": True, "login": user.get("login"), "html_url": user.get("html_url")}


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


async def check_repo_exists(owner: str, name: str, pat: str) -> bool:
    """Return True if the repo owner/name already exists on GitHub."""
    async with httpx.AsyncClient(timeout=20.0) as cx:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if pat:
            headers["Authorization"] = f"Bearer {pat}"
        r = await cx.get(f"{GH}/repos/{owner}/{name}", headers=headers)
        return r.status_code == 200


async def create_branch_pr_from_files(
    *,
    owner: str,
    repo: str,
    files: list[dict],
    prompt: str,
    job_slug: str,
    pat: str,
    validation_scores: dict | None = None,
    coverage_score: dict | None = None,
    stack: str = "",
    preview_note: str = "",
) -> dict:
    """Create a new branch off the default branch and open a PR with our files.

    Used when the target repo already exists (collision fallback).
    The branch name is: amarktai-builder/{job_slug}

    Phase 8: The PR body now includes validation scores, coverage score, stack,
    preview/fallback note, and changed files for reviewer context.
    """
    if not pat:
        raise ValueError("GitHub PAT is required. Connect GitHub PAT in Settings.")
    if not files:
        raise ValueError("No files are available to commit.")

    branch_name = f"amarktai-builder/{job_slug}"
    title = f"Amarktai App Builder: {prompt[:80]}"

    async with httpx.AsyncClient(timeout=60.0) as cx:
        info = await _gh(cx, "GET", f"/repos/{owner}/{repo}", pat)
        default_branch = info.get("default_branch", "main")

    # Build enriched PR body
    body_lines = [
        "### Generated by Amarktai App Builder",
        "",
        f"**Prompt:** {prompt[:400]}",
        "",
    ]
    if stack:
        body_lines += [f"**Stack:** {stack}", ""]
    if validation_scores:
        q = validation_scores.get("qualityScore", "—")
        d = validation_scores.get("designScore", "—")
        s = validation_scores.get("securityScore", "—")
        ok = validation_scores.get("canFinalize", False)
        body_lines += [
            "**Validation result:**",
            f"- Quality: {q}/100",
            f"- Design: {d}/100",
            f"- Security: {s}/100",
            f"- Can finalize: {'✅ yes' if ok else '⚠️ no'}",
            "",
        ]
    if coverage_score:
        cs = coverage_score.get("coverageScore", "—")
        intent = coverage_score.get("intent", "")
        missing = coverage_score.get("missingRequirements", [])
        body_lines += [f"**Coverage score:** {cs}/100" + (f" ({intent})" if intent else ""), ""]
        if missing:
            body_lines += ["**Missing requirements:**"]
            body_lines += [f"- {m}" for m in missing[:8]]
            body_lines += [""]
    if files:
        body_lines += [
            "**Changed files:**",
            *[f"- `{f['path']}`" for f in files[:30]],
            "",
        ]
    if preview_note:
        body_lines += [f"**Preview:** {preview_note}", ""]
    body_lines += [
        "---",
        f"This PR was created automatically because `{owner}/{repo}` already exists. "
        "Review and merge if the changes look good.",
    ]
    body_md = "\n".join(body_lines)

    return await open_pr(
        owner=owner,
        repo=repo,
        base_branch=default_branch,
        new_branch=branch_name,
        files=files,
        title=title,
        body=body_md,
        pat=pat,
    )


async def create_repo_with_files(*, name: str, description: str, private: bool,
                                 files: list[dict], pat: str) -> dict:
    if not pat:
        raise ValueError("GitHub PAT is required. Connect GitHub PAT in Settings.")
    if not files:
        raise ValueError("No files are available to commit.")

    async with httpx.AsyncClient(timeout=60.0) as cx:
        me = await _gh(cx, "GET", "/user", pat)
        repo = await _gh(cx, "POST", "/user/repos", pat, json={
            "name": name,
            "description": description or "Created with Amarktai App Builder",
            "private": private,
            "auto_init": True,
        })
        owner = repo["owner"]["login"]
        default_branch = repo.get("default_branch") or "main"
        ref = await _gh(cx, "GET", f"/repos/{owner}/{name}/git/ref/heads/{default_branch}", pat)
        base_sha = ref["object"]["sha"]
        base_commit = await _gh(cx, "GET", f"/repos/{owner}/{name}/git/commits/{base_sha}", pat)
        base_tree_sha = base_commit["tree"]["sha"]

        tree_items = []
        for f in files:
            blob = await _gh(cx, "POST", f"/repos/{owner}/{name}/git/blobs", pat,
                             json={"content": f["content"], "encoding": "utf-8"})
            tree_items.append({"path": f["path"], "mode": "100644", "type": "blob", "sha": blob["sha"]})

        new_tree = await _gh(cx, "POST", f"/repos/{owner}/{name}/git/trees", pat,
                             json={"base_tree": base_tree_sha, "tree": tree_items})
        new_commit = await _gh(cx, "POST", f"/repos/{owner}/{name}/git/commits", pat,
                               json={"message": "Initial commit from Amarktai App Builder",
                                     "tree": new_tree["sha"], "parents": [base_sha]})
        await _gh(cx, "PATCH", f"/repos/{owner}/{name}/git/refs/heads/{default_branch}", pat,
                  json={"sha": new_commit["sha"], "force": False})

    return {
        "repo": f"{owner}/{name}",
        "url": repo["html_url"],
        "owner": owner,
        "created_by": me.get("login"),
        "branch": default_branch,
        "commit_sha": new_commit["sha"],
    }


async def open_pr(*, owner: str, repo: str, base_branch: str, new_branch: str,
                  files: list[dict], title: str, body: str, pat: str) -> dict:
    """Create branch from base, commit all files, open a PR. PAT must be able to push."""
    if not pat:
        raise ValueError("GitHub PAT is required. Connect GitHub PAT in Settings.")
    if not files:
        raise ValueError("No files are available to commit.")

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
