import json

from agents.coverage_score import compute_coverage_score
from app.services.build_contract_service import final_gate_blockers
from app.services.media_runtime_service import _filter_relevant_pixabay_assets, _media_queries
from app.services.quality_gate_service import run_quality_gate


def _static_workspace(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head>'
        '<body><main><section id="hero"><h1>Luma & Stone Bakery</h1>'
        '<p>Warm artisan sourdough, seasonal pastries, and coffee.</p></section></main></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "styles.css").write_text(
        ":root{--earth:#8b5e34}.hero{display:grid}@media (max-width:700px){.hero{display:block}}",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Luma & Stone\n", encoding="utf-8")
    (tmp_path / "amarktai.project.json").write_text('{"mode":"landing_page"}', encoding="utf-8")
    (tmp_path / "preview-manifest.json").write_text('{"status":"ready","entry":"index.html","preview_url":"/preview"}', encoding="utf-8")
    return tmp_path


def test_bakery_media_queries_are_industry_specific():
    prompt = "Build a cinematic premium one-page website for a luxury artisan bakery called Luma & Stone."
    queries = _media_queries(prompt, ["hero", "pastries", "coffee"])

    assert queries[:3] == ["artisan bakery", "sourdough bread", "pastry cafe"]
    assert not any("software" in q or "dashboard" in q or "artificial intelligence" in q for q in queries)


def test_bakery_pixabay_conflict_assets_are_rejected():
    prompt = "Build a luxury artisan bakery website with sourdough, pastries, and coffee."
    assets = [
        {"title": "Software dashboard", "tags": "software, computer, logistics"},
        {"title": "Fresh sourdough", "tags": "bread, bakery, pastry cafe"},
    ]

    accepted, rejected = _filter_relevant_pixabay_assets(
        assets,
        prompt=prompt,
        sections=["hero", "gallery"],
        media_type="image",
    )

    assert len(accepted) == 1
    assert accepted[0]["title"] == "Fresh sourdough"
    assert rejected and rejected[0]["reason"].startswith("conflicting_")


def test_static_runtime_qa_tooling_failure_warns_and_locks_finalize(tmp_path, monkeypatch):
    ws = _static_workspace(tmp_path)

    def fake_runtime_qa(_workspace):
        return {
            "pass": False,
            "blockers": [
                "axe-core source is not available to the backend runtime.",
                "Lighthouse did not produce a report because CHROME_PATH is missing.",
            ],
            "report_path": str(ws / "runtime-qa" / "runtime-qa-report.json"),
        }

    monkeypatch.setattr("app.services.quality_gate_service.run_runtime_qa", fake_runtime_qa)

    result = run_quality_gate(ws, require_runtime=True, prompt="Luxury artisan bakery landing page", mode="landing_page")

    assert result["pass"] is True
    assert any(w["check"] == "runtime_qa" for w in result["warnings"])
    assert result["checks"]["runtime_qa"]["finalize_locked"] is True


def test_static_runtime_qa_missing_scores_and_broken_refs_warn_and_lock_finalize(tmp_path, monkeypatch):
    ws = _static_workspace(tmp_path)

    def fake_runtime_qa(_workspace):
        return {
            "pass": False,
            "accessibility": {"available": False, "score": 0},
            "performance": {"available": False, "score": 0},
            "blockers": [
                "axe-core source is not available to the backend runtime.",
                "Accessibility score 0 below 90.",
                "Lighthouse execution failed: CHROME_PATH missing.",
                "Performance score 0 below 70.",
                "Broken runtime links detected: 1.",
                "Broken runtime media assets detected: 1.",
            ],
            "report_path": str(ws / "runtime-qa" / "runtime-qa-report.json"),
        }

    monkeypatch.setattr("app.services.quality_gate_service.run_runtime_qa", fake_runtime_qa)

    result = run_quality_gate(ws, require_runtime=True, prompt="Luxury artisan bakery landing page", mode="landing_page")

    assert result["pass"] is True
    assert result["checks"]["runtime_qa"]["warning"] is True
    assert result["checks"]["runtime_qa"]["finalize_locked"] is True


def test_static_source_broken_media_warning_locks_finalize_without_failing_preview(tmp_path):
    ws = _static_workspace(tmp_path)
    html = (ws / "index.html").read_text(encoding="utf-8").replace(
        "</section>",
        '<img src="media/missing.jpg" alt="Bakery table"></section>',
    )
    (ws / "index.html").write_text(html, encoding="utf-8")

    result = run_quality_gate(ws, prompt="Luxury bakery landing page", mode="landing_page")

    assert result["pass"] is True
    assert result["checks"]["broken_assets"]["warning"] is True
    assert result["checks"]["broken_assets"]["finalize_locked"] is True


def test_static_runtime_qa_missing_core_files_still_blocks(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html><body><main>Hello</main></body></html>", encoding="utf-8")

    def fake_runtime_qa(_workspace):
        return {
            "pass": False,
            "blockers": ["axe-core source is not available to the backend runtime."],
            "report_path": str(tmp_path / "runtime-qa" / "runtime-qa-report.json"),
        }

    monkeypatch.setattr("app.services.quality_gate_service.run_runtime_qa", fake_runtime_qa)

    result = run_quality_gate(tmp_path, require_runtime=True, prompt="Landing page", mode="landing_page")

    assert result["pass"] is False
    assert any(item["check"] == "runtime_qa" for item in result["blockers"])


def test_inert_static_cta_is_repaired_to_contact_anchor(tmp_path):
    ws = _static_workspace(tmp_path)
    html = (ws / "index.html").read_text(encoding="utf-8").replace(
        "</main>",
        '<section id="contact"><h2>Contact</h2></section><a class="button primary" href="#">Book tasting</a><button class="button">Plan an event</button></main>',
    )
    (ws / "index.html").write_text(html, encoding="utf-8")

    result = run_quality_gate(ws, prompt="Luxury bakery landing page", mode="landing_page")
    repaired_html = (ws / "index.html").read_text(encoding="utf-8")

    assert result["pass"] is True
    assert not any(item["check"] == "dead_ctas" for item in result["warnings"])
    assert 'href="#contact"' in repaired_html
    assert any(item["type"] == "dead_cta_repair" for item in result["fixes_applied"])


def test_nav_toggle_and_testimonial_buttons_with_handlers_are_not_dead_ctas(tmp_path):
    ws = _static_workspace(tmp_path)
    (ws / "index.html").write_text(
        '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head>'
        '<body><button class="nav-toggle" type="button" aria-label="Open menu">Menu</button>'
        '<section id="hero"><h1>Luma</h1></section>'
        '<button class="testimonial-next" type="button" aria-label="Next testimonial">Next</button>'
        '<script src="script.js"></script></body></html>',
        encoding="utf-8",
    )
    (ws / "script.js").write_text(
        "document.querySelector('.nav-toggle')?.addEventListener('click',()=>{});"
        "document.querySelector('.testimonial-next')?.addEventListener('click',()=>{});",
        encoding="utf-8",
    )

    result = run_quality_gate(ws, prompt="Luxury bakery landing page", mode="landing_page")

    assert not any(item["check"] == "dead_ctas" for item in result["warnings"])
    assert result["checks"]["dead_ctas"]["ok"] is True


def test_final_gate_runtime_artifacts_warn_for_static_preview_but_block_finalize(tmp_path):
    ws = _static_workspace(tmp_path)

    default_blockers = final_gate_blockers(
        ws,
        mode="landing_page",
        quality_tier="premium",
        runtime_required=True,
    )
    warning_policy_blockers = final_gate_blockers(
        ws,
        mode="landing_page",
        quality_tier="premium",
        runtime_required=True,
        allow_static_runtime_warnings=True,
    )

    assert any("runtime QA artifact" in b for b in default_blockers)
    assert not any("runtime QA artifact" in b for b in warning_policy_blockers)


def test_static_media_no_relevant_stock_fallback_does_not_block_preview_ready(tmp_path):
    ws = _static_workspace(tmp_path)
    (ws / "media_manifest.json").write_text(
        json.dumps({"status": "fallback", "reason": "no_relevant_media_found", "assets": [], "asset_count": 0}),
        encoding="utf-8",
    )

    default_blockers = final_gate_blockers(
        ws,
        mode="landing_page",
        quality_tier="premium",
        media_required=True,
    )
    warning_policy_blockers = final_gate_blockers(
        ws,
        mode="landing_page",
        quality_tier="premium",
        media_required=True,
        allow_static_media_fallback_warnings=True,
    )

    assert any("persisted media assets" in b for b in default_blockers)
    assert not any("persisted media assets" in b for b in warning_policy_blockers)


def test_static_landing_coverage_does_not_require_docker_or_env():
    files = [
        {"path": "index.html", "content": '<html><head><link rel="stylesheet" href="styles.css"></head><body><section>Bakery</section></body></html>'},
        {"path": "styles.css", "content": ":root{--x:#fff}.hero{display:grid}@media(max-width:700px){.hero{display:block}}"},
        {"path": "README.md", "content": "# Bakery"},
        {"path": "amarktai.project.json", "content": "{}"},
        {"path": "preview-manifest.json", "content": "{}"},
    ]

    result = compute_coverage_score(
        "Build a responsive landing page. Do NOT reference deployment systems.",
        files,
        mode="landing_page",
        preview_fallback={"canPreview": True},
    )

    assert result["requestSatisfied"] is True
    assert not any("Docker" in item or ".env" in item for item in result["missingRequirements"])


def test_static_preview_manifest_ready_satisfies_preview_evidence():
    files = [
        {"path": "index.html", "content": "<html><body>Bakery</body></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "README.md", "content": "# Bakery"},
        {"path": "amarktai.project.json", "content": "{}"},
        {"path": "preview-manifest.json", "content": '{"status":"ready","entry":"index.html"}'},
    ]

    result = compute_coverage_score("Build landing page", files, mode="landing_page")

    assert "preview or preview fallback available" in result["checkedRequirements"]
    assert "preview or preview fallback available" not in result["missingRequirements"]


def test_static_project_manifest_preview_entry_satisfies_preview_evidence():
    files = [
        {"path": "index.html", "content": "<html><body>Bakery</body></html>"},
        {"path": "styles.css", "content": "body{}"},
        {"path": "README.md", "content": "# Bakery"},
        {"path": "amarktai.project.json", "content": '{"preview":{"entry":"index.html"}}'},
    ]

    result = compute_coverage_score("Build landing page", files, mode="landing_page")

    assert "preview or preview fallback available" in result["checkedRequirements"]


def test_full_stack_without_preview_keeps_stricter_preview_requirement():
    files = [
        {"path": "README.md", "content": "# API"},
        {"path": "server.py", "content": "from fastapi import FastAPI\napp=FastAPI()"},
    ]

    result = compute_coverage_score("Build a full stack API", files, mode="full_stack")

    assert "preview or preview fallback available" in result["missingRequirements"]


def test_full_stack_coverage_still_requires_docker_and_env():
    files = [
        {"path": "README.md", "content": "# API"},
        {"path": "server.py", "content": "from fastapi import FastAPI\napp=FastAPI()"},
    ]

    result = compute_coverage_score(
        "Build and deploy a full stack API service.",
        files,
        mode="full_stack",
        preview_fallback={"canPreview": True},
    )

    assert any("Docker configuration present" in item for item in result["missingRequirements"])
    assert any(".env.example present" in item for item in result["missingRequirements"])
