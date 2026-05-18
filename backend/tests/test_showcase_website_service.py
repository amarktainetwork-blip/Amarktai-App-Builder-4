import json


def test_showcase_uses_capability_truth_labels_without_faking_setup_needed(tmp_path):
    from app.services.showcase_website_service import write_showcase_workspace

    truth = {
        "capabilities": {
            "image_generation": {
                "end_to_end_available": True,
                "dashboard_label": "End-to-end available",
            },
            "avatar_generation": {
                "end_to_end_available": False,
                "capability_status": "setup_needed",
                "dashboard_label": "Setup needed",
                "reason": "Provider runtime proof missing.",
            },
        }
    }
    result = write_showcase_workspace(tmp_path, truth)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "showcase-manifest.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert "End-to-end available" in html
    assert "Setup needed" in html
    assert "Avatar systems" in html
    assert manifest["truthful_capability_labels"] is True
    assert manifest["fake_provider_claims"] is False


def test_showcase_output_passes_premium_design_qa(tmp_path):
    from app.services.showcase_website_service import write_showcase_workspace
    from app.services.premium_design_qa_service import run_premium_design_qa

    write_showcase_workspace(tmp_path, {"capabilities": {}})
    report = run_premium_design_qa(tmp_path, prompt="premium cinematic showcase website")

    assert report["ok"] is True
    assert report["score"] >= 78
    assert "reduced_motion" in report["motion_systems"]
