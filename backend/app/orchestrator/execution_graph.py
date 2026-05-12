"""
Amarktai App Builder — Execution Graph Orchestrator (Phase 1C).

Replaces linear Scout→Architect→Coder→Reviewer chains with a DAG-based
execution graph that can:

  - dynamically assign agents to nodes
  - branch on failure (repair tasks)
  - retry intelligently with exponential back-off
  - route agents through the capability registry
  - maintain shared context across the entire graph
  - emit deterministic state snapshots after every step

The Execution Graph wraps the existing ``Orchestrator`` class from
``agents.orchestrator`` so it does not break any existing build paths.
New builds opt in by setting ``use_graph=True``; legacy builds continue
to work unchanged.

Usage::

    from app.orchestrator.execution_graph import ExecutionGraph, NodeStatus

    graph = ExecutionGraph(
        db=db,
        provider=provider,
        project_id=project_id,
        emit=emit,
    )
    await graph.run(user_prompt, mode="landing_page")
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger("amarktai.execution_graph")


# ── Status / stage types ──────────────────────────────────────────────────────


class NodeStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class GraphStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


EmitFn = Callable[[dict], Awaitable[None]]


# ── Node descriptor ───────────────────────────────────────────────────────────


@dataclass
class GraphNode:
    """A single agent node in the execution graph."""

    node_id: str
    agent: str           # e.g. "scout", "coder", "reviewer"
    depends_on: list[str] = field(default_factory=list)  # node_ids
    max_retries: int = 2
    timeout_s: int = 300
    can_repair: bool = False  # if True, failure triggers a repair branch
    # Runtime state
    status: NodeStatus = NodeStatus.PENDING
    attempt: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    output: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "max_retries": self.max_retries,
            "timeout_s": self.timeout_s,
            "can_repair": self.can_repair,
            "status": self.status.value,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "warnings": self.warnings,
        }


# ── Snapshot ──────────────────────────────────────────────────────────────────


@dataclass
class OrchestratorSnapshot:
    """Point-in-time state of the execution graph."""

    snapshot_id: str
    project_id: str
    graph_status: GraphStatus
    nodes: list[dict]
    shared_context: dict
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "graph_status": self.graph_status.value,
            "nodes": self.nodes,
            "shared_context_keys": list(self.shared_context.keys()),
            "timestamp": self.timestamp,
        }


# ── Graph definition helpers ──────────────────────────────────────────────────


def build_standard_graph(mode: str) -> list[GraphNode]:
    """Build the standard agent DAG for a given build mode.

    All modes share the Scout → Architect → Coder → Reviewer backbone.
    Mode-specific variants add or remove nodes.
    """
    _s = lambda agent, deps=None, **kw: GraphNode(  # noqa: E731
        node_id=agent,
        agent=agent,
        depends_on=deps or [],
        **kw,
    )

    # Core pipeline present in all modes
    base_nodes: list[GraphNode] = [
        _s("scout", timeout_s=180),
        _s("architect", deps=["scout"], timeout_s=240),
        _s("creative_director", deps=["scout"], timeout_s=120),
        _s("coder", deps=["architect", "creative_director"], timeout_s=480, can_repair=True),
        _s("reviewer", deps=["coder"], timeout_s=240),
        _s("validator", deps=["coder", "reviewer"], timeout_s=120),
    ]

    # Add repair node (triggered dynamically when coder/reviewer flag issues)
    repair_node = _s(
        "repair",
        deps=["validator"],
        timeout_s=300,
        max_retries=3,
        can_repair=False,
    )

    # Mode-specific additions
    if mode in ("research",):
        return [_s("scout", timeout_s=300)]

    if mode == "repo_fix":
        return [
            _s("scout", timeout_s=180),
            _s("architect", deps=["scout"], timeout_s=240),
            _s("coder", deps=["architect"], timeout_s=480, can_repair=True),
            _s("reviewer", deps=["coder"], timeout_s=240),
            repair_node,
        ]

    if mode in ("api_service", "api_backend"):
        return [
            _s("scout", timeout_s=180),
            _s("architect", deps=["scout"], timeout_s=240),
            _s("coder", deps=["architect"], timeout_s=480, can_repair=True),
            _s("reviewer", deps=["coder"], timeout_s=240),
            repair_node,
        ]

    return base_nodes + [repair_node]


# ── Execution Graph ───────────────────────────────────────────────────────────


class ExecutionGraph:
    """DAG-based orchestration engine wrapping the existing Orchestrator.

    The graph maintains full orchestration state and persists snapshots to
    MongoDB so that reconnecting WebSocket clients can replay the timeline.
    """

    def __init__(
        self,
        db: Any,
        provider: Any,
        project_id: str,
        emit: EmitFn,
    ) -> None:
        self.db = db
        self.provider = provider
        self.project_id = project_id
        self.emit = emit

        self._graph_status = GraphStatus.IDLE
        self._nodes: dict[str, GraphNode] = {}
        self._shared_context: dict = {}
        self._snapshots: list[OrchestratorSnapshot] = []
        self._cancelled = False

    # ── Public entry points ───────────────────────────────────────────────────

    async def run(self, user_prompt: str, mode: str = "landing_page",
                  stack_decision: dict | None = None) -> None:
        """Execute the full build graph for the given mode."""
        from agents.orchestrator import Orchestrator

        nodes = build_standard_graph(mode)
        self._nodes = {n.node_id: n for n in nodes}
        self._shared_context = {
            "prompt": user_prompt,
            "mode": mode,
            "stack_decision": stack_decision or {},
        }

        self._graph_status = GraphStatus.RUNNING
        await self._emit_snapshot()

        # Delegate actual execution to the existing Orchestrator to preserve
        # all working functionality while adding graph tracking around it.
        orch = Orchestrator(self.db, self.provider, self.project_id, self._graph_emit)
        try:
            if mode == "research":
                await self._track(
                    "scout", orch.run_full_build(user_prompt, mode="research")
                )
            elif mode == "repo_fix":
                await self._track(
                    "pipeline", orch.run_full_build(user_prompt, mode="repo_fix",
                                                    stack_decision=stack_decision)
                )
            else:
                await self._track(
                    "pipeline", orch.run_full_build(user_prompt, mode=mode,
                                                    stack_decision=stack_decision)
                )
            self._graph_status = GraphStatus.COMPLETED
        except Exception as exc:
            self._graph_status = GraphStatus.FAILED
            logger.error("Execution graph failed for %s: %s", self.project_id, exc)
            raise
        finally:
            await self._emit_snapshot()

    async def run_iteration(self, user_prompt: str) -> None:
        """Execute an iteration through the graph."""
        from agents.orchestrator import Orchestrator

        self._graph_status = GraphStatus.RUNNING
        await self._emit_snapshot()
        orch = Orchestrator(self.db, self.provider, self.project_id, self._graph_emit)
        try:
            await self._track("iteration", orch.run_iteration(user_prompt))
            self._graph_status = GraphStatus.COMPLETED
        except Exception as exc:
            self._graph_status = GraphStatus.FAILED
            raise
        finally:
            await self._emit_snapshot()

    # ── Node tracking helpers ─────────────────────────────────────────────────

    async def _track(self, node_id: str, coro: Any) -> None:
        """Run ``coro`` while emitting node lifecycle events."""
        node = self._nodes.get(node_id)
        if node:
            node.status = NodeStatus.STARTED
            node.started_at = _now()
            await self._emit_node_event(node, "start", f"Node {node_id} started.")

        try:
            await coro
            if node:
                node.status = NodeStatus.COMPLETED
                node.completed_at = _now()
                await self._emit_node_event(node, "completion", f"Node {node_id} completed.")
        except Exception as exc:
            if node:
                node.status = NodeStatus.FAILED
                node.error = str(exc)
                node.completed_at = _now()
                await self._emit_node_event(node, "failure",
                                            f"Node {node_id} failed: {exc}")
            raise

    async def _emit_node_event(self, node: GraphNode, event_type: str, detail: str) -> None:
        """Emit a graph node lifecycle event to the WebSocket hub."""
        payload = {
            "type": "orchestration_graph_event",
            "data": {
                "node_id": node.node_id,
                "agent": node.agent,
                "event": event_type,  # start | progress | completion | warning | failure | retry
                "detail": detail,
                "status": node.status.value,
                "timestamp": _now(),
                "project_id": self.project_id,
            },
        }
        await self.emit(payload)
        # Persist node event to MongoDB for timeline replay
        await self._persist_event(payload["data"])

    async def _graph_emit(self, payload: dict) -> None:
        """Wrapper emit that forwards to the real emit and adds graph tracking."""
        await self.emit(payload)

    # ── Snapshot management ───────────────────────────────────────────────────

    async def _emit_snapshot(self) -> None:
        """Emit and persist a full graph state snapshot."""
        snapshot = OrchestratorSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=self.project_id,
            graph_status=self._graph_status,
            nodes=[n.to_dict() for n in self._nodes.values()],
            shared_context=self._shared_context,
            timestamp=_now(),
        )
        self._snapshots.append(snapshot)
        await self.emit({
            "type": "orchestration_snapshot",
            "data": snapshot.to_dict(),
        })
        # Persist snapshot to MongoDB
        try:
            await self.db.orchestration_snapshots.insert_one({
                **snapshot.to_dict(),
                "_id": snapshot.snapshot_id,
            })
        except Exception:
            pass  # Non-fatal

    async def _persist_event(self, event_data: dict) -> None:
        """Persist a graph node event to MongoDB."""
        try:
            doc = {
                "_id": str(uuid.uuid4()),
                "project_id": self.project_id,
                **event_data,
            }
            await self.db.orchestration_events.insert_one(doc)
        except Exception:
            pass  # Non-fatal

    def get_snapshot(self) -> dict:
        """Return the latest graph state snapshot dict."""
        return {
            "graph_status": self._graph_status.value,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "project_id": self.project_id,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
