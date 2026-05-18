import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.build_contract import (
    ensure_required_files,
    filter_app_source_files,
    is_report_or_metadata_file,
    repair_static_design_family,
    validate_project_files,
)
from agents.orchestrator import (
    Orchestrator,
    _agent_app_files,
    _parse_reviewer_tolerant_output,
    _reviewer_app_patches,
    _static_reviewer_failure_can_continue,
)
from app.services.content_quality_service import run_content_quality_check_for_files


BAKERY_PROMPT = """
Build a cinematic premium one-page website for a luxury artisan bakery called Luma & Stone.
Include cinematic hero, artisan sourdough, seasonal pastries, coffee experience, bakery gallery,
private catering/events, testimonials, contact, warm earthy palette, elegant typography, and subtle premium animations.
Do NOT reference AI, software, Amarktai, dashboards, repo workflows, runtime QA, providers, or deployment systems.
"""


def _bakery_html() -> str:
    return """<!doctype html>
<html><head><title>Luma & Stone</title><link rel="stylesheet" href="styles.css"></head>
<body><header class="site-header"><a class="brand" href="#hero">Luma & Stone</a><nav><a href="#sourdough">Sourdough</a><a href="#contact">Visit</a></nav></header>
<main>
<section id="hero" class="hero bakery-hero hero-copy"><h1>Luma & Stone</h1><p class="lede">Warm artisan bakery.</p></section>
</main><script src="script.js"></script></body></html>"""


def test_report_metadata_files_are_excluded_from_app_source_payloads():
    files = [
        {"path": "index.html", "content": "<html></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "content_quality_report.json", "content": "{}"},
        {"path": "runtime-qa/runtime-qa-report.json", "content": "{}"},
        {"path": "media_manifest.json", "content": "{}"},
    ]

    assert is_report_or_metadata_file("content_quality_report.json")
    assert [f["path"] for f in filter_app_source_files(files)] == ["index.html", "styles.css"]
    assert [f["path"] for f in _agent_app_files(files)] == ["index.html", "styles.css"]


def test_reviewer_report_patch_is_ignored_not_crashing_app_repair():
    patches, ignored = _reviewer_app_patches([
        {"path": "content_quality_report.json", "content": '{"pass": true}'},
        {"path": "styles.css", "content": "body{color:white}"},
    ])

    assert [p["path"] for p in patches] == ["styles.css"]
    assert ignored == ["content_quality_report.json"]


def test_content_quality_ignores_report_files_without_keyerror():
    result = run_content_quality_check_for_files(
        [
            {"path": "index.html", "content": "<html><body><main><section><h1>Luma & Stone</h1><p>Artisan bakery with sourdough, pastries, coffee, testimonials, and contact.</p><a href='#contact'>Book</a></section><section id='contact'>Visit us</section></main></body></html>"},
            {"path": "content_quality_report.json", "content": "{}"},
        ],
        prompt=BAKERY_PROMPT,
        strict=False,
    )

    assert "content_quality_report.json" not in result["files_checked"]


def test_bakery_html_repairs_to_matching_css_js_without_saas_family():
    files = [
        {"path": "index.html", "language": "html", "content": _bakery_html()},
        {"path": "styles.css", "language": "css", "content": ":root{--color-bg:#05070b;--color-fg:#fff}.hero{color:#00e676}"},
        {"path": "script.js", "language": "javascript", "content": "document.querySelector('.missing-motion').classList.add('x')"},
    ]

    repaired, changed = repair_static_design_family({"mode": "landing_page"}, BAKERY_PROMPT, {}, files, force=True)
    by_path = {f["path"]: f for f in repaired}

    assert "index.html" in changed
    assert "styles.css" in changed
    assert "script.js" in changed
    assert "Luma & Stone" in by_path["index.html"]["content"]
    assert "Amarktai" not in by_path["index.html"]["content"]
    assert ".bakery-hero" in by_path["styles.css"]["content"]
    assert ".sourdough-section" in by_path["styles.css"]["content"]
    assert "#00e676" not in by_path["styles.css"]["content"].lower()
    assert ".missing-motion" not in by_path["script.js"]["content"]
    validation = validate_project_files({"mode": "landing_page"}, repaired, prompt=BAKERY_PROMPT)
    assert validation["structureOk"] is True
    assert not any("script.js targets missing selector" in err for err in validation["errors"])


def test_missing_manifests_generated_without_replacing_customer_visual_files():
    html = _bakery_html().replace("</main>", """
<section id="sourdough" class="story-section sourdough-section" data-amarktai-motion-scene><h2>Artisan sourdough</h2><p>Long fermentation.</p></section>
<section id="pastries" class="story-section pastries-section" data-amarktai-motion-scene><h2>Seasonal pastries</h2><p>Fruit tarts.</p></section>
<section id="coffee" class="story-section coffee-section" data-amarktai-motion-scene><h2>Coffee experience</h2><p>Espresso and filter coffee.</p></section>
<section id="gallery" class="story-section gallery-section" data-amarktai-motion-scene><h2>Bakery gallery</h2><p>Warm interior.</p></section>
<section id="events" class="story-section events-section" data-amarktai-motion-scene><h2>Private catering and events</h2><p>Gatherings.</p></section>
<section id="testimonials" class="story-section testimonial-section" data-amarktai-motion-scene><h2>Testimonials</h2><p>Beloved craft.</p></section>
<section id="contact" class="story-section contact-section" data-amarktai-motion-scene><h2>Contact</h2><p>Visit us.</p></section>
</main>""")
    files = [
        {"path": "index.html", "language": "html", "content": html},
        {"path": "styles.css", "language": "css", "content": ""},
        {"path": "script.js", "language": "javascript", "content": ""},
        {"path": "README.md", "language": "markdown", "content": "# Luma & Stone"},
    ]
    repaired, changed = repair_static_design_family({"mode": "landing_page"}, BAKERY_PROMPT, {}, files, force=False)
    by_path = {f["path"]: f for f in repaired}

    assert "Luma & Stone" in by_path["index.html"]["content"]
    assert "preview-manifest.json" in by_path
    assert "motion_manifest.json" in by_path
    assert "amarktai.project.json" in by_path
    assert "preview-manifest.json" in changed
    assert json.loads(by_path["preview-manifest.json"]["content"])["entry"] == "index.html"


def test_ensure_required_files_does_not_request_reports_as_app_source():
    files, changed = ensure_required_files(
        {"mode": "landing_page"},
        BAKERY_PROMPT,
        {},
        [{"path": "index.html", "language": "html", "content": _bakery_html()}],
    )
    app_paths = [f["path"] for f in filter_app_source_files(files)]

    assert "content_quality_report.json" not in app_paths
    assert not any(re.search(r"(?:_report|-report)\\.json$", path) for path in app_paths)
    assert "index.html" in app_paths


def test_markdown_reviewer_output_is_structured():
    data = _parse_reviewer_tolerant_output("""
**Verdict:** needs_regeneration

**Issues:**
- styles.css does not match index.html
- preview-manifest.json is missing
""")

    assert data is not None
    assert data["verdict"] == "needs_regeneration"
    assert data["issues"] == [
        "styles.css does not match index.html",
        "preview-manifest.json is missing",
    ]
    assert data["patched_files"] == []


@pytest.mark.asyncio
async def test_reviewer_markdown_run_agent_does_not_raise_invalid_json():
    provider = MagicMock()
    provider.complete = AsyncMock(return_value={
        "text": "**Verdict:** needs_regeneration\n\n**Issues:**\n- styles.css does not match index.html",
        "model_label": "test-reviewer",
    })
    db = MagicMock()
    db.agent_events.insert_one = AsyncMock()
    db.messages.insert_one = AsyncMock()
    db.projects.update_one = AsyncMock()
    emitted = []
    async def emit(payload):
        emitted.append(payload)

    orch = Orchestrator(db, provider, "proj1", emit)
    result = await orch._run_agent("reviewer", "review", "files")

    assert result["data"]["verdict"] == "needs_regeneration"
    assert result["data"]["issues"] == ["styles.css does not match index.html"]
    assert result["data"]["patched_files"] == []


def test_reviewer_invalid_json_is_warning_only_for_preview_ready_static_files():
    files, _changed = ensure_required_files(
        {"mode": "landing_page"},
        BAKERY_PROMPT,
        {},
        [
            {"path": "index.html", "language": "html", "content": _bakery_html()},
            {"path": "styles.css", "language": "css", "content": ":root{--color-bg:#fff;--color-fg:#221}body{color:var(--color-fg)}"},
        ],
    )

    assert _parse_reviewer_tolerant_output("not json and not a reviewer audit") is None
    assert _static_reviewer_failure_can_continue(
        {"mode": "landing_page", "prompt": BAKERY_PROMPT},
        files,
    )


def test_markdown_needs_regeneration_triggers_coherent_static_repair():
    reviewer_data = _parse_reviewer_tolerant_output("""
**Verdict:** needs_regeneration

**Issues:**
- styles.css does not match index.html
- script.js targets missing selectors
""")
    files = [
        {"path": "index.html", "language": "html", "content": _bakery_html()},
        {"path": "styles.css", "language": "css", "content": ":root{--color-bg:#05070b;--color-fg:#fff}.hero{color:#00e676}"},
        {"path": "script.js", "language": "javascript", "content": "document.querySelector('.missing-motion').classList.add('x')"},
    ]

    assert reviewer_data["verdict"] == "needs_regeneration"
    repaired, changed = repair_static_design_family(
        {"mode": "landing_page"},
        BAKERY_PROMPT,
        {},
        files,
        force=True,
    )
    by_path = {f["path"]: f for f in repaired}

    assert {"index.html", "styles.css", "script.js"}.issubset(set(changed))
    assert "Luma & Stone" in by_path["index.html"]["content"]
    assert "#00e676" not in by_path["styles.css"]["content"].lower()
    assert ".missing-motion" not in by_path["script.js"]["content"]
    assert validate_project_files({"mode": "landing_page"}, repaired, prompt=BAKERY_PROMPT)["structureOk"]
