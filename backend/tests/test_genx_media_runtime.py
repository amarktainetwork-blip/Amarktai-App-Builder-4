import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body><main><section id='hero'><h1>Ember & Crumb</h1></section>"
        "<section id='gallery'></section><section id='menu'></section></main></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "styles.css").write_text("@media (max-width:700px){main{display:block}}", encoding="utf-8")
    return tmp_path


def test_genx_payload_includes_required_params():
    from app.services.genx_runtime_service import build_genx_generate_payload

    payload = build_genx_generate_payload(
        model="gpt-image-2",
        prompt="premium bakery hero",
        category="image",
        extra={"size": "1792x1024"},
    )

    assert payload["params"]["prompt"] == "premium bakery hero"
    assert payload["params"]["size"] == "1792x1024"
    assert payload["model"] == "gpt-image-2"


@pytest.mark.asyncio
async def test_successful_genx_media_response_persists_and_injects(tmp_path):
    from app.services import media_runtime_service as svc

    ws = _workspace(tmp_path)
    with patch.object(svc, "generate_genx_media_job", AsyncMock(return_value={
        "ok": True,
        "provider": "genx",
        "model": "gpt-image-2",
        "category": "image",
        "status": "succeeded",
        "bytes": PNG_1X1,
        "content_type": "image/png",
        "result_url": "https://genx.test/result.png",
    })):
        manifest = await svc.execute_media_plan(
            ws,
            project_id="genx-ok",
            prompt="premium cinematic bakery gallery menu story website",
            sections=["hero", "gallery", "menu"],
            genx_api_key="key",
            genx_image_model="gpt-image-2",
            allow_stock_fallback=False,
        )

    assert manifest["assets"][0]["source"] == "genx"
    assert manifest["persisted"] is True
    assert manifest["injected"] is True
    assert (ws / manifest["assets"][0]["path"]).exists()
    assert "data-amarktai-media-asset" in (ws / "index.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_genx_response_marks_runtime_failed_not_available(tmp_path):
    from app.services import media_runtime_service as svc

    ws = _workspace(tmp_path)
    with patch.object(svc, "generate_genx_media_job", AsyncMock(return_value={
        "ok": False,
        "provider": "genx",
        "status": "submit_failed",
        "error": "GenX generate HTTP 400: params is required",
    })):
        manifest = await svc.execute_media_plan(
            ws,
            project_id="genx-fail",
            prompt="premium cinematic bakery gallery menu story website",
            sections=["hero", "gallery", "menu"],
            genx_api_key="key",
            genx_image_model="gpt-image-2",
            allow_stock_fallback=False,
        )

    persisted = json.loads((ws / "media_manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_call_failed"] is True
    assert persisted["runtime_call_failed"] is True
    assert manifest["status"] == "fallback"
    assert manifest["premium_media_complete"] is False
