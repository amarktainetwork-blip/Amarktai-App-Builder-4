from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any


IDEA_BUILDER_SYSTEM_PROMPT = """You are Amarktai Idea Builder.
Help the user turn a rough idea into a clear build prompt for Amarktai App Builder.
Ask concise product, audience, workflow, design, data, integrations, and launch-readiness questions.
When enough context exists, produce a production-ready build prompt with:
- product name and audience
- build type
- goals
- required pages or screens
- key workflows
- visual style
- data/integrations
- quality, accessibility, and preview expectations
Do not claim external providers are available. Say when media/research/PR work depends on configured capabilities."""


DEFAULT_MODE = "website"
VALID_MODES = {
    "landing_page",
    "website",
    "web_app",
    "pwa",
    "dashboard",
    "full_stack",
    "api_service",
    "repo_fix",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_mode(mode: str | None) -> str:
    value = (mode or DEFAULT_MODE).lower().strip()
    return value if value in VALID_MODES else DEFAULT_MODE


def make_session_doc(owner_id: str, seed_prompt: str = "", mode: str | None = None) -> dict[str, Any]:
    normalized_mode = normalize_mode(mode)
    messages: list[dict[str, Any]] = []
    seed = (seed_prompt or "").strip()
    if seed:
        messages.append(make_message("user", seed))
        messages.append(make_message("assistant", deterministic_reply(messages, normalized_mode)))
    return {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "mode": normalized_mode,
        "status": "active",
        "messages": messages,
        "final_prompt": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def make_message(role: str, content: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": (content or "").strip(),
        "created_at": utc_now(),
    }


def model_user_message(messages: list[dict[str, Any]], mode: str) -> str:
    transcript = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in messages[-12:]
    )
    return (
        f"Build mode: {normalize_mode(mode)}\n"
        "Conversation transcript:\n"
        f"{transcript}\n\n"
        "Reply as the Idea Builder. Ask the next best question or summarize the refined build direction."
    )


def deterministic_reply(messages: list[dict[str, Any]], mode: str) -> str:
    """Deterministic fallback when a model is unavailable.

    The fallback keeps the chat useful and testable without faking model-backed work.
    """
    user_text = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    ideas = _keywords(user_text)
    inferred = ", ".join(ideas[:5]) if ideas else "your product idea"
    mode_label = normalize_mode(mode).replace("_", " ")
    question = _next_question(user_text)
    return (
        f"I can shape this into a {mode_label} build. I am tracking: {inferred}. "
        f"{question} Once those details are clear, I can generate a polished build prompt for the main pipeline."
    )


def normalize_model_reply(model_text: str | None, messages: list[dict[str, Any]], mode: str) -> str:
    text = (model_text or "").strip()
    if not text:
        return deterministic_reply(messages, mode)
    return text[:4000]


def compose_final_prompt(
    messages: list[dict[str, Any]],
    mode: str,
    project_name: str | None = None,
    model_text: str | None = None,
) -> str:
    text = (model_text or "").strip()
    if text and len(text) >= 120:
        return text[:12000]

    user_messages = [m.get("content", "") for m in messages if m.get("role") == "user"]
    combined = "\n".join(user_messages).strip()
    keywords = _keywords(combined)
    name = (project_name or _infer_project_name(combined) or "Amarktai-built Product").strip()
    normalized_mode = normalize_mode(mode)
    audience = _infer_audience(combined)
    style = _infer_style(combined)
    features = keywords[:8] or ["clear value proposition", "polished user experience", "responsive preview"]

    return (
        f"Create a premium production-ready {normalized_mode.replace('_', ' ')} for \"{name}\".\n\n"
        f"Audience: {audience}.\n\n"
        f"Goal:\nTurn this idea into a launch-ready digital experience: {combined or 'a refined product concept'}.\n\n"
        f"Style:\n{style}. Use strong hierarchy, responsive layout, accessible interactions, polished copy, and motion where appropriate.\n\n"
        "Required content and workflows:\n"
        + "\n".join(f"- {feature.capitalize()}" for feature in features)
        + "\n\nTechnical requirements:\n"
        "- Generate working files with complete HTML/CSS/JS or the appropriate app structure.\n"
        "- Include real copy, semantic markup, responsive CSS, no lorem ipsum, no dead CTAs, and graceful media fallbacks.\n"
        "- Produce a preview and quality report.\n"
    )


def final_model_user_message(messages: list[dict[str, Any]], mode: str, project_name: str | None) -> str:
    transcript = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in messages[-16:]
    )
    return (
        f"Project name hint: {project_name or 'not supplied'}\n"
        f"Build mode: {normalize_mode(mode)}\n"
        "Conversation transcript:\n"
        f"{transcript}\n\n"
        "Return one final production-ready build prompt only. Do not include chat narration."
    )


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "build",
        "create", "need", "want", "app", "site", "website", "user", "users",
    }
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word in stop or word in seen:
            continue
        seen.add(word)
        result.append(word.replace("-", " "))
    return result


def _next_question(text: str) -> str:
    lower = text.lower()
    if "audience" not in lower and "for " not in lower:
        return "Who is the primary audience and what painful job should it solve for them?"
    if not any(w in lower for w in ("style", "look", "feel", "brand", "visual")):
        return "What should it look and feel like visually?"
    if not any(w in lower for w in ("section", "screen", "page", "workflow", "feature")):
        return "Which screens, sections, or workflows are mandatory for version one?"
    return "What should make this feel unusually premium or differentiated?"


def _infer_project_name(text: str) -> str | None:
    quoted = re.search(r"[\"']([^\"']{2,80})[\"']", text)
    if quoted:
        return quoted.group(1)
    called = re.search(r"(?:called|named)\s+([A-Z][A-Za-z0-9 ]{2,60})", text)
    return called.group(1).strip() if called else None


def _infer_audience(text: str) -> str:
    lower = text.lower()
    if "founder" in lower or "startup" in lower:
        return "founders, startups, agencies, product teams, and businesses"
    if "developer" in lower:
        return "developers, technical teams, and software-led businesses"
    if "admin" in lower or "dashboard" in lower:
        return "operators, admins, analysts, and decision makers"
    return "founders, agencies, product teams, startups, and businesses"


def _infer_style(text: str) -> str:
    lower = text.lower()
    if "luxury" in lower or "cinematic" in lower:
        return "Dark luxury, cinematic lighting, refined glass surfaces, premium typography, and tasteful motion"
    if "playful" in lower:
        return "Bright, approachable, polished, and energetic without looking generic"
    if "minimal" in lower:
        return "Minimal, calm, high-trust, spacious, and editorial"
    return "Modern premium SaaS, strong contrast, clean spacing, professional components, and subtle animation"
