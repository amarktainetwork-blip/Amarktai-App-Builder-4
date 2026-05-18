import json
from pathlib import Path


def _ember_fixture(root: Path, project_id: str) -> Path:
    ws = root / "generated" / project_id
    (ws / "media").mkdir(parents=True)
    (ws / "runtime-qa").mkdir()
    (ws / "media" / "fallback-1.png").write_bytes(b"png")
    (ws / "media" / "fallback-2.png").write_bytes(b"png")
    (ws / "media" / "stock.mp4").write_bytes(b"mp4")
    (ws / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main>"
        "<section id='hero'><img data-amarktai-media-asset src='media/fallback-1.png' alt='Hero'></section>"
        "<section id='menu'></section><section id='story'></section><section id='gallery'></section><section id='contact'></section>"
        "</main></body></html>",
        encoding="utf-8",
    )
    (ws / "styles.css").write_text("@media (max-width:700px){main{display:block}}", encoding="utf-8")
    (ws / "media_manifest.json").write_text(json.dumps({
        "status": "stock",
        "asset_count": 3,
        "assets": [
            {"source": "pixabay", "media_type": "video", "section": "hero", "path": "media/stock.mp4"},
            {"source": "local_runtime_fallback", "media_type": "image", "section": "hero", "path": "media/fallback-1.png"},
            {"source": "local_runtime_fallback", "media_type": "image", "section": "hero", "path": "media/fallback-2.png"},
        ],
        "attempts": [
            {"provider": "genx", "ok": False, "error": "GenX generate HTTP 400: params is required"},
            {"provider": "qwen", "ok": False, "error": "qwen image endpoint HTTP 404"},
            {"provider": "pixabay", "ok": False, "status": "rate_limited", "reason": "429 Too Many Requests"},
        ],
        "section_alignment": {
            "expected_sections": ["hero", "menu", "story", "gallery", "contact"],
            "aligned_sections": ["hero"],
            "missing_sections": ["menu", "story", "gallery", "contact"],
            "hero_only": True,
        },
    }), encoding="utf-8")
    (ws / "runtime-qa" / "runtime-qa-report.json").write_text(json.dumps({
        "pass": False,
        "blockers": ["Broken runtime media assets detected: 1."],
        "warnings": ["axe-core setup-needed", "Lighthouse failed because CHROME_PATH is not set"],
        "media_assets": {"broken": [{"src": "media/missing.png"}]},
        "screenshots": {"desktop": "runtime-qa/screenshots/desktop.png"},
        "accessibility": {"available": False, "tool_unavailable": True},
        "performance": {"available": False, "reason": "CHROME_PATH is not set"},
    }), encoding="utf-8")
    (ws / "quality-report.json").write_text(json.dumps({"pass": True, "score": 100, "blockers": [], "warnings": []}), encoding="utf-8")
    return ws


def test_audit_extracts_provider_failures_and_hero_only_alignment(tmp_path):
    from scripts.audit_project_build_quality import audit_project

    project_id = "284c4875-a5bd-4224-9fc8-a99263b7e2b4"
    _ember_fixture(tmp_path, project_id)
    report = audit_project(project_id, tmp_path)

    assert report["project_id"] == project_id
    assert len(report["provider_attempt_failures"]) == 3
    assert report["media_manifest_summary"]["section_alignment"]["hero_only"] is True
    assert "Provider execution failures were recorded." in report["exact_blockers"]


def test_audit_flags_quality_100_with_runtime_failure_as_inconsistent(tmp_path):
    from scripts.audit_project_build_quality import audit_project

    project_id = "ember-quality"
    _ember_fixture(tmp_path, project_id)
    report = audit_project(project_id, tmp_path)

    assert report["quality_report_score"] == 100
    assert any("score is 100" in blocker for blocker in report["exact_blockers"])
    assert report["final_verdict"] == "needs_attention"
