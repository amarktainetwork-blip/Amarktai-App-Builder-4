from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_AUDIENCE = "founders, agencies, product teams, startups, and businesses"
VALID_MODES = {"landing_page", "website", "web_app", "full_stack", "repo_fix"}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(_strip_fences(text))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return _parse_markdownish(text)
    return {}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _parse_markdownish(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {"summary": ""}
    current_key: str | None = None
    lines = text.splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        kv = re.match(r"^(?:[-*]\s*)?\**([A-Za-z][A-Za-z0-9 _-]{1,40})\**\s*:\s*(.+)$", line)
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if heading:
            current_key = _key(heading.group(1))
            data.setdefault(current_key, [])
        elif kv:
            k = _key(kv.group(1))
            data[k] = _split_list(kv.group(2))
            current_key = k
        elif bullet and current_key:
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(bullet.group(1).strip())
        elif not data.get("summary"):
            data["summary"] = line
    return data


def _key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    aliases = {
        "target_audience": "audience",
        "who_it_is_for": "audience",
        "core_features": "features",
        "file_plan": "required_files",
        "files": "required_files",
    }
    return aliases.get(key, key)


def _split_list(value: Any) -> Any:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not isinstance(value, str):
        return value
    if "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return value.strip()


def _as_list(value: Any) -> list[Any]:
    value = _split_list(value)
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            joined = ", ".join(str(v).strip() for v in value if str(v).strip())
            if joined:
                return joined
    return default


def _infer_brand(project_name: str | None, prompt: str) -> str:
    if project_name and project_name.strip():
        return project_name.strip()
    match = re.search(r"(?:called|named|brand(?:ed)? as)\s+([A-Z][A-Za-z0-9 &'-]{1,50})", prompt)
    if match:
        return match.group(1).strip(" .")
    words = re.findall(r"[A-Z][A-Za-z0-9]+", prompt)
    return " ".join(words[:2]) if words else "Amarktai Build"


def _infer_goal(prompt: str) -> str:
    match = re.search(r"(?:goal|objective)\s*:\s*(.+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if "landing" in prompt.lower():
        return "Convert visitors into qualified leads and product signups."
    return "Create a production-ready digital experience from the supplied brief."


def _infer_style(prompt: str) -> str:
    lowered = prompt.lower()
    style_words = [
        "luxury", "glassmorphism", "cinematic", "minimal", "brutalist",
        "playful", "premium", "dark", "clean", "editorial", "modern",
    ]
    found = [word for word in style_words if word in lowered]
    return ", ".join(found) if found else "premium, modern, polished"


def _normalize_mode(build_mode: str | None) -> str:
    raw = (build_mode or "web_app").strip().lower()
    aliases = {
        "landing": "landing_page",
        "site": "website",
        "app": "web_app",
        "fullstack": "full_stack",
        "repo": "repo_fix",
    }
    mode = aliases.get(raw, raw)
    return mode if mode in VALID_MODES else "web_app"


def normalize_build_context(
    prompt: str,
    project_name: str | None = None,
    build_mode: str | None = None,
    planner_output: Any = None,
    scout_output: Any = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a crash-proof context shared by all builder agents.

    Planner and Scout may return JSON, dicts, markdown, or partial data. This
    helper keeps the pipeline moving with explicit defaults instead of leaking
    KeyError/TypeError into the build.
    """
    planner = _as_dict(planner_output)
    scout = _as_dict(scout_output)
    settings = settings or {}
    mode = _normalize_mode(build_mode)

    audience = _first_text(
        scout.get("audience"),
        scout.get("target_audience"),
        planner.get("audience"),
        planner.get("target_audience"),
        settings.get("audience"),
        default=DEFAULT_AUDIENCE,
    )
    sections = _as_list(scout.get("sections") or planner.get("sections"))
    features = _as_list(
        scout.get("features")
        or scout.get("core_features")
        or planner.get("features")
        or planner.get("core_features")
    )
    required_files = _as_list(
        planner.get("required_files")
        or planner.get("file_plan")
        or scout.get("required_files")
        or settings.get("required_files")
    )
    quality_tier = _first_text(settings.get("quality_tier"), planner.get("quality_tier"), default="balanced").lower()
    if quality_tier not in {"premium", "balanced", "cheap"}:
        quality_tier = "balanced"

    media_policy = _first_text(settings.get("media_policy"), settings.get("media_requirements"), default="css_svg").lower()
    if "stock" in media_policy or "pixabay" in media_policy:
        media_policy = "stock"
    elif "ai" in media_policy or "image" in media_policy:
        media_policy = "ai"
    elif media_policy not in {"ai", "stock", "css_svg"}:
        media_policy = "css_svg"

    return {
        "audience": audience,
        "target_audience": audience,
        "brand_name": _infer_brand(project_name, prompt),
        "product_type": mode.replace("_", " "),
        "goal": _first_text(scout.get("goal"), planner.get("goal"), default=_infer_goal(prompt)),
        "style": _first_text(scout.get("style"), planner.get("style"), default=_infer_style(prompt)),
        "sections": sections,
        "features": features,
        "constraints": _as_list(scout.get("constraints") or planner.get("constraints") or settings.get("constraints")),
        "required_files": required_files,
        "mode": mode,
        "quality_tier": quality_tier,
        "media_policy": media_policy,
        "integrations": _as_list(scout.get("integrations") or planner.get("integrations") or settings.get("integrations")),
        "seo_required": mode in {"landing_page", "website"},
        "accessibility_required": True,
        "preview_required": True,
        "planner": planner,
        "scout": scout,
    }


def ensure_build_context_defaults(
    context: Any,
    *,
    prompt: str = "",
    project_name: str | None = None,
    build_mode: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return context with the required builder defaults enforced.

    This is intentionally small and boring: it preserves existing values, but
    guarantees both audience aliases and the shared normalized keys exist before
    a pipeline stage receives the context.
    """
    base = normalize_build_context(
        prompt,
        project_name=project_name,
        build_mode=build_mode,
        planner_output={},
        scout_output={},
        settings=settings or {},
    )
    supplied = _as_dict(context)
    merged = {**base, **supplied}
    audience = _first_text(
        merged.get("audience"),
        merged.get("target_audience"),
        default=DEFAULT_AUDIENCE,
    )
    merged["audience"] = audience
    merged["target_audience"] = audience
    for key in ["sections", "features", "constraints", "required_files", "integrations"]:
        merged[key] = _as_list(merged.get(key))
    merged["seo_required"] = bool(merged.get("seo_required", base["seo_required"]))
    merged["accessibility_required"] = bool(merged.get("accessibility_required", True))
    merged["preview_required"] = bool(merged.get("preview_required", True))
    return merged


def parse_best_effort_agent_output(value: Any) -> dict[str, Any]:
    """Parse JSON or markdown-ish model output into a dict without raising."""
    return _as_dict(value)
