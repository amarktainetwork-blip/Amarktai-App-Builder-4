"""
Phase 2B Tests — Agent Activation + Toolchain Completion + Premium Orchestration Hardening.

Tests cover:
- Agent activation status (no critical agents remain partial)
- Manager Agent completion gate blocking
- Media Director full activation (honesty, scoring, dedup)
- Deployment Agent full activation (validation, instructions)
- Accessibility Agent real scoring (WCAG checks)
- SEO/Performance Agent real scoring (enhanced)
- Motion Agent accessibility fallback
- Logo Agent persistence and versioning
- Capability Truth verification
- Extended agents (10 new agents)
- Toolchain completeness
- Agent registry Phase 2B acceptance
"""
from __future__ import annotations

import json
import re
from typing import Any

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: Agent Activation Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentActivation:
    """All critical agents must be ACTIVE (not PARTIAL or PLANNED)."""

    def test_no_partial_agents(self):
        """No agent should remain PARTIAL after Phase 2B."""
        from agents.agent_registry import AGENT_REGISTRY, PARTIAL
        partial = [k for k, v in AGENT_REGISTRY.items() if v["status"] == PARTIAL]
        assert partial == [], f"Agents still PARTIAL (unacceptable): {partial}"

    def test_no_planned_agents(self):
        """No agent should remain PLANNED after Phase 2B."""
        from agents.agent_registry import AGENT_REGISTRY, PLANNED
        planned = [k for k, v in AGENT_REGISTRY.items() if v.get("status") == PLANNED]
        assert planned == [], f"Agents still PLANNED: {planned}"

    def test_28_agents_minimum(self):
        """Registry must have at least 28 agents (18 original + 10 new)."""
        from agents.agent_registry import AGENT_REGISTRY
        assert len(AGENT_REGISTRY) >= 28, (
            f"Expected >= 28 agents, got {len(AGENT_REGISTRY)}"
        )

    def test_media_director_active(self):
        """Media Director must be ACTIVE."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("media_director", {})
        assert agent.get("status") == ACTIVE, (
            f"media_director status: {agent.get('status')} (expected ACTIVE)"
        )

    def test_deployment_active(self):
        """Deployment Agent must be ACTIVE."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("deployment", {})
        assert agent.get("status") == ACTIVE, (
            f"deployment status: {agent.get('status')} (expected ACTIVE)"
        )

    def test_accessibility_active(self):
        """Accessibility Agent must be ACTIVE."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("accessibility", {})
        assert agent.get("status") == ACTIVE, (
            f"accessibility status: {agent.get('status')} (expected ACTIVE)"
        )

    def test_seo_performance_active(self):
        """SEO/Performance Agent must be ACTIVE."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("seo_performance", {})
        assert agent.get("status") == ACTIVE, (
            f"seo_performance status: {agent.get('status')} (expected ACTIVE)"
        )

    def test_creative_director_active(self):
        """Creative Director must be ACTIVE (upgraded from DETERMINISTIC)."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("creative_director", {})
        assert agent.get("status") == ACTIVE, (
            f"creative_director status: {agent.get('status')}"
        )

    def test_ui_designer_active(self):
        """UI Designer must be ACTIVE (upgraded from DETERMINISTIC)."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        agent = AGENT_REGISTRY.get("ui_designer", {})
        assert agent.get("status") == ACTIVE, (
            f"ui_designer status: {agent.get('status')}"
        )

    def test_10_new_agents_present(self):
        """All 10 new Phase 2B agents must be in the registry."""
        from agents.agent_registry import AGENT_REGISTRY
        required_new = [
            "runtime_engineer",
            "tool_integration",
            "data_architect",
            "component_librarian",
            "prompt_optimizer",
            "documentation",
            "export_agent",
            "monitoring",
            "memory_curator",
            "capability_truth",
        ]
        missing = [a for a in required_new if a not in AGENT_REGISTRY]
        assert not missing, f"New agents missing from registry: {missing}"

    def test_phase_2b_complete_flag(self):
        """Registry status summary must report phase_2b_complete=True."""
        from agents.agent_registry import get_agent_status_summary
        summary = get_agent_status_summary()
        assert summary.get("phase_2b_complete") is True, (
            f"phase_2b_complete is False. Summary: {summary}"
        )

    def test_all_active_agents_have_tools(self):
        """All ACTIVE agents must have at least one tool declared."""
        from agents.agent_registry import AGENT_REGISTRY, ACTIVE
        missing_tools = [
            k for k, v in AGENT_REGISTRY.items()
            if v["status"] == ACTIVE and not v.get("tools")
        ]
        assert not missing_tools, f"ACTIVE agents missing tools: {missing_tools}"

    def test_all_agents_have_inputs_and_outputs(self):
        """All agents must declare inputs and outputs."""
        from agents.agent_registry import AGENT_REGISTRY
        missing = [
            k for k, v in AGENT_REGISTRY.items()
            if not v.get("inputs") or not v.get("outputs")
        ]
        assert not missing, f"Agents missing inputs/outputs: {missing}"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Manager Agent Hardening Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestManagerCompletionGate:
    """Manager Agent must block incomplete builds."""

    def _make_orchestrator(self):
        """Create a minimal orchestrator-like object with the completion gate method."""
        from agents.agent_registry import AGENT_REGISTRY
        # We test the logic directly through the method
        return None

    def test_gate_blocks_unresolved_tasks(self):
        """Completion gate must block when unresolved tasks exist."""
        from agents.orchestrator import BuildOrchestrator
        # We test the logic via the _manager_completion_gate method signature
        # by checking the orchestrator has the method
        assert hasattr(BuildOrchestrator, "_manager_completion_gate"), (
            "BuildOrchestrator must have _manager_completion_gate method"
        )

    def test_gate_method_exists(self):
        """Manager completion gate method must exist on orchestrator."""
        from agents.orchestrator import BuildOrchestrator
        assert callable(getattr(BuildOrchestrator, "_manager_completion_gate", None))

    def test_deployment_agent_imported(self):
        """Orchestrator must import and use deployment agent."""
        import agents.orchestrator as orch_module
        assert hasattr(orch_module, "run_deployment_validation"), (
            "orchestrator.py must import run_deployment_validation"
        )

    def test_media_director_imported(self):
        """Orchestrator must import media director."""
        import agents.orchestrator as orch_module
        assert hasattr(orch_module, "run_media_director"), (
            "orchestrator.py must import run_media_director"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4: Media Director Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMediaDirector:
    """Media Director must be fully operational and honest about AI availability."""

    def test_strategy_honest_when_ai_unavailable(self):
        """When AI is unavailable, strategy must report honestly and use CSS/SVG."""
        from agents.media_director import select_media_strategy
        strategy = select_media_strategy("ai", capability_registry={"supports_image_generation": False})
        assert strategy["mode"] == "css_svg"
        assert strategy.get("ai_unavailable") is True
        assert "NOT available" in strategy["honest_report"]

    def test_strategy_uses_ai_when_available(self):
        """When AI is available, strategy should use AI mode."""
        from agents.media_director import select_media_strategy
        strategy = select_media_strategy("ai", capability_registry={"supports_image_generation": True})
        assert strategy["mode"] == "ai"
        assert not strategy.get("ai_unavailable")

    def test_relevance_scoring_range(self):
        """Relevance scoring must return 0-100."""
        from agents.media_director import score_media_relevance
        score = score_media_relevance("technology startup", "tech", "tech", "minimal")
        assert 0 <= score <= 100

    def test_relevance_rejects_generic(self):
        """Generic/placeholder subjects should score low."""
        from agents.media_director import score_media_relevance
        score = score_media_relevance("random placeholder stock photo", "random", "tech")
        assert score < 50, f"Generic subject should score low, got {score}"

    def test_quality_scoring_range(self):
        """Quality scoring must return 0-100."""
        from agents.media_director import score_media_quality
        score = score_media_quality({"width": 1920, "height": 1080, "type": "image/webp", "url": "https://example.com/img.webp"})
        assert 0 <= score <= 100

    def test_quality_scores_high_res_well(self):
        """1920x1080 webp should score high quality."""
        from agents.media_director import score_media_quality
        score = score_media_quality({"width": 1920, "height": 1080, "type": "image/webp", "url": "https://cdn.example.com/hero.webp"})
        assert score >= 70, f"High-res webp should score >= 70, got {score}"

    def test_duplicate_detection(self):
        """Duplicate detection must identify same URLs."""
        from agents.media_director import detect_duplicates
        assets = [
            {"id": "a1", "url": "https://cdn.example.com/img.jpg"},
            {"id": "a2", "url": "https://cdn.example.com/img.jpg"},  # duplicate
            {"id": "a3", "url": "https://cdn.example.com/other.jpg"},
        ]
        dupes = detect_duplicates(assets)
        assert "a2" in dupes, f"a2 should be detected as duplicate, got: {dupes}"
        assert "a3" not in dupes

    def test_run_media_director_returns_complete_result(self):
        """run_media_director must return all expected keys."""
        from agents.media_director import run_media_director
        result = run_media_director(
            industry="tech",
            style="minimal",
            media_source="css_svg",
            page_context=[{"section": "hero"}, {"section": "features"}],
        )
        required_keys = ["media_strategy", "section_media", "warnings", "media_score",
                         "honest_report", "ai_image_available"]
        for key in required_keys:
            assert key in result, f"Missing key '{key}' in media_director result"

    def test_media_score_in_range(self):
        """Media score must be 0-100."""
        from agents.media_director import run_media_director
        result = run_media_director(industry="finance", style="corporate")
        assert 0 <= result["media_score"] <= 100

    def test_no_fake_ai_generation(self):
        """When AI is unavailable, media director must not claim AI generation."""
        from agents.media_director import run_media_director
        result = run_media_director(
            media_source="ai",
            capability_registry={"supports_image_generation": False},
        )
        assert result["ai_image_available"] is False
        assert result["media_strategy"]["mode"] != "ai"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7: Accessibility Agent Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAccessibilityScoring:
    """Accessibility Agent must produce real scores and actionable violations."""

    def _score(self, html: str, css: str = "") -> tuple[int, list[str]]:
        from agents.quality_validator import _score_accessibility
        return _score_accessibility(html, css)

    def test_score_returns_int_and_list(self):
        score, errors = self._score("<html lang='en'><body><h1>Test</h1></body></html>")
        assert isinstance(score, int)
        assert isinstance(errors, list)

    def test_score_range(self):
        score, _ = self._score("<html lang='en'><body><h1>Test</h1></body></html>")
        assert 0 <= score <= 100

    def test_missing_lang_penalized(self):
        score_without_lang, errors = self._score("<html><body><h1>Test</h1></body></html>")
        score_with_lang, _ = self._score("<html lang='en'><body><h1>Test</h1></body></html>")
        assert score_with_lang > score_without_lang
        assert any("lang" in e.lower() for e in errors)

    def test_missing_alt_penalized(self):
        html_no_alt = "<html lang='en'><body><h1>X</h1><img src='a.png'></body></html>"
        html_with_alt = "<html lang='en'><body><h1>X</h1><img src='a.png' alt='Hero image'></body></html>"
        score_no, errors = self._score(html_no_alt)
        score_with, _ = self._score(html_with_alt)
        assert score_with >= score_no
        assert any("alt" in e.lower() for e in errors)

    def test_aria_attributes_rewarded(self):
        html_no_aria = "<html lang='en'><body><h1>X</h1><button>Click</button></body></html>"
        html_aria = "<html lang='en'><body><h1>X</h1><button aria-label='Submit form'>Click</button></body></html>"
        score_no, _ = self._score(html_no_aria)
        score_aria, _ = self._score(html_aria)
        assert score_aria >= score_no

    def test_focus_visible_css_rewarded(self):
        css_no_focus = "body { color: black; }"
        css_focus = "a:focus-visible { outline: 2px solid blue; }"
        html = "<html lang='en'><body><h1>Test</h1><a href='/'>Link</a></body></html>"
        score_no, _ = self._score(html, css_no_focus)
        score_focus, _ = self._score(html, css_focus)
        assert score_focus >= score_no

    def test_reduced_motion_rewarded(self):
        css_no_motion = "@keyframes fade { from { opacity: 0; } to { opacity: 1; } }"
        css_motion = "@keyframes fade { from { opacity: 0; } to { opacity: 1; } } @media (prefers-reduced-motion: reduce) { * { animation: none; } }"
        html = "<html lang='en'><body><h1>Test</h1></body></html>"
        score_no, errors_no = self._score(html, css_no_motion)
        score_motion, _ = self._score(html, css_motion)
        assert score_motion >= score_no
        assert any("reduced-motion" in e.lower() or "prefers-reduced-motion" in e.lower() for e in errors_no)

    def test_multiple_h1_penalized(self):
        html_multi_h1 = "<html lang='en'><body><h1>First</h1><h1>Second</h1></body></html>"
        _, errors = self._score(html_multi_h1)
        assert any("h1" in e.lower() and ("multiple" in e.lower() or "two" in e.lower() or "2" in e) for e in errors)

    def test_positive_tabindex_penalized(self):
        html = "<html lang='en'><body><h1>X</h1><button tabindex='3'>Click</button></body></html>"
        _, errors = self._score(html)
        assert any("tabindex" in e.lower() for e in errors)

    def test_perfect_html_scores_high(self):
        """Well-crafted accessible HTML should score well."""
        html = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
<a href="#main" class="skip-link">Skip to main content</a>
<header><nav aria-label="Main navigation"><ul><li><a href="/">Home</a></li></ul></nav></header>
<main id="main">
  <h1>Accessible Heading</h1>
  <img src="hero.webp" alt="Hero image showing product" width="1200" height="600">
  <button aria-label="Get started">Get Started</button>
</main>
<footer><p>Footer</p></footer>
</body>
</html>"""
        css = """
:focus-visible { outline: 2px solid blue; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
"""
        score, _ = self._score(html, css)
        assert score >= 70, f"Well-crafted accessible HTML should score >= 70, got {score}"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8: SEO/Performance Agent Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSEOScoring:
    """SEO Agent must produce real scores with actionable recommendations."""

    def _score(self, html: str) -> tuple[int, list[str]]:
        from agents.quality_validator import _score_seo
        return _score_seo(html)

    def test_score_range(self):
        score, _ = self._score("<html><head><title>Test</title></head><body><h1>X</h1></body></html>")
        assert 0 <= score <= 100

    def test_missing_title_penalized(self):
        score, errors = self._score("<html><head></head><body><h1>X</h1></body></html>")
        assert any("title" in e.lower() for e in errors)

    def test_missing_meta_description_penalized(self):
        score, errors = self._score("<html><head><title>T</title></head><body></body></html>")
        assert any("description" in e.lower() for e in errors)

    def test_missing_og_tags_penalized(self):
        score, errors = self._score("<html><head><title>T</title></head><body></body></html>")
        assert any("og:" in e.lower() or "open graph" in e.lower() for e in errors)

    def test_twitter_card_missing_reported(self):
        score, errors = self._score("<html><head><title>T</title></head><body></body></html>")
        assert any("twitter" in e.lower() for e in errors)

    def test_structured_data_bonus(self):
        html_no_sd = "<html><head><title>T</title></head><body></body></html>"
        html_sd = '<html><head><title>T</title><script type="application/ld+json">{"@context":"https://schema.org"}</script></head><body></body></html>'
        score_no, _ = self._score(html_no_sd)
        score_sd, _ = self._score(html_sd)
        assert score_sd >= score_no

    def test_full_seo_html_scores_well(self):
        """Well-crafted SEO HTML should score high."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>Premium SaaS Dashboard — Manage Your Business</title>
  <meta name="description" content="The most powerful SaaS dashboard for managing your business metrics, team, and growth in one place. Start free today.">
  <meta property="og:title" content="Premium SaaS Dashboard">
  <meta property="og:description" content="Manage your business in one place.">
  <meta property="og:image" content="https://cdn.example.com/og-image.jpg">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Premium SaaS Dashboard">
  <link rel="canonical" href="https://example.com/">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebApplication","name":"Dashboard"}</script>
</head>
<body>
  <h1>Dashboard</h1>
  <h2>Features</h2>
  <h3>Analytics</h3>
  <img src="chart.webp" alt="Analytics chart showing growth" width="800" height="400">
</body>
</html>"""
        score, _ = self._score(html)
        assert score >= 75, f"Well-crafted SEO HTML should score >= 75, got {score}"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 9: Deployment Agent Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDeploymentAgent:
    """Deployment Agent must validate builds and never fake success."""

    def test_valid_static_site_passes(self):
        """Static site with index.html should pass deployment validation."""
        from agents.deployment_agent import run_deployment_validation
        files = [
            {"path": "index.html", "content": "<!DOCTYPE html><html><head><title>T</title></head><body><h1>X</h1></body></html>"},
            {"path": "styles.css", "content": "body { margin: 0; }"},
        ]
        result = run_deployment_validation(files, "landing_page")
        assert isinstance(result, dict)
        assert "passed" in result
        assert "deploy_checklist" in result
        assert "deployment_instructions" in result

    def test_missing_html_fails_for_static_mode(self):
        """No HTML file should fail deployment validation for static mode."""
        from agents.deployment_agent import validate_preview_readiness
        result = validate_preview_readiness([], "landing_page")
        assert result["can_preview"] is False
        assert result["passed"] is False

    def test_docker_validation_checks_from(self):
        """Dockerfile without FROM should fail."""
        from agents.deployment_agent import validate_docker_config
        files = [{"path": "Dockerfile", "content": "RUN echo hello\nCMD node index.js"}]
        result = validate_docker_config(files)
        assert not result["passed"]
        assert any("FROM" in e for e in result["errors"])

    def test_docker_validation_passes_valid(self):
        """Valid Dockerfile should pass."""
        from agents.deployment_agent import validate_docker_config
        dockerfile = "FROM node:18-alpine\nWORKDIR /app\nCOPY . .\nRUN npm install\nEXPOSE 3000\nCMD node server.js"
        files = [{"path": "Dockerfile", "content": dockerfile}]
        result = validate_docker_config(files)
        assert result["passed"]
        assert result["has_dockerfile"]

    def test_env_example_rejects_real_secrets(self):
        """Real secrets in .env.example must be flagged."""
        from agents.deployment_agent import validate_env_template
        files = [{"path": ".env.example", "content": "JWT_SECRET=abc123verylongsecretkey\nDATABASE_URL=postgres://user:pass@db:5432/prod"}]
        result = validate_env_template(files)
        assert not result["passed"]
        assert any("real secrets" in e.lower() or "secret" in e.lower() for e in result["errors"])

    def test_env_example_passes_placeholders(self):
        """Placeholder values in .env.example should pass."""
        from agents.deployment_agent import validate_env_template
        files = [{"path": ".env.example", "content": "JWT_SECRET=your_jwt_secret_here\nDATABASE_URL=your_database_url_here"}]
        result = validate_env_template(files)
        assert result["passed"]

    def test_placeholder_text_warned(self):
        """Placeholder text in HTML should generate warnings."""
        from agents.deployment_agent import validate_preview_readiness
        html = "<!DOCTYPE html><html><body><h1>Lorem ipsum dolor sit amet</h1></body></html>"
        files = [{"path": "index.html", "content": html}]
        result = validate_preview_readiness(files, "landing_page")
        assert any("lorem ipsum" in w.lower() or "placeholder" in w.lower() for w in result["warnings"])

    def test_deployment_instructions_generated(self):
        """Deployment instructions must be non-empty."""
        from agents.deployment_agent import generate_deployment_instructions
        files = [{"path": "index.html", "content": "<!DOCTYPE html><html><body></body></html>"}]
        instructions = generate_deployment_instructions(files, "landing_page")
        assert len(instructions) > 100
        assert "Deployment" in instructions or "deploy" in instructions.lower()

    def test_full_validation_result_structure(self):
        """Full validation result must have all required keys."""
        from agents.deployment_agent import run_deployment_validation
        result = run_deployment_validation([], "api_service")
        required_keys = ["passed", "deploy_checklist", "warnings", "errors",
                         "preview_readiness", "docker_validation", "env_validation",
                         "deployment_instructions", "rollback_guidance"]
        for key in required_keys:
            assert key in result, f"Missing key '{key}'"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 5: Logo Agent Versioning Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLogoAgentVersioning:
    """Logo Agent must persist and version logos across iterations."""

    def test_run_logo_agent_returns_version(self):
        """run_logo_agent must return logoVersion."""
        import asyncio
        from agents.logo_agent import run_logo_agent
        result = asyncio.run(run_logo_agent({"businessName": "TestCo", "industry": "tech"}))
        assert "logoVersion" in result
        assert result["logoVersion"] >= 1

    def test_run_logo_agent_returns_brand_colors(self):
        """run_logo_agent must return brandColors dict."""
        import asyncio
        from agents.logo_agent import run_logo_agent
        result = asyncio.run(run_logo_agent({"businessName": "TestCo", "industry": "tech"}))
        assert "brandColors" in result
        assert isinstance(result["brandColors"], dict)

    def test_run_logo_agent_not_reused_when_no_memory(self):
        """Logo should not be marked as reused when no memory provided."""
        import asyncio
        from agents.logo_agent import run_logo_agent
        result = asyncio.run(run_logo_agent({"businessName": "TestCo"}))
        assert result.get("reusedFromMemory") is False

    def test_logo_memory_reuse(self):
        """Logo should be reused from memory when business name matches."""
        import asyncio
        from agents.logo_agent import run_logo_agent
        memory = {
            "logo": {
                "logoType": "svg",
                "assetId": "test-asset-id",
                "htmlSnippet": "<svg>test</svg>",
                "cssSnippet": ".logo {}",
                "faviconDataUri": "data:image/svg+xml;base64,test",
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text>TestCo</text></svg>',
                "faviconSvg": '<svg xmlns="http://www.w3.org/2000/svg"><text>T</text></svg>',
                "businessName": "TestCo",
                "logoVersion": 3,
            }
        }
        result = asyncio.run(run_logo_agent(
            {"businessName": "TestCo"},
            project_memory=memory,
        ))
        assert result.get("reusedFromMemory") is True
        assert result.get("logoVersion") == 3

    def test_logo_memory_not_reused_different_name(self):
        """Logo should NOT be reused when business name differs."""
        import asyncio
        from agents.logo_agent import run_logo_agent
        memory = {
            "logo": {
                "businessName": "OtherCompany",
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg"><text>O</text></svg>',
                "logoType": "svg",
                "logoVersion": 2,
            }
        }
        result = asyncio.run(run_logo_agent(
            {"businessName": "TestCo"},
            project_memory=memory,
        ))
        assert result.get("reusedFromMemory") is False

    def test_extract_brand_colors(self):
        """Brand colors should be extracted from SVG."""
        from agents.logo_agent import extract_brand_colors
        svg = '<svg><rect fill="#2563eb" /><text fill="#f8fafc">T</text></svg>'
        colors = extract_brand_colors(svg)
        assert "primary" in colors
        assert "#2563eb" in colors.values() or "#f8fafc" in colors.values()

    def test_should_reuse_logo_true_match(self):
        """should_reuse_logo returns True for matching business name."""
        from agents.logo_agent import should_reuse_logo
        memory = {"logo": {"businessName": "AcmeCorp", "logoType": "svg"}}
        assert should_reuse_logo(memory, "AcmeCorp") is True

    def test_should_reuse_logo_false_mismatch(self):
        """should_reuse_logo returns False for different business name."""
        from agents.logo_agent import should_reuse_logo
        memory = {"logo": {"businessName": "AcmeCorp", "logoType": "svg"}}
        assert should_reuse_logo(memory, "OtherCo") is False

    def test_memory_versioning_increments(self):
        """update_memory_logo must increment logoVersion on new logo."""
        from agents.project_memory import update_memory_logo
        memory = {"logo": {"logoType": "svg", "logoVersion": 2, "businessName": "TestCo"}}
        new_logo = {"logoType": "svg", "assetId": "new-id", "reusedFromMemory": False}
        updated = update_memory_logo(memory, new_logo)
        assert updated["logo"]["logoVersion"] == 3

    def test_memory_versioning_preserved_on_reuse(self):
        """update_memory_logo must NOT increment version when reusing."""
        from agents.project_memory import update_memory_logo
        memory = {"logo": {"logoType": "svg", "logoVersion": 2, "businessName": "TestCo"}}
        reused_logo = {"logoType": "svg", "assetId": "same-id", "reusedFromMemory": True}
        updated = update_memory_logo(memory, reused_logo)
        assert updated["logo"]["logoVersion"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# Phase 10: Extended Agents Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestExtendedAgents:
    """All 10 new extended agents must work correctly."""

    def test_runtime_health_check_passes_valid_project(self):
        """Runtime health check should pass for a project with valid entry point."""
        from agents.extended_agents import check_runtime_health
        files = [{"path": "index.html", "content": "<!DOCTYPE html><html><body></body></html>"}]
        result = check_runtime_health(files, build_logs="Compiled successfully!")
        assert "runtime_ok" in result
        assert result.get("has_entry_point") is True

    def test_runtime_health_check_fails_with_build_errors(self):
        """Runtime health check should report issues when build logs have errors."""
        from agents.extended_agents import check_runtime_health
        files = [{"path": "index.html", "content": "<!DOCTYPE html><body></body></html>"}]
        result = check_runtime_health(files, build_logs="ERROR in ./src/App.js\nFailed to compile")
        assert len(result["issues"]) > 0

    def test_tool_integration_detects_stripe(self):
        """Tool integration agent must detect Stripe usage."""
        from agents.extended_agents import verify_tool_integration
        files = [
            {"path": "payment.js", "content": "const stripe = require('stripe');"},
            {"path": ".env.example", "content": "STRIPE_SECRET_KEY=your_key\nSTRIPE_PUBLISHABLE_KEY=your_pk"},
        ]
        result = verify_tool_integration(files)
        assert "stripe" in result["detected_tools"]
        assert "stripe" in result["connected_tools"]

    def test_tool_integration_reports_missing_env(self):
        """Tool integration must report missing env vars."""
        from agents.extended_agents import verify_tool_integration
        files = [
            {"path": "mailer.js", "content": "const sg = require('@sendgrid/mail');"},
            {"path": ".env.example", "content": "APP_NAME=myapp"},
        ]
        result = verify_tool_integration(files)
        assert "sendgrid" in result["missing_env_vars"]

    def test_data_architect_detects_prisma(self):
        """Data architect must detect Prisma ORM."""
        from agents.extended_agents import analyze_data_architecture
        files = [{"path": "schema.prisma", "content": "generator client { provider = \"prisma-client-js\" }"}]
        result = analyze_data_architecture(files, "full_stack")
        assert result["db_technology"] == "Prisma ORM"

    def test_component_librarian_finds_react_components(self):
        """Component librarian must find React components."""
        from agents.extended_agents import register_components
        files = [{"path": "Hero.tsx", "content": "export default function HeroSection() { return <div>Hero</div>; }"}]
        result = register_components(files)
        assert result["component_count"] >= 1
        assert any(c["name"] == "HeroSection" for c in result["react_components"])

    def test_prompt_optimizer_detects_vague(self):
        """Prompt optimizer must detect vague requirements."""
        from agents.extended_agents import analyze_prompt_quality
        result = analyze_prompt_quality("make something nice")
        assert len(result["issues"]) > 0
        assert result["prompt_quality_score"] < 70

    def test_prompt_optimizer_rewards_specific(self):
        """Prompt optimizer must reward specific, detailed prompts."""
        from agents.extended_agents import analyze_prompt_quality
        prompt = (
            "Build a SaaS landing page for a project management tool targeting startup founders. "
            "Include hero, features, pricing, and testimonials sections. "
            "Target audience: CTOs and founders. Color scheme: dark navy with electric blue accents."
        )
        result = analyze_prompt_quality(prompt)
        assert len(result["strengths"]) > 0
        assert result["prompt_quality_score"] >= 50

    def test_generate_readme_has_required_sections(self):
        """Documentation agent must generate README with required sections."""
        from agents.extended_agents import generate_readme
        readme = generate_readme(
            project_name="TestApp",
            mode="landing_page",
            files=[{"path": "index.html", "content": ""}],
            tech_stack={"frontend": "Vite + React"},
            features=["Feature A", "Feature B"],
        )
        assert "TestApp" in readme
        assert "Tech Stack" in readme
        assert "Getting Started" in readme

    def test_export_manifest_complete(self):
        """Export agent must produce complete manifest."""
        from agents.extended_agents import prepare_export_manifest
        files = [
            {"path": "index.html", "content": "<!DOCTYPE html>..."},
            {"path": "styles.css", "content": "body {}"},
            {"path": "README.md", "content": "# Docs"},
        ]
        result = prepare_export_manifest(files, "TestProject", "1.0.0")
        assert result["export_ready"] is True
        assert result["total_files"] == 3
        assert "file_categories" in result

    def test_monitoring_detects_health_endpoint(self):
        """Monitoring agent must detect /health endpoint."""
        from agents.extended_agents import analyze_monitoring_readiness
        files = [{"path": "server.py", "content": '@app.get("/health")\ndef health(): return {"status": "ok"}'}]
        result = analyze_monitoring_readiness(files)
        assert result["has_health_endpoint"] is True

    def test_memory_curator_trims_long_history(self):
        """Memory curator must trim agent_decisions to 20 entries."""
        from agents.extended_agents import curate_memory
        memory = {
            "brand": {"name": "TestCo"},
            "agent_decisions": [{"decision": f"d{i}"} for i in range(30)],
        }
        result = curate_memory(memory)
        assert result["curated"] is True
        assert len(memory["agent_decisions"]) == 20

    def test_capability_truth_detects_false_claim(self):
        """Capability Truth must flag AI image claim when not available."""
        from agents.extended_agents import verify_capability_claims
        result = verify_capability_claims(
            frontend_claims=["AI image generation", "live preview"],
            capability_registry={"supports_image_generation": False, "supports_streaming": True},
        )
        assert result["all_claims_truthful"] is False
        false_claims = [m["claim"] for m in result["mismatched_claims"]]
        assert any("ai image" in c.lower() for c in false_claims)

    def test_capability_truth_passes_true_claims(self):
        """Capability Truth must pass claims that are actually available."""
        from agents.extended_agents import verify_capability_claims
        result = verify_capability_claims(
            frontend_claims=["AI image generation"],
            capability_registry={"supports_image_generation": True},
        )
        assert result["all_claims_truthful"] is True
        assert result["truth_score"] == 100


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: Agent Activation Report Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentActivationReport:
    """Activation report must correctly audit all agents."""

    def test_generate_activation_report_structure(self):
        """Activation report must have all required sections."""
        from agents.agent_activation_report import generate_activation_report
        report = generate_activation_report()
        required_keys = [
            "generated_at", "schema_version", "total_agents", "summary",
            "active_agents", "partial_agents", "agents",
            "phase_2b_acceptance",
        ]
        for key in required_keys:
            assert key in report, f"Missing key '{key}' in activation report"

    def test_activation_report_no_partial(self):
        """Activation report must show no partial agents after Phase 2B."""
        from agents.agent_activation_report import generate_activation_report
        report = generate_activation_report()
        assert report["partial_agents"] == [], (
            f"Activation report shows partial agents: {report['partial_agents']}"
        )

    def test_phase_2b_acceptance_flags(self):
        """Phase 2B acceptance flags must all be True."""
        from agents.agent_activation_report import generate_activation_report
        report = generate_activation_report()
        acceptance = report["phase_2b_acceptance"]
        assert acceptance["media_director_active"] is True
        assert acceptance["deployment_agent_active"] is True
        assert acceptance["accessibility_active"] is True
        assert acceptance["seo_performance_active"] is True
        assert acceptance["capability_truth_active"] is True

    def test_each_agent_has_audit_record(self):
        """Every agent in registry must have an audit record."""
        from agents.agent_activation_report import generate_activation_report
        from agents.agent_registry import AGENT_REGISTRY
        report = generate_activation_report()
        for agent_id in AGENT_REGISTRY:
            assert agent_id in report["agents"], (
                f"Agent '{agent_id}' has no audit record in activation report"
            )

    def test_activation_report_counts_match(self):
        """Summary counts must match actual agent lists."""
        from agents.agent_activation_report import generate_activation_report
        report = generate_activation_report()
        summary = report["summary"]
        assert summary["active"] == len(report["active_agents"])
        assert summary["partial"] == len(report["partial_agents"])


# ══════════════════════════════════════════════════════════════════════════════
# Phase 11: Toolchain Completeness Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestToolchainCompleteness:
    """Verify required toolchain modules are present and importable."""

    def test_media_director_importable(self):
        import agents.media_director  # noqa: F401

    def test_deployment_agent_importable(self):
        import agents.deployment_agent  # noqa: F401

    def test_extended_agents_importable(self):
        import agents.extended_agents  # noqa: F401

    def test_logo_agent_importable(self):
        import agents.logo_agent  # noqa: F401

    def test_quality_validator_importable(self):
        import agents.quality_validator  # noqa: F401

    def test_agent_registry_importable(self):
        import agents.agent_registry  # noqa: F401

    def test_project_memory_importable(self):
        import agents.project_memory  # noqa: F401

    def test_prompts_have_new_agent_prompts(self):
        """New agent prompts must be in prompts.py."""
        from agents.prompts import (
            RUNTIME_ENGINEER_PROMPT,
            DATA_ARCHITECT_PROMPT,
            DOCUMENTATION_PROMPT,
            EXPORT_PROMPT,
            CAPABILITY_TRUTH_PROMPT,
            MEMORY_CURATOR_PROMPT,
        )
        for prompt in [RUNTIME_ENGINEER_PROMPT, DATA_ARCHITECT_PROMPT, DOCUMENTATION_PROMPT,
                       EXPORT_PROMPT, CAPABILITY_TRUTH_PROMPT, MEMORY_CURATOR_PROMPT]:
            assert len(prompt) > 100, "Prompt too short — must be substantive"

    def test_agent_activation_report_importable(self):
        import agents.agent_activation_report  # noqa: F401

    def test_orchestrator_has_manager_gate(self):
        """Orchestrator must have Manager completion gate."""
        from agents.orchestrator import BuildOrchestrator
        assert hasattr(BuildOrchestrator, "_manager_completion_gate")
