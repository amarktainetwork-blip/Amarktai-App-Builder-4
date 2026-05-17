import json
from pathlib import Path

import pytest

from agents.build_contract import (
    filter_app_source_files,
    premium_static_fallback_files,
    validate_project_files,
)
from app.services.avatar_runtime_service import execute_avatar_pipeline
from app.services.build_contract_service import final_gate_blockers
from app.services.capability_truth_service import CapabilityTruthService
from app.services.model_router import get_router_status
from app.services.tier_service import normalize_quality_tier, repair_attempt_limit


def test_legacy_tiers_map_to_public_tiers():
    assert normalize_quality_tier("cheap") == "standard"
    assert normalize_quality_tier("balanced") == "standard"
    assert normalize_quality_tier("standard") == "standard"
    assert normalize_quality_tier("premium") == "premium"
    assert repair_attempt_limit("balanced") == 2
    assert repair_attempt_limit("premium") == 3


def test_report_files_are_filtered_from_agent_app_payloads():
    files = [
        {"path": "index.html", "content": "<main></main>"},
        {"path": "content_quality_report.json", "content": "{}"},
        {"path": "runtime-qa/runtime-qa-report.json", "content": "{}"},
        {"path": "media_manifest.json", "content": "{}"},
    ]
    assert [item["path"] for item in filter_app_source_files(files)] == ["index.html"]


def test_missing_content_quality_report_is_not_required_app_file(tmp_path: Path):
    files = premium_static_fallback_files("Create a premium cinematic one-page website for Amarktai Builder")
    validation = validate_project_files({"mode": "landing_page", "quality_tier": "premium"}, files)
    assert "Missing required file: content_quality_report.json" not in validation["errors"]
    for item in files:
        (tmp_path / item["path"]).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / item["path"]).write_text(item["content"], encoding="utf-8")
    blockers = final_gate_blockers(
        tmp_path,
        mode="landing_page",
        quality_tier="premium",
        media_required=False,
        motion_required=False,
        runtime_required=False,
    )
    assert "Missing content_quality_report.json." not in blockers


def test_router_status_exposes_agent_routes():
    result = get_router_status(["claude-sonnet-4-6", "gemini-2.5-flash", "kling-avatar-v2-pro"])
    assert "agents" in result
    assert "tasks" in result
    assert result["agents"]["planner"]["task_type"] == "research"
    assert result["agents"]["media_director"]["required_capabilities"]
    assert result["agents"]["github_pr_agent"]["task_type"] == "repo_audit"


@pytest.mark.asyncio
async def test_capability_truth_shape_includes_optional_open_source_hooks():
    async def resolver(key: str):
        return {"value": None, "source": "missing", "configured": False}

    truth = await CapabilityTruthService(resolver).build()
    for key in [
        "runtime_qa",
        "preview_generation",
        "deployment_finalize",
        "whisper_stt",
        "faiss_vector_memory",
        "stable_diffusion_fallback",
        "musicgen_fallback",
        "orchestration_graph",
    ]:
        assert key in truth["capabilities"]
        assert "live_status" in truth["capabilities"][key]


@pytest.mark.asyncio
async def test_avatar_pipeline_requires_remote_urls_for_provider_video(monkeypatch, tmp_path: Path):
    (tmp_path / "index.html").write_text("<main></main>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("", encoding="utf-8")
    (tmp_path / "script.js").write_text("", encoding="utf-8")

    async def fake_generate(**kwargs):
        category = kwargs.get("category")
        return {
            "ok": True,
            "bytes": b"asset-bytes",
            "content_type": "audio/mpeg" if category == "voice" else "image/png",
            "job_id": f"job-{category}",
            "status": "succeeded",
            "result_url": "",
        }

    import app.services.avatar_runtime_service as avatar_service

    monkeypatch.setattr(avatar_service, "generate_genx_media_job", fake_generate)
    monkeypatch.setattr(
        avatar_service,
        "_write_asset",
        lambda workspace, **kwargs: {
            "path": f"media/{kwargs['media_type']}.bin",
            "remote_url": "",
            "mime_type": kwargs.get("content_type"),
            "size_bytes": len(kwargs.get("content") or b""),
        },
    )
    manifest = await execute_avatar_pipeline(
        tmp_path,
        project_id="p1",
        prompt="Create an AI sales-agent page",
        genx_api_key="gnxk_test",
        genx_runtime={
            "capability_models": {
                "avatar": [{"id": "kling-avatar-v2-pro"}],
                "image": [{"id": "gpt-image-2"}],
                "voice": [{"id": "genxlm-voice-v1"}],
            }
        },
    )
    assert manifest["status"] == "fallback"
    assert "provider-accessible image and audio URLs" in json.dumps(manifest["attempts"])
    assert (tmp_path / "avatar_manifest.json").exists()
