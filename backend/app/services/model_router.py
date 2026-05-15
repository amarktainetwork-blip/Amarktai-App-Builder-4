"""
Amarktai App Builder — Intelligent Model Router.

Routes agent tasks to the best available model based on task type,
capability requirements, and available providers.

Returns a structured routing decision including:
  - selected_model
  - selected_provider
  - reason
  - fallback_used
  - missing_best_model_reason
  - estimated_cost_tier
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("amarktai.model_router")

# ── Task → Capability requirements ───────────────────────────────────────────

TASK_ROUTING: dict[str, dict[str, Any]] = {
    "code_repair": {
        "required_caps": ["coding"],
        "preferred_caps": ["reasoning", "tool_use"],
        "preferred_models": ["claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4.1", "qwen3-coder-plus"],
        "cost_tier": "medium",
        "description": "Code repair and refactoring",
    },
    "repo_audit": {
        "required_caps": ["coding"],
        "preferred_caps": ["long_context", "reasoning"],
        "preferred_models": ["claude-sonnet-4-6", "gemini-2.5-pro", "gpt-4.1"],
        "cost_tier": "high",
        "description": "Repo audit and analysis",
    },
    "frontend_design": {
        "required_caps": ["reasoning"],
        "preferred_caps": ["vision", "coding"],
        "preferred_models": ["claude-sonnet-4-6", "gemini-2.5-pro", "gpt-5"],
        "cost_tier": "high",
        "description": "Frontend design with optional visual reasoning",
    },
    "backend_architecture": {
        "required_caps": ["reasoning", "coding"],
        "preferred_caps": ["tool_use"],
        "preferred_models": ["claude-sonnet-4-6", "gpt-4.1", "deepseek-v3"],
        "cost_tier": "high",
        "description": "Backend architecture planning",
    },
    "image_generation": {
        "required_caps": ["image"],
        "preferred_caps": [],
        "preferred_models": ["qwen-image-plus"],
        "cost_tier": "medium",
        "description": "Image generation",
    },
    "audio_voice": {
        "required_caps": ["audio"],
        "preferred_caps": [],
        "preferred_models": ["qwen3-asr-flash", "qwen3-omni-flash"],
        "cost_tier": "medium",
        "description": "Audio / voice processing",
    },
    "research": {
        "required_caps": ["text"],
        "preferred_caps": ["reasoning", "long_context"],
        "preferred_models": ["gemini-2.5-flash", "claude-haiku-4-5", "gpt-4.1-mini"],
        "cost_tier": "low",
        "description": "Research and information gathering",
    },
    "qa_security_accessibility": {
        "required_caps": ["reasoning"],
        "preferred_caps": ["coding"],
        "preferred_models": ["claude-sonnet-4-6", "gpt-4.1", "gemini-2.5-pro"],
        "cost_tier": "medium",
        "description": "QA, security, and accessibility checks",
    },
    "documentation": {
        "required_caps": ["text"],
        "preferred_caps": [],
        "preferred_models": ["claude-haiku-4-5", "gemini-2.5-flash", "gpt-4.1-mini"],
        "cost_tier": "low",
        "description": "Documentation generation",
    },
    "large_repo": {
        "required_caps": ["long_context"],
        "preferred_caps": ["coding", "reasoning"],
        "preferred_models": ["gemini-2.5-pro", "claude-sonnet-4-6", "qwen-long-latest"],
        "cost_tier": "high",
        "description": "Large repository analysis requiring long context",
    },
    "general": {
        "required_caps": ["text"],
        "preferred_caps": ["reasoning"],
        "preferred_models": ["claude-sonnet-4-6", "gemini-2.5-flash", "gpt-4.1-mini"],
        "cost_tier": "low",
        "description": "General purpose task",
    },
}


def route_task(
    task_type: str,
    available_models: list[str],
    provider: str = "genx",
    has_screenshots: bool = False,
    repo_size_files: int = 0,
) -> dict[str, Any]:
    """
    Select the best model for the given task type.

    Parameters
    ----------
    task_type : str
        One of the task types in TASK_ROUTING.
    available_models : list[str]
        The models currently available (from live registry or static fallback).
    provider : str
        The provider to use (genx, qwen).
    has_screenshots : bool
        If True, prefer vision-capable models for frontend tasks.
    repo_size_files : int
        Number of files in the repo; triggers long_context preference if large.

    Returns
    -------
    dict with: selected_model, selected_provider, reason, fallback_used,
               missing_best_model_reason, estimated_cost_tier
    """
    # Auto-upgrade task type based on context
    if task_type == "frontend_design" and has_screenshots:
        task_type = "frontend_design"  # already prefers vision
    if task_type in ("repo_audit", "code_repair") and repo_size_files > 500:
        task_type = "large_repo"

    spec = TASK_ROUTING.get(task_type, TASK_ROUTING["general"])
    preferred = spec["preferred_models"]

    fallback_used = False
    missing_reason: str | None = None

    # Try preferred models first
    for model in preferred:
        if model in available_models:
            return {
                "selected_model": model,
                "selected_provider": provider,
                "task_type": task_type,
                "reason": f"Best model for {task_type}: {model} is available",
                "fallback_used": False,
                "missing_best_model_reason": None,
                "estimated_cost_tier": spec["cost_tier"],
                "description": spec["description"],
            }

    # None of the preferred models are available — pick any with required capability
    if available_models:
        selected = available_models[0]
        if task_type == "image_generation":
            selected = next((m for m in available_models if any(token in m.lower() for token in ("image", "flux", "dall", "stable", "midjourney", "ideogram"))), selected)
        elif task_type == "audio_voice":
            selected = next((m for m in available_models if any(token in m.lower() for token in ("audio", "voice", "tts", "asr", "omni"))), selected)
        missing_reason = f"None of the preferred models {preferred} were available; using {selected}"
        return {
            "selected_model": selected,
            "selected_provider": provider,
            "task_type": task_type,
            "reason": f"Fallback model for {task_type}",
            "fallback_used": True,
            "missing_best_model_reason": missing_reason,
            "estimated_cost_tier": spec["cost_tier"],
            "description": spec["description"],
        }

    # No models at all
    return {
        "selected_model": None,
        "selected_provider": None,
        "task_type": task_type,
        "reason": "No models available",
        "fallback_used": True,
        "missing_best_model_reason": "No models available in registry",
        "estimated_cost_tier": spec["cost_tier"],
        "description": spec["description"],
    }


def get_router_status(available_models: list[str]) -> dict[str, Any]:
    """Return routing decisions for all task types given the available models."""
    return {
        task: route_task(task, available_models)
        for task in TASK_ROUTING
    }
