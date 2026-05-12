"""
Project Memory package — Phase 1B.

Re-exports the canonical memory helpers from ``agents.project_memory``
and adds the extended schema fields required by Phase 1B.

Any module that needs project memory should import from here going forward::

    from app.core.project_memory import (
        make_empty_memory,
        load_memory,
        save_memory,
        ...
    )
"""
from __future__ import annotations

# Re-export everything from the canonical implementation so callers that
# already import from ``agents.project_memory`` continue to work unchanged.
from agents.project_memory import (  # noqa: F401  (re-export)
    make_empty_memory,
    load_memory,
    save_memory,
    update_memory_brand,
    update_memory_design,
    update_memory_product,
    update_memory_pages,
    update_memory_features,
    update_memory_iteration,
    update_memory_agent_decision,
    mark_issue_resolved,
    add_unresolved_issue,
    get_design_tokens,
    get_font_pair,
    get_design_direction_summary,
    get_design_lock_prompt,
)

# ── Phase 1B extensions ───────────────────────────────────────────────────────


def record_accepted_task(memory: dict, task: str, iteration_id: str = "") -> dict:
    """Mark a task as accepted in project memory.

    Accepted tasks are changes the user confirmed as good and wants preserved
    across future iterations.
    """
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)
    accepted = memory.get("acceptedTasks", [])
    entry = {"task": task, "iteration_id": iteration_id}
    if entry not in accepted:
        accepted.append(entry)
    memory["acceptedTasks"] = accepted
    return memory


def record_rejected_task(memory: dict, task: str, iteration_id: str = "",
                          reason: str = "") -> dict:
    """Mark a task as rejected in project memory.

    Rejected tasks are things the user explicitly asked not to do again.
    """
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)
    rejected = memory.get("rejectedTasks", [])
    entry = {"task": task, "iteration_id": iteration_id, "reason": reason}
    if entry not in rejected:
        rejected.append(entry)
    memory["rejectedTasks"] = rejected
    return memory


def set_design_archetype(memory: dict, archetype: str) -> dict:
    """Store the chosen design archetype (e.g. 'editorial-luxury', 'bold-tech').

    The archetype is part of the design identity lock — it must not change
    between iterations unless the user explicitly requests a redesign.
    """
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)
    memory["designArchetype"] = archetype
    # Also mirror into design.visualDirection if it is not yet set
    if not memory.get("design", {}).get("visualDirection"):
        memory.setdefault("design", {})["visualDirection"] = archetype
    return memory


def get_rejected_tasks(memory: dict) -> list[dict]:
    """Return all rejected tasks from project memory."""
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)
    return memory.get("rejectedTasks", [])


def get_accepted_tasks(memory: dict) -> list[dict]:
    """Return all accepted tasks from project memory."""
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)
    return memory.get("acceptedTasks", [])


def build_task_constraint_prompt(memory: dict) -> str:
    """Build a prompt block that tells iteration agents what to preserve and avoid.

    Injects:
      - Accepted tasks (must keep)
      - Rejected tasks (must NOT do)
    """
    from agents.project_memory import _ensure_schema
    memory = _ensure_schema(memory)

    accepted = get_accepted_tasks(memory)
    rejected = get_rejected_tasks(memory)

    lines: list[str] = []

    if accepted:
        lines.append("PRESERVED DECISIONS (user has accepted these — keep them):")
        for item in accepted[-10:]:  # cap to last 10 to stay within context
            lines.append(f"  ✓ {item['task']}")
        lines.append("")

    if rejected:
        lines.append("REJECTED REQUESTS (user explicitly said NO — never do these):")
        for item in rejected[-10:]:
            reason = f" ({item['reason']})" if item.get("reason") else ""
            lines.append(f"  ✗ {item['task']}{reason}")
        lines.append("")

    return "\n".join(lines)
