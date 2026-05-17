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
    "video_generation": {
        "required_caps": ["video"],
        "preferred_caps": [],
        "preferred_models": ["kling-avatar-v2-pro", "veo-3", "kling-v2"],
        "cost_tier": "medium",
        "description": "Video generation and image-to-video media",
    },
    "avatar_generation": {
        "required_caps": ["avatar_generation", "video"],
        "preferred_caps": ["audio_image_to_video"],
        "preferred_models": ["kling-avatar-v2-pro"],
        "cost_tier": "high",
        "description": "Avatar video generation from image and audio",
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


AGENT_TASK_MAP: dict[str, str] = {
    "manager": "general",
    "prompt_optimizer": "research",
    "planner": "research",
    "scout": "research",
    "product_strategist": "research",
    "creative_director": "frontend_design",
    "architect": "backend_architecture",
    "ux_architect": "frontend_design",
    "ui_designer": "frontend_design",
    "coder": "frontend_design",
    "frontend_coder": "frontend_design",
    "backend_coder": "backend_architecture",
    "data_architect": "backend_architecture",
    "tool_integration": "backend_architecture",
    "component_librarian": "frontend_design",
    "media_director": "image_generation",
    "motion_3d": "frontend_design",
    "reviewer": "qa_security_accessibility",
    "visual_qa": "qa_security_accessibility",
    "accessibility": "qa_security_accessibility",
    "seo_performance": "qa_security_accessibility",
    "security": "qa_security_accessibility",
    "runtime_engineer": "qa_security_accessibility",
    "deployment": "documentation",
    "documentation": "documentation",
    "repo_engineer": "repo_audit",
    "repo_analyzer": "repo_audit",
    "repair_agent": "code_repair",
    "test_runner": "qa_security_accessibility",
    "github_pr_agent": "repo_audit",
    "export_agent": "documentation",
    "memory_curator": "documentation",
    "advisor": "general",
    "capability_truth": "general",
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
    """Return routing decisions for all task types and registered agent roles."""
    task_routes = {task: route_task(task, available_models) for task in TASK_ROUTING}
    agent_routes: dict[str, Any] = {}
    for agent, task_type in AGENT_TASK_MAP.items():
        spec = TASK_ROUTING.get(task_type, TASK_ROUTING["general"])
        standard = route_task(task_type, available_models)
        premium = route_task(task_type, available_models)
        if available_models:
            for preferred in spec.get("preferred_models", []):
                if preferred in available_models:
                    premium = {**premium, "selected_model": preferred, "fallback_used": False}
                    break
        agent_routes[agent] = {
            "agent": agent,
            "task_type": task_type,
            "selected_standard_model": standard.get("selected_model"),
            "selected_premium_model": premium.get("selected_model"),
            "required_capabilities": spec.get("required_caps", []),
            "preferred_capabilities": spec.get("preferred_caps", []),
            "available": bool(standard.get("selected_model")),
            "fallback_status": "fallback" if standard.get("fallback_used") else "preferred",
            "reason": standard.get("reason"),
        }
    return {
        **task_routes,
        "tasks": task_routes,
        "agents": agent_routes,
    }
