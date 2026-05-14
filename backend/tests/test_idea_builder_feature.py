from __future__ import annotations

from app.services.idea_builder_service import (
    compose_final_prompt,
    deterministic_reply,
    make_message,
    make_session_doc,
    normalize_mode,
)
from agents.orchestrator import _media_source_for_director, _static_visual_qa_result


def test_idea_builder_session_seed_gets_assistant_reply():
    session = make_session_doc(
        owner_id="user-1",
        seed_prompt="I want a luxury AI app builder website for agencies.",
        mode="website",
    )

    assert session["mode"] == "website"
    assert len(session["messages"]) == 2
    assert session["messages"][0]["role"] == "user"
    assert session["messages"][1]["role"] == "assistant"
    assert "build" in session["messages"][1]["content"].lower()


def test_idea_builder_final_prompt_is_build_ready():
    messages = [
        make_message("user", "Create a cinematic AI software factory website called Amarktai Builder."),
        make_message("user", "Audience is founders, agencies, startups, and product teams."),
        make_message("user", "It needs repo import, live preview, repair, quality gates, and GitHub PR automation."),
    ]

    prompt = compose_final_prompt(messages, "website", "Amarktai Builder")

    assert "Amarktai Builder" in prompt
    assert "Audience:" in prompt
    assert "Technical requirements:" in prompt
    assert "quality report" in prompt.lower()
    assert "no lorem ipsum" in prompt.lower()


def test_idea_builder_deterministic_reply_never_claims_provider_work():
    reply = deterministic_reply(
        [make_message("user", "A dashboard for operators with analytics and automation.")],
        "dashboard",
    )

    assert "dashboard" in reply.lower()
    assert "generate a polished build prompt" in reply.lower()
    assert "genx" not in reply.lower()


def test_idea_builder_mode_normalization():
    assert normalize_mode("full_stack") == "full_stack"
    assert normalize_mode("unknown") == "website"


def test_media_director_source_mapping_is_truthful():
    assert _media_source_for_director({"mode": "ai_generated"}) == "ai"
    assert _media_source_for_director({"mode": "pixabay"}) == "pixabay"
    assert _media_source_for_director({"mode": "free_assets"}) == "css_svg"
    assert _media_source_for_director({"mode": "placeholder"}) == "css_svg"


def test_static_visual_qa_blocks_premium_without_css_motion_or_media():
    result = _static_visual_qa_result(
        [{"path": "index.html", "content": "<html><body><main><section><h1>Hello</h1></section></main></body></html>"}],
        {"designScore": 90},
        mode="website",
        quality_tier="premium",
    )

    assert result["passed"] is False
    assert result["metrics"]["has_css"] is False
    assert any("CSS" in issue for issue in result["issues"])


def test_static_visual_qa_passes_premium_with_css_motion_media_and_sections():
    html = "<html><head><link rel='stylesheet' href='styles.css'></head><body><main>"
    html += "".join(f"<section><h2>Section {i}</h2><p>Detailed launch-ready copy for professional teams.</p></section>" for i in range(6))
    html += "<svg role='img' aria-label='Product visual'></svg></main></body></html>"
    css = "body{margin:0}.hero{background:linear-gradient(#000,#111);animation:rise 4s ease}@keyframes rise{to{transform:translateY(0)}}"
    result = _static_visual_qa_result(
        [
            {"path": "index.html", "content": html},
            {"path": "styles.css", "content": css},
        ],
        {"designScore": 92},
        mode="website",
        quality_tier="premium",
    )

    assert result["passed"] is True
    assert result["metrics"]["section_count"] == 6
    assert result["metrics"]["has_motion"] is True
    assert result["metrics"]["has_media_signal"] is True
