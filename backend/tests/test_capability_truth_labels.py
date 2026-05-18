import asyncio


async def _resolver(secrets):
    async def resolve(key: str):
        if key in secrets:
            return {"value": secrets[key], "configured": bool(secrets[key]), "source": "settings"}
        return {"value": None, "configured": False, "source": "missing"}
    return resolve


def _genx_probe():
    return {
        "genx": {
            "live_status": "live_ok",
            "runtime": {
                "capabilities": {"image": True},
                "capability_models": {"image": [{"id": "gpt-image-2"}]},
                "models": [{"id": "gpt-image-2", "category": "image", "capabilities": ["image"]}],
            },
        }
    }


def test_provider_discovered_does_not_mean_dashboard_available():
    from app.services.capability_truth_service import CapabilityTruthService

    service = CapabilityTruthService(
        asyncio.run(_resolver({"GENX_API_KEY": "key"})),
        cached_probes=_genx_probe(),
    )
    truth = asyncio.run(service.build())
    image = truth["capabilities"]["image_generation"]

    assert image["available"] is True
    assert image["end_to_end_available"] is False
    assert image["capability_status"] == "provider_discovered"
    assert image["dashboard_label"] == "Provider discovered"


def test_runtime_failed_label_uses_latest_build_evidence():
    from app.services.capability_truth_service import CapabilityTruthService

    service = CapabilityTruthService(
        asyncio.run(_resolver({"GENX_API_KEY": "key"})),
        cached_probes=_genx_probe(),
        latest_build_evidence={"image_generation": {"runtime_call_tested": True, "runtime_call_failed": True, "reason": "params is required"}},
    )
    truth = asyncio.run(service.build())

    assert truth["capabilities"]["image_generation"]["capability_status"] == "runtime_failed"
    assert truth["capabilities"]["image_generation"]["dashboard_label"] == "Runtime failed"


def test_full_artifact_chain_can_show_end_to_end_available():
    from app.services.capability_truth_service import CapabilityTruthService

    proof = {
        "runtime_call_tested": True,
        "runtime_call_passed": True,
        "artifact_persisted": True,
        "used_in_latest_build": True,
        "visible_in_preview": True,
        "final_gate_enforced": True,
    }
    service = CapabilityTruthService(
        asyncio.run(_resolver({"GENX_API_KEY": "key"})),
        cached_probes=_genx_probe(),
        latest_build_evidence={"image_generation": proof},
    )
    truth = asyncio.run(service.build())

    assert truth["capabilities"]["image_generation"]["end_to_end_available"] is True
    assert truth["capabilities"]["image_generation"]["dashboard_label"] == "End-to-end available"


def test_optional_setup_needed_features_stay_setup_needed_or_optional():
    from app.services.capability_truth_service import CapabilityTruthService

    service = CapabilityTruthService(asyncio.run(_resolver({})))
    truth = asyncio.run(service.build())

    assert truth["capabilities"]["stable_diffusion_fallback"]["capability_status"] in {"optional", "setup_needed"}
    assert truth["capabilities"]["musicgen_fallback"]["end_to_end_available"] is False
