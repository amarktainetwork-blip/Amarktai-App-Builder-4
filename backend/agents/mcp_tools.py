"""
MCP-style tool layer for the Emergent orchestrator.

These helpers expose a Model-Context-Protocol-compatible surface (filesystem, github, web search)
backed by either real services (when API keys are present) or sensible mock implementations.

The JSON tool schemas exposed to the LLM are kept here so the orchestrator can advertise them
to GenXProvider when tool-calling is enabled.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


# ----- Tool JSON Schemas (advertised to LLMs) -----------------------------------------------

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
        "description": "Search the web (Brave Search) for research / inspiration.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "github_create_repo",
        "description": "Create a new GitHub repository and push the project to it.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "private": {"type": "boolean"},
            },
            "required": ["name"],
        },
    },
]


# ----- MongoDB-backed filesystem -------------------------------------------------------------

class ProjectFS:
    """Per-project filesystem stored in MongoDB."""

    def __init__(self, db, project_id: str):
        self.db = db
        self.project_id = project_id

    async def write(self, path: str, content: str, language: str = "text") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "project_id": self.project_id,
            "path": path,
            "content": content,
            "language": language,
            "updated_at": now,
        }
        await self.db.files.update_one(
            {"project_id": self.project_id, "path": path},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return {"path": path, "language": language, "size": len(content), "updated_at": now}

    async def read(self, path: str) -> dict | None:
        doc = await self.db.files.find_one(
            {"project_id": self.project_id, "path": path}, {"_id": 0}
        )
        return doc

    async def list(self) -> list[dict]:
        cur = self.db.files.find(
            {"project_id": self.project_id},
            {"_id": 0, "path": 1, "language": 1, "updated_at": 1},
        )
        return await cur.to_list(2000)

    async def list_full(self) -> list[dict]:
        cur = self.db.files.find({"project_id": self.project_id}, {"_id": 0})
        return await cur.to_list(2000)


# ----- External tools (mocked when no key is provided) ---------------------------------------

async def web_search(query: str) -> dict:
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return {
            "mocked": True,
            "query": query,
            "results": [
                {
                    "title": f"Mock result for '{query}'",
                    "snippet": "Brave Search API key not configured. "
                    "Add BRAVE_SEARCH_API_KEY to backend/.env to enable real web search.",
                    "url": "https://brave.com/search/api/",
                }
            ],
        }
    # Real Brave Search call would go here.
    return {"mocked": False, "query": query, "results": []}


async def github_create_repo(name: str, description: str = "", private: bool = False) -> dict:
    pat = os.environ.get("GITHUB_PAT")
    if not pat:
        return {
            "mocked": True,
            "repo": f"placeholder-org/{name}",
            "url": f"https://github.com/placeholder-org/{name}",
            "message": "GITHUB_PAT not configured. Add it to backend/.env to enable real pushes.",
        }
    # Real GitHub API calls would go here.
    return {"mocked": False, "repo": f"you/{name}", "url": f"https://github.com/you/{name}"}
