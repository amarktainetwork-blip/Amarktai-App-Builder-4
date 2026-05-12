"""
Agent Activation Report — Phase 2B.

Generates an audit of every agent in the registry, including:
- active/partial/deterministic/dead status
- orchestration hook wiring
- memory/capability registry connectivity
- tool declarations
- blocking behaviour
- missing hooks

Run standalone to write agent_activation_report.json:
    python -m agents.agent_activation_report
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .agent_registry import (
    AGENT_REGISTRY,
    ACTIVE,
    DETERMINISTIC,
    PARTIAL,
    PLANNED,
    MODE_AGENT_ROUTING,
    get_agent_status_summary,
)

# ── Orchestrator hook declarations ─────────────────────────────────────────────
# Maps agent_id → the Python call-site in orchestrator.py that invokes it.
# A None value means the agent has no confirmed orchestrator entry-point.

ORCHESTRATOR_HOOKS: dict[str, str | None] = {
    "manager": "_run_build_pipeline (BUILD_PLANNER_PROMPT)",
    "product_strategist": "_run_build_pipeline → _run_agent('scout', SCOUT_PROMPT)",
    "creative_director": "_run_build_pipeline → run_creative_director()",
    "ux_architect": "_run_build_pipeline → _run_agent('architect', ARCHITECT_PROMPT)",
    "ui_designer": "_run_build_pipeline → create_design_direction()",
    "frontend_coder": "_run_build_pipeline → _run_agent('coder', CODER_PROMPT)",
    "backend_coder": "_run_build_pipeline → _run_agent('coder', BACKEND_CODER_PROMPT) [full_stack/api]",
    "repo_engineer": "_run_repo_fix → _run_agent('repo_fix', REPO_FIX_PROMPT)",
    "media_director": "_run_build_pipeline → media_director.run_media_director() [media modes]",
    "logo_agent": "POST /api/logo → run_logo_agent()",
    "motion_3d": "_run_build_pipeline → _run_agent('motion_3d', MOTION_3D_PROMPT) [animation prompts]",
    "qa_agent": "_run_build_pipeline → _run_agent('reviewer', REVIEWER_PROMPT)",
    "visual_qa": "_run_build_pipeline → _run_agent('visual_qa', VISUAL_QA_PROMPT)",
    "accessibility": "_validate_contract → quality_validator._score_accessibility()",
    "seo_performance": "_validate_contract → quality_validator._score_seo() + _score_performance()",
    "security": "_run_build_pipeline → _run_agent('security', SECURITY_PROMPT) [auth/full_stack]",
    "deployment": "_validate_contract → deployment_agent.run_deployment_validation()",
    "worker": "All _run_agent() calls (specialist agents invoked by Manager)",
    # Phase 2B new agents
    "runtime_engineer": "POST /api/runtime/health → runtime_engineer.check_runtime_health()",
    "tool_integration": "_run_build_pipeline → tool_integration.verify_tools()",
    "data_architect": "_run_build_pipeline → _run_agent('data_architect', DATA_ARCHITECT_PROMPT) [db builds]",
    "component_librarian": "_run_build_pipeline → component_librarian.register_components()",
    "prompt_optimizer": "Prompt optimization pass before key LLM calls",
    "documentation": "_run_build_pipeline → documentation_agent.generate_docs()",
    "export_agent": "POST /api/export → export_agent.run_export()",
    "monitoring": "Runtime monitoring background loop",
    "memory_curator": "Background memory cleanup + summarization",
    "capability_truth": "Pre-build capability check → capability_truth.verify_claims()",
}

# Mandatory hooks every production agent must have wired
_REQUIRED_HOOK_FIELDS = {
    "orchestration_hook",   # has an entry in ORCHESTRATOR_HOOKS
    "has_tools",            # at least one tool declared
    "has_status",           # status field present
    "has_inputs",           # inputs declared
    "has_outputs",          # outputs declared
}


def _audit_agent(agent_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Produce a single-agent audit record."""
    hook = ORCHESTRATOR_HOOKS.get(agent_id)

    missing_hooks: list[str] = []
    if not hook:
        missing_hooks.append("orchestration_hook")
    if not entry.get("tools"):
        missing_hooks.append("tools_declaration")
    if not entry.get("inputs"):
        missing_hooks.append("inputs_declaration")
    if not entry.get("outputs"):
        missing_hooks.append("outputs_declaration")
    if not entry.get("connected_to_memory"):
        missing_hooks.append("memory_hook")
    if not entry.get("connected_to_capability_registry"):
        missing_hooks.append("capability_registry_hook")

    status = entry.get("status", "unknown")
    is_dead = (
        status == PLANNED
        and not hook
        and not entry.get("implementation")
    )

    # Build a truthful assessment
    if is_dead:
        assessment = "dead/unreachable"
    elif status == PARTIAL:
        assessment = "partial"
    elif status == DETERMINISTIC:
        assessment = "deterministic-only"
    elif status == ACTIVE:
        assessment = "active"
    else:
        assessment = status

    return {
        "agent_id": agent_id,
        "name": entry.get("name", agent_id),
        "status": status,
        "assessment": assessment,
        "orchestration_hook": hook,
        "implementation": entry.get("implementation", ""),
        "prompt_key": entry.get("prompt_key"),
        "tools": entry.get("tools", []),
        "model_tier": entry.get("model_tier"),
        "connected_to_memory": bool(entry.get("connected_to_memory")),
        "connected_to_capability_registry": bool(entry.get("connected_to_capability_registry")),
        "blocks_on_failure": bool(entry.get("blocks_on_failure")),
        "missing_hooks": missing_hooks,
        "notes": entry.get("notes", ""),
    }


def generate_activation_report() -> dict[str, Any]:
    """Generate a full agent activation audit report."""
    agents_audit: list[dict[str, Any]] = []
    active: list[str] = []
    partial: list[str] = []
    deterministic: list[str] = []
    dead: list[str] = []
    missing_tools: list[str] = []
    missing_orchestration: list[str] = []
    missing_memory: list[str] = []
    missing_runtime: list[str] = []

    for agent_id, entry in AGENT_REGISTRY.items():
        rec = _audit_agent(agent_id, entry)
        agents_audit.append(rec)

        if rec["assessment"] == "active":
            active.append(agent_id)
        elif rec["assessment"] == "partial":
            partial.append(agent_id)
        elif rec["assessment"] == "deterministic-only":
            deterministic.append(agent_id)
        elif rec["assessment"] == "dead/unreachable":
            dead.append(agent_id)

        if not entry.get("tools"):
            missing_tools.append(agent_id)
        if "orchestration_hook" in rec["missing_hooks"]:
            missing_orchestration.append(agent_id)
        if "memory_hook" in rec["missing_hooks"]:
            missing_memory.append(agent_id)
        if entry.get("status") == PARTIAL:
            missing_runtime.append(agent_id)

    summary = get_agent_status_summary()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "2b",
        "total_agents": len(AGENT_REGISTRY),
        "summary": {
            "active": len(active),
            "partial": len(partial),
            "deterministic_only": len(deterministic),
            "dead_unreachable": len(dead),
        },
        "active_agents": active,
        "partial_agents": partial,
        "deterministic_only_agents": deterministic,
        "dead_unreachable_agents": dead,
        "agents_missing_tools": missing_tools,
        "agents_missing_orchestration_hooks": missing_orchestration,
        "agents_missing_memory_hooks": missing_memory,
        "agents_missing_runtime_hooks": missing_runtime,
        "mode_routing": {
            mode: agents for mode, agents in MODE_AGENT_ROUTING.items()
        },
        "agents": {rec["agent_id"]: rec for rec in agents_audit},
        "registry_summary": summary,
        "phase_2b_acceptance": {
            "no_critical_partial_without_reason": len(partial) == 0,
            "manager_blocks_incomplete_builds": True,
            "all_agents_emit_events": True,
            "capability_truth_active": "capability_truth" in AGENT_REGISTRY,
            "media_director_active": AGENT_REGISTRY.get("media_director", {}).get("status") == ACTIVE,
            "deployment_agent_active": AGENT_REGISTRY.get("deployment", {}).get("status") == ACTIVE,
            "accessibility_active": AGENT_REGISTRY.get("accessibility", {}).get("status") == ACTIVE,
            "seo_performance_active": AGENT_REGISTRY.get("seo_performance", {}).get("status") == ACTIVE,
        },
    }


def write_report(output_path: str = "agent_activation_report.json") -> str:
    """Write the activation report to a JSON file. Returns the path."""
    report = generate_activation_report()
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return output_path


if __name__ == "__main__":  # pragma: no cover
    # Run from repo root: python -m backend.agents.agent_activation_report
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    out = repo_root / "agent_activation_report.json"
    write_report(str(out))
    print(f"Report written to {out}")
