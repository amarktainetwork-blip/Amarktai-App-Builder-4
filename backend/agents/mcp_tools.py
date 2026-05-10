"""Tool layer for Amarktai Coding Agents."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

import httpx


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the current project sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the content of a file in the current project sandbox.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files in the current project sandbox.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web with Brave Search when the optional key is configured.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def safe_project_path(path: str) -> str:
    if not path or "\x00" in path:
        raise ValueError("Invalid file path")
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Path traversal is not allowed")
    cleaned = str(candidate)
    if cleaned in ("", "."):
        raise ValueError("Invalid file path")
    return cleaned


class ProjectFS:
    """Per-project filesystem stored in MongoDB."""

    def __init__(self, db, project_id: str):
        self.db = db
        self.project_id = project_id

    async def write(self, path: str, content: str, language: str = "text") -> dict:
        cleaned = safe_project_path(path)
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "project_id": self.project_id,
            "path": cleaned,
            "content": content,
            "language": language,
            "updated_at": now,
        }
        await self.db.files.update_one(
            {"project_id": self.project_id, "path": cleaned},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return {"path": cleaned, "language": language, "size": len(content), "updated_at": now}

    async def read(self, path: str) -> dict | None:
        cleaned = safe_project_path(path)
        return await self.db.files.find_one(
            {"project_id": self.project_id, "path": cleaned}, {"_id": 0}
        )

    async def list(self) -> list[dict]:
        cur = self.db.files.find(
            {"project_id": self.project_id},
            {"_id": 0, "path": 1, "language": 1, "updated_at": 1},
        ).sort("path", 1)
        return await cur.to_list(2000)

    async def list_full(self) -> list[dict]:
        cur = self.db.files.find({"project_id": self.project_id}, {"_id": 0}).sort("path", 1)
        return await cur.to_list(2000)


async def web_search(query: str, api_key: str | None) -> dict:
    if not api_key:
        return {"enabled": False, "query": query, "results": []}
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": 5, "text_decorations": "false"}
    async with httpx.AsyncClient(timeout=15.0) as cx:
        response = await cx.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
    results = []
    for item in data.get("web", {}).get("results", [])[:5]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("description"),
            "url": item.get("url"),
        })
    return {"enabled": True, "query": query, "results": results}
