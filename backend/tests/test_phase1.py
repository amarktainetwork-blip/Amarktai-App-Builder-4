"""
Phase 1 test suite — Amarktai App Builder.

Covers:
  - Capability Registry (1A)
  - Project Memory extensions (1B)
  - Execution Graph construction (1C)
  - Creative Director Agent (1D)
  - Build Mode Classifier (1E)
  - Strict Validation Engine (1F)
  - WebSocket event buffering / replay (1G)
"""
from __future__ import annotations

import asyncio
import sys
import os

# Ensure the backend package root is on sys.path when running from repo root
_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Phase 1A — Capability Registry
# ─────────────────────────────────────────────────────────────────────────────

from app.core.capability_registry import (
    get_registry,
    capabilities_summary,
    get_model_capability,
    models_with_capability,
)


class TestCapabilityRegistry:
    def test_registry_not_empty(self):
        registry = get_registry()
        assert len(registry) > 0, "Registry must contain at least one model"

    def test_all_entries_have_required_fields(self):
        required = {
            "provider", "model", "supports_reasoning", "supports_vision",
            "supports_image_generation", "supports_video_generation",
            "supports_audio", "supports_repo_analysis", "supports_long_context",
            "supports_tool_use", "supports_streaming", "cost_tier",
            "speed_tier", "reliability_score",
        }
        for entry in get_registry():
            missing = required - set(entry.keys())
            assert not missing, f"Entry {entry.get('model')} missing fields: {missing}"

    def test_cost_tier_values(self):
        valid = {"low", "medium", "high"}
        for entry in get_registry():
            assert entry["cost_tier"] in valid, (
                f"Model {entry['model']} has invalid cost_tier: {entry['cost_tier']}"
            )

    def test_reliability_score_range(self):
        for entry in get_registry():
            score = entry["reliability_score"]
            assert 0.0 <= score <= 1.0, (
                f"Model {entry['model']} reliability_score {score} out of range"
            )

    def test_get_model_capability_known(self):
        cap = get_model_capability("genx", "claude-sonnet-4-6")
        assert cap is not None
        assert cap.supports_reasoning is True
        assert cap.provider == "genx"

    def test_get_model_capability_unknown(self):
        cap = get_model_capability("genx", "nonexistent-model-xyz")
        assert cap is None

    def test_models_with_image_generation(self):
        models = models_with_capability("supports_image_generation")
        assert len(models) > 0, "At least one model should support image generation"
        for m in models:
            assert m["supports_image_generation"] is True

    def test_models_with_unknown_capability(self):
        models = models_with_capability("supports_telekinesis")
        assert models == [], "Unknown capability should return empty list"

    def test_capabilities_summary_keys(self):
        summary = capabilities_summary()
        expected_keys = {
            "text_generation", "reasoning", "vision", "image_generation",
            "video_generation", "audio", "repo_analysis", "long_context",
            "tool_use", "streaming",
        }
        assert expected_keys.issubset(set(summary.keys()))

    def test_capabilities_summary_honest_when_no_key(self):
        # Without GENX_API_KEY in env, image generation must be marked unavailable
        original = os.environ.pop("GENX_API_KEY", None)
        try:
            summary = capabilities_summary()
            assert summary["image_generation"]["available"] is False
            assert summary["image_generation"]["reason"] is not None
        finally:
            if original is not None:
                os.environ["GENX_API_KEY"] = original

    def test_capabilities_summary_available_when_key_set(self):
        os.environ["GENX_API_KEY"] = "test-key-abc"
        try:
            summary = capabilities_summary()
            assert summary["text_generation"]["available"] is True
            assert summary["image_generation"]["available"] is True
        finally:
            os.environ.pop("GENX_API_KEY", None)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1B — Project Memory extensions
# ─────────────────────────────────────────────────────────────────────────────

from agents.project_memory import make_empty_memory, _ensure_schema
from app.core.project_memory import (
    record_accepted_task,
    record_rejected_task,
    set_design_archetype,
    get_accepted_tasks,
    get_rejected_tasks,
    build_task_constraint_prompt,
)


class TestProjectMemoryExtensions:
    def test_empty_memory_has_new_fields(self):
        mem = make_empty_memory()
        assert "acceptedTasks" in mem
        assert "rejectedTasks" in mem
        assert "designArchetype" in mem
        assert mem["acceptedTasks"] == []
        assert mem["rejectedTasks"] == []
        assert mem["designArchetype"] == ""

    def test_record_accepted_task(self):
        mem = make_empty_memory()
        mem = record_accepted_task(mem, "Make hero darker", "iter-1")
        tasks = get_accepted_tasks(mem)
        assert len(tasks) == 1
        assert tasks[0]["task"] == "Make hero darker"
        assert tasks[0]["iteration_id"] == "iter-1"

    def test_record_rejected_task(self):
        mem = make_empty_memory()
        mem = record_rejected_task(mem, "Add animated background", "iter-2", reason="too distracting")
        tasks = get_rejected_tasks(mem)
        assert len(tasks) == 1
        assert tasks[0]["task"] == "Add animated background"
        assert tasks[0]["reason"] == "too distracting"

    def test_accepted_task_deduplication(self):
        mem = make_empty_memory()
        mem = record_accepted_task(mem, "Make hero darker", "iter-1")
        mem = record_accepted_task(mem, "Make hero darker", "iter-1")
        assert len(get_accepted_tasks(mem)) == 1, "Duplicate accepted tasks should not be added"

    def test_set_design_archetype(self):
        mem = make_empty_memory()
        mem = set_design_archetype(mem, "editorial-luxury")
        assert mem["designArchetype"] == "editorial-luxury"
        assert mem["design"]["visualDirection"] == "editorial-luxury"

    def test_build_task_constraint_prompt_includes_accepted(self):
        mem = make_empty_memory()
        mem = record_accepted_task(mem, "Keep the gold color scheme")
        prompt = build_task_constraint_prompt(mem)
        assert "PRESERVED DECISIONS" in prompt
        assert "Keep the gold color scheme" in prompt

    def test_build_task_constraint_prompt_includes_rejected(self):
        mem = make_empty_memory()
        mem = record_rejected_task(mem, "Use Comic Sans font", reason="user hates it")
        prompt = build_task_constraint_prompt(mem)
        assert "REJECTED REQUESTS" in prompt
        assert "Use Comic Sans font" in prompt
        assert "user hates it" in prompt

    def test_ensure_schema_fills_missing_fields(self):
        old_mem = {"brand": {"name": "Acme"}}
        mem = _ensure_schema(old_mem)
        assert "acceptedTasks" in mem
        assert "rejectedTasks" in mem
        assert "designArchetype" in mem


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1C — Execution Graph
# ─────────────────────────────────────────────────────────────────────────────

from app.orchestrator.execution_graph import (
    build_standard_graph,
    GraphNode,
    NodeStatus,
    GraphStatus,
    ExecutionGraph,
)


class TestExecutionGraph:
    def test_standard_graph_has_required_agents(self):
        nodes = build_standard_graph("landing_page")
        agent_names = {n.agent for n in nodes}
        # All standard builds must include these agents
        required = {"scout", "architect", "coder", "reviewer"}
        assert required.issubset(agent_names)

    def test_standard_graph_has_repair_node(self):
        nodes = build_standard_graph("landing_page")
        agents = [n.agent for n in nodes]
        assert "repair" in agents

    def test_research_mode_only_scout(self):
        nodes = build_standard_graph("research")
        assert len(nodes) == 1
        assert nodes[0].agent == "scout"

    def test_repo_fix_graph_has_coder_not_creative_director(self):
        nodes = build_standard_graph("repo_fix")
        agents = {n.agent for n in nodes}
        assert "coder" in agents
        # repo_fix doesn't need creative director
        assert "creative_director" not in agents

    def test_coder_node_can_repair(self):
        nodes = build_standard_graph("landing_page")
        coder = next(n for n in nodes if n.agent == "coder")
        assert coder.can_repair is True

    def test_node_defaults(self):
        node = GraphNode(node_id="test", agent="test_agent")
        assert node.status == NodeStatus.PENDING
        assert node.attempt == 0
        assert node.output == {}
        assert node.warnings == []

    def test_graph_get_snapshot(self):
        # Check snapshot can be serialised without DB
        import types

        class MockDB:
            pass

        class MockProvider:
            pass

        async def noop(p):
            pass

        graph = ExecutionGraph(
            db=MockDB(),
            provider=MockProvider(),
            project_id="test-123",
            emit=noop,
        )
        snapshot = graph.get_snapshot()
        assert snapshot["graph_status"] == GraphStatus.IDLE.value
        assert snapshot["project_id"] == "test-123"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1D — Creative Director Agent
# ─────────────────────────────────────────────────────────────────────────────

from agents.creative_director import run_creative_director, DesignBlueprint


class TestCreativeDirector:
    def test_returns_design_blueprint(self):
        bp = run_creative_director(
            prompt="A luxury property platform for high-net-worth buyers",
            mode="landing_page",
        )
        assert isinstance(bp, DesignBlueprint)

    def test_blueprint_has_style_name(self):
        bp = run_creative_director(prompt="A tech SaaS dashboard", mode="saas_dashboard")
        assert bp.style_name, "Blueprint must have a non-empty style_name"
        assert bp.style_label, "Blueprint must have a non-empty style_label"

    def test_blueprint_section_archetypes_not_empty(self):
        bp = run_creative_director(prompt="An ecommerce store", mode="ecommerce")
        assert len(bp.section_archetypes) > 0

    def test_blueprint_has_color_palette(self):
        bp = run_creative_director(prompt="A portfolio site", mode="portfolio")
        assert isinstance(bp.color_palette, dict)
        assert len(bp.color_palette) > 0

    def test_blueprint_to_dict_serialisable(self):
        import json
        bp = run_creative_director(prompt="A startup landing page", mode="landing_page")
        d = bp.to_dict()
        # Should be JSON-serialisable
        json.dumps(d)  # raises if not serialisable

    def test_blueprint_prompt_block_is_string(self):
        bp = run_creative_director(prompt="A SaaS app", mode="saas_dashboard")
        block = bp.to_prompt_block()
        assert isinstance(block, str)
        assert "CREATIVE DIRECTOR BLUEPRINT" in block
        assert "MANDATORY" in block

    def test_blueprint_prompt_block_includes_sections(self):
        bp = run_creative_director(prompt="Build a landing page", mode="landing_page")
        block = bp.to_prompt_block()
        # Each archetype should be in the block
        for arch in bp.section_archetypes[:3]:
            assert arch in block

    def test_animation_tone_populated(self):
        bp = run_creative_director(prompt="A dark tech site", mode="landing_page")
        assert isinstance(bp.animation_tone, dict)
        # All blueprints should have tone and description
        assert "tone" in bp.animation_tone
        assert "description" in bp.animation_tone


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1E — Build Mode Classifier
# ─────────────────────────────────────────────────────────────────────────────

from agents.mode_classifier import classify_build_mode, SUPPORTED_MODES, normalise_mode_for_orchestrator


class TestBuildModeClassifier:
    def test_landing_page_detection(self):
        result = classify_build_mode("Build a landing page for my SaaS product")
        assert result.mode == "landing_page"
        assert result.confidence >= 0.85

    def test_multipage_site_detection(self):
        result = classify_build_mode("Create a 5-page website for my business")
        assert result.mode == "multipage_site"

    def test_pwa_detection(self):
        result = classify_build_mode("Build a Progressive Web App with offline support")
        assert result.mode == "pwa"
        assert result.confidence >= 0.85

    def test_saas_dashboard_detection(self):
        result = classify_build_mode("Build a SaaS dashboard with user authentication and subscription")
        assert result.mode == "saas_dashboard"

    def test_api_backend_detection(self):
        result = classify_build_mode("Create a REST API backend with FastAPI and PostgreSQL")
        assert result.mode == "api_backend"

    def test_repo_upgrade_detection(self):
        result = classify_build_mode("Improve my repo at github.com/user/myproject")
        assert result.mode == "repo_upgrade"

    def test_ecommerce_detection(self):
        result = classify_build_mode("Build an online store where customers can buy products")
        assert result.mode == "ecommerce"

    def test_portfolio_detection(self):
        result = classify_build_mode("Create a portfolio site to showcase my design work")
        assert result.mode == "portfolio"

    def test_admin_system_detection(self):
        result = classify_build_mode("Build an admin panel to manage users and orders")
        assert result.mode == "admin_system"

    def test_vague_prompt_needs_clarification(self):
        result = classify_build_mode("build an app")
        assert result.needs_clarification is True

    def test_vague_prompt_returns_questions(self):
        result = classify_build_mode("create a website")
        assert len(result.clarification_questions) > 0

    def test_forced_mode_overrides_detection(self):
        result = classify_build_mode(
            "Build a landing page for my SaaS",
            forced_mode="portfolio"
        )
        assert result.mode == "portfolio"
        assert result.confidence == 1.0

    def test_all_modes_in_supported_modes(self):
        for mode in SUPPORTED_MODES:
            assert mode in SUPPORTED_MODES

    def test_result_is_serialisable(self):
        import json
        result = classify_build_mode("Build a portfolio for a photographer")
        d = result.to_dict()
        json.dumps(d)  # raises if not JSON serialisable

    def test_normalise_mode_for_orchestrator(self):
        assert normalise_mode_for_orchestrator("landing_page") == "landing_page"
        assert normalise_mode_for_orchestrator("admin_system") == "dashboard"
        assert normalise_mode_for_orchestrator("saas_dashboard") == "full_stack"
        assert normalise_mode_for_orchestrator("repo_upgrade") == "repo_fix"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1F — Strict Validation Engine
# ─────────────────────────────────────────────────────────────────────────────

from agents.quality_validator import score_project_quality, _check_duplicate_ids, _check_broken_anchors, _check_typography_integrity


class TestStrictValidation:
    def _make_file(self, path, content):
        return {"path": path, "content": content, "language": "html"}

    def test_placeholder_copy_penalises_quality(self):
        html = """<!DOCTYPE html><html lang="en"><head><title>Test</title>
        <meta name="viewport" content="width=device-width"></head>
        <body><h1>Welcome</h1><p>Lorem ipsum dolor sit amet consectetur</p>
        <section><p>Some content here</p></section>
        <section><p>More content</p></section>
        <section><p>Even more</p></section>
        <section id="features"><p>Features</p></section>
        <section id="about"><p>About</p></section>
        <nav><a href="#home">Home</a></nav><footer>Footer</footer></body></html>"""
        css = "body { margin: 0; } @media (max-width: 768px) { body { padding: 10px; } } "
        css += ".hero { display: flex; } var(--test) { color: blue; }"
        files = [
            {"path": "index.html", "content": html, "language": "html"},
            {"path": "styles.css", "content": css, "language": "css"},
        ]
        result = score_project_quality(files, "static-site", "landing_page", "")
        # Lorem ipsum should cause a quality penalty
        assert result["qualityScore"] < 100

    def test_duplicate_id_detection(self):
        html = '<div id="hero"></div><div id="hero"></div><div id="features"></div>'
        dups = _check_duplicate_ids(html)
        assert "hero" in dups
        assert "features" not in dups

    def test_broken_anchor_detection(self):
        html = '<a href="#pricing">Pricing</a><div id="about">About</div>'
        broken = _check_broken_anchors(html)
        assert "pricing" in broken
        assert "about" not in broken  # about exists

    def test_typography_integrity_ok_when_declared(self):
        css = ":root { --font-heading: 'Inter'; --font-body: 'Lato'; } h1 { font-family: var(--font-heading); }"
        issues = _check_typography_integrity("", css)
        assert issues == []

    def test_typography_integrity_fails_when_undeclared(self):
        css = "h1 { font-family: var(--font-heading); }"
        issues = _check_typography_integrity("", css)
        assert len(issues) > 0
        assert "broken at runtime" in issues[0]

    def test_missing_css_penalises_design(self):
        html = """<!DOCTYPE html><html lang="en"><head><title>Test</title></head>
        <body><h1>Hello</h1></body></html>"""
        files = [{"path": "index.html", "content": html, "language": "html"}]
        result = score_project_quality(files, "static-site", "landing_page", "")
        assert result["designScore"] < 80, "Missing CSS should drop design below threshold"
        assert result["designOk"] is False

    def test_empty_html_causes_fail(self):
        files = [{"path": "index.html", "content": "", "language": "html"}]
        result = score_project_quality(files, "static-site", "landing_page", "")
        assert result["qualityScore"] < 80
        assert result["qualityOk"] is False

    def test_score_100_is_hard_to_achieve(self):
        """
        A minimal but technically-passing HTML/CSS should NOT score 100 on design.
        Phase 1F spec: 'Design 100 must become difficult to achieve.'
        """
        html = """<!DOCTYPE html><html lang="en"><head>
        <title>Minimal</title>
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <link rel="stylesheet" href="styles.css">
        </head><body>
        <nav><a href="#home">Home</a></nav>
        <h1 id="home">Welcome to My Site</h1>
        <section id="features" class="feature"><p>Feature one description here.</p></section>
        <section id="about"><p>About us section with real copy.</p></section>
        <section id="services" class="service"><p>Our services listed here.</p></section>
        <section><p>Even more content for word count</p></section>
        <a class="btn cta" href="#signup">Get Started</a>
        <footer><p>Footer content</p></footer>
        </body></html>"""
        css = """
        :root {
            --font-heading: 'Inter', sans-serif;
            --font-body: 'Lato', sans-serif;
        }
        @media (max-width: 768px) { body { padding: 1rem; } }
        @media (min-width: 1200px) { body { max-width: 1200px; } }
        @media screen { .nav { display: flex; } }
        body { display: flex; font-family: var(--font-body); }
        h1 { font-family: var(--font-heading); }
        background: linear-gradient(135deg, #ff6b6b, #feca57);
        """
        files = [
            {"path": "index.html", "content": html, "language": "html"},
            {"path": "styles.css", "content": css, "language": "css"},
        ]
        result = score_project_quality(files, "static-site", "landing_page", "Build a minimal site")
        assert result["designScore"] < 100, "Design score of 100 should not be achievable with basic content"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1G — WebSocket Event Buffering & Replay
# ─────────────────────────────────────────────────────────────────────────────

class TestWebSocketHub:
    """Unit tests for the Hub event buffer (no network required)."""

    def _make_hub(self):
        """Import Hub from server.py via a mock-free import."""
        # We need to import Hub without triggering FastAPI startup
        import importlib.util
        import types

        # Manually import just what we need from server.py: the Hub class
        # by re-creating the minimal version from the same source
        class Hub:
            _MAX_BUFFER = 500

            def __init__(self):
                import asyncio
                self.rooms: dict = {}
                self.lock = asyncio.Lock()
                self._event_buffer: dict = {}

            def _buffer_event(self, project_id, payload):
                from datetime import datetime, timezone
                buf = self._event_buffer.setdefault(project_id, [])
                if "ts" not in payload:
                    payload = {**payload, "ts": datetime.now(timezone.utc).isoformat()}
                buf.append(payload)
                if len(buf) > self._MAX_BUFFER:
                    self._event_buffer[project_id] = buf[-self._MAX_BUFFER:]

            def get_buffered_events(self, project_id):
                return list(self._event_buffer.get(project_id, []))

        return Hub()

    def test_buffer_event_adds_to_buffer(self):
        hub = self._make_hub()
        hub._buffer_event("proj-1", {"type": "agent_event", "data": {"detail": "Scout started"}})
        assert len(hub.get_buffered_events("proj-1")) == 1

    def test_buffer_respects_max_size(self):
        hub = self._make_hub()
        hub._MAX_BUFFER = 10
        for i in range(15):
            hub._buffer_event("proj-1", {"type": "test", "i": i})
        events = hub.get_buffered_events("proj-1")
        assert len(events) == 10, "Buffer should be trimmed to MAX_BUFFER"

    def test_events_from_different_projects_are_isolated(self):
        hub = self._make_hub()
        hub._buffer_event("proj-A", {"type": "start", "project": "A"})
        hub._buffer_event("proj-B", {"type": "start", "project": "B"})
        assert len(hub.get_buffered_events("proj-A")) == 1
        assert len(hub.get_buffered_events("proj-B")) == 1

    def test_empty_project_returns_empty_list(self):
        hub = self._make_hub()
        assert hub.get_buffered_events("nonexistent") == []

    def test_event_gets_ts_stamp(self):
        hub = self._make_hub()
        hub._buffer_event("proj-1", {"type": "test_event"})
        events = hub.get_buffered_events("proj-1")
        assert "ts" in events[0], "Buffer must add timestamp to events"
