"""Prompt/domain policy for legacy template isolation."""
from __future__ import annotations

import json
import re
from typing import Any

AUTOMOTIVE_TEMPLATE_FILES = {"inventory.html", "vehicle-detail.html", "finance.html"}

_AUTOMOTIVE_INTENT_RE = re.compile(
    r"\b("
    r"automotive|dealership|car dealer|used cars?|luxury cars?|vehicle showroom|"
    r"vehicle inventory|car inventory|test drive|bmw|mercedes|audi|lexus|porsche|"
    r"auto sales|automobile"
    r")\b",
    re.IGNORECASE,
)


def is_automotive_prompt(prompt: str = "", requirements: Any = None, plan: Any = None) -> bool:
    """Return True only for clear automotive/dealership intent."""
    parts = [prompt or ""]
    for value in (requirements, plan):
        if not value:
            continue
        if isinstance(value, str):
            parts.append(value)
        else:
            try:
                parts.append(json.dumps(value, sort_keys=True))
            except Exception:
                parts.append(str(value))
    return bool(_AUTOMOTIVE_INTENT_RE.search("\n".join(parts)))


def remove_legacy_template_contamination(
    files: list[dict],
    *,
    prompt: str = "",
    requirements: Any = None,
    plan: Any = None,
) -> tuple[list[dict], list[str]]:
    """Strip automotive starter pages from non-automotive generated output."""
    if is_automotive_prompt(prompt, requirements, plan):
        return files, []
    cleaned: list[dict] = []
    removed: list[str] = []
    for item in files or []:
        path = str((item or {}).get("path") or "").replace("\\", "/").lstrip("/")
        if path in AUTOMOTIVE_TEMPLATE_FILES:
            removed.append(path)
            continue
        cleaned.append(item)
    return cleaned, removed
