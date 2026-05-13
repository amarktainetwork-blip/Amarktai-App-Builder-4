"""
Capability Truth tests — Amarktai App Builder.

Covers:
  - async_capabilities_summary reads from get_secret_fn correctly
  - Settings-based keys override env vars
  - Qwen missing field detection (key set but model IDs missing)
  - Qwen recommended config completeness
  - GitHub PAT truth
  - All capabilities present in summary
"""
from __future__ import annotations

import asyncio
import os
import sys

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pytest

from app.core.capability_registry import (
    async_capabilities_summary,
    QWEN_DEFAULT_BASE_URL,
    QWEN_RECOMMENDED_MODELS,
    QWEN_ALT_BASE_URLS,
    QWEN_OPTIONAL_MODELS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: mock get_secret_fn
# ─────────────────────────────────────────────────────────────────────────────

def make_secret_fn(secrets: dict):
    """Return an async callable that mimics settings_store.get_secret."""
    async def _fn(key: str):
        return secrets.get(key) or None
    return _fn


# ─────────────────────────────────────────────────────────────────────────────
# Capability summary — no keys configured
# ─────────────────────────────────────────────────────────────────────────────

class TestCapabilityTruthNoKeys:
    def setup_method(self):
        # Ensure env vars don't bleed through
        for k in ["GENX_API_KEY", "QWEN_API_KEY", "GITHUB_PAT",
                   "QWEN_BASE_URL", "QWEN_MODEL_CHAT", "QWEN_MODEL_CODE",
                   "QWEN_MODEL_IMAGE", "QWEN_MODEL_VIDEO", "QWEN_MODEL_AUDIO"]:
            os.environ.pop(k, None)

    def test_all_unavailable_when_no_keys(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["text_generation"]["available"] is False
        assert summary["reasoning"]["available"] is False
        assert summary["image_generation"]["available"] is False
        assert summary["github_integration"]["available"] is False
        assert summary["qwen"]["available"] is False

    def test_preview_always_available(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["preview_generation"]["available"] is True

    def test_reasons_are_set_when_unavailable(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["text_generation"]["reason"] is not None
        assert summary["github_integration"]["reason"] is not None

    def test_required_keys_present_in_summary(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        required = [
            "text_generation", "reasoning", "vision", "image_generation",
            "video_generation", "audio", "repo_analysis", "long_context",
            "tool_use", "streaming", "github_integration",
            "preview_generation", "voice_generation", "qwen",
        ]
        for key in required:
            assert key in summary, f"Missing capability: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# Capability summary — GenX key configured via settings (DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestCapabilityTruthGenXFromSettings:
    def setup_method(self):
        os.environ.pop("GENX_API_KEY", None)

    def test_genx_available_from_settings(self):
        secrets = {"GENX_API_KEY": "sk-genx-test-key"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["text_generation"]["available"] is True
        assert summary["reasoning"]["available"] is True
        assert summary["image_generation"]["available"] is True

    def test_genx_env_fallback(self):
        os.environ["GENX_API_KEY"] = "sk-genx-env-key"
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["text_generation"]["available"] is True
        os.environ.pop("GENX_API_KEY", None)


# ─────────────────────────────────────────────────────────────────────────────
# Capability summary — GitHub PAT
# ─────────────────────────────────────────────────────────────────────────────

class TestCapabilityTruthGitHub:
    def setup_method(self):
        os.environ.pop("GITHUB_PAT", None)

    def test_github_available_from_settings(self):
        secrets = {"GITHUB_PAT": "ghp_testtoken"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["github_integration"]["available"] is True
        assert summary["github_integration"]["reason"] is None

    def test_github_unavailable_with_no_pat(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["github_integration"]["available"] is False
        assert "GITHUB_PAT" in summary["github_integration"]["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# Qwen truth — key set but models missing
# ─────────────────────────────────────────────────────────────────────────────

class TestCapabilityTruthQwen:
    def setup_method(self):
        for k in ["QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL_CHAT",
                   "QWEN_MODEL_CODE", "QWEN_MODEL_IMAGE", "QWEN_MODEL_VIDEO",
                   "QWEN_MODEL_AUDIO"]:
            os.environ.pop(k, None)

    def test_qwen_unavailable_when_no_key(self):
        summary = asyncio.run(async_capabilities_summary(make_secret_fn({})))
        assert summary["qwen"]["available"] is False

    def test_qwen_available_when_key_set(self):
        secrets = {"QWEN_API_KEY": "sk-qwen-test"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["qwen"]["available"] is True
        assert summary["qwen"]["api_key_set"] is True

    def test_qwen_reports_missing_models(self):
        # Key set but no models
        secrets = {"QWEN_API_KEY": "sk-qwen-test"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        missing = summary["qwen"]["missing"]
        assert len(missing) > 0, "Should report missing model IDs"
        assert "QWEN_MODEL_CHAT" in missing
        assert "QWEN_MODEL_CODE" in missing

    def test_qwen_no_missing_when_fully_configured(self):
        secrets = {
            "QWEN_API_KEY": "sk-qwen-test",
            "QWEN_BASE_URL": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "QWEN_MODEL_CHAT": "qwen3-max",
            "QWEN_MODEL_CODE": "qwen3-coder-plus",
            "QWEN_MODEL_IMAGE": "qwen-image-plus",
            "QWEN_MODEL_VIDEO": "qwen3-omni-flash",
            "QWEN_MODEL_AUDIO": "qwen3-asr-flash",
        }
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["qwen"]["missing"] == []

    def test_qwen_video_unavailable_without_video_model(self):
        secrets = {"QWEN_API_KEY": "sk-qwen-test"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["video_generation"]["available"] is False
        # The reason should mention the specific missing field
        assert summary["video_generation"]["reason"] is not None

    def test_qwen_video_available_with_model(self):
        secrets = {"QWEN_API_KEY": "sk-qwen-test", "QWEN_MODEL_VIDEO": "qwen3-omni-flash"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["video_generation"]["available"] is True

    def test_qwen_reason_mentions_specific_missing_key(self):
        # Key set but no video model
        secrets = {"QWEN_API_KEY": "sk-qwen-test"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        reason = summary["video_generation"]["reason"]
        assert reason is not None
        # Must name the missing key, not be vague
        assert "QWEN_MODEL_VIDEO" in reason or "not configured" in reason


# ─────────────────────────────────────────────────────────────────────────────
# Qwen defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestQwenDefaults:
    def test_default_base_url_set(self):
        assert QWEN_DEFAULT_BASE_URL.startswith("https://")
        assert "dashscope" in QWEN_DEFAULT_BASE_URL

    def test_alt_base_urls_not_empty(self):
        assert len(QWEN_ALT_BASE_URLS) >= 3

    def test_recommended_models_complete(self):
        required_keys = {
            "QWEN_MODEL_CHAT", "QWEN_MODEL_CODE", "QWEN_MODEL_IMAGE",
            "QWEN_MODEL_VIDEO", "QWEN_MODEL_AUDIO",
        }
        assert required_keys == set(QWEN_RECOMMENDED_MODELS.keys())

    def test_recommended_model_values_non_empty(self):
        for key, model in QWEN_RECOMMENDED_MODELS.items():
            assert model, f"{key} has empty recommended model"

    def test_optional_models_not_empty(self):
        assert len(QWEN_OPTIONAL_MODELS) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# Settings-DB takes precedence over env vars
# ─────────────────────────────────────────────────────────────────────────────

class TestSettingsPrecedence:
    def test_settings_key_overrides_env(self):
        os.environ["GENX_API_KEY"] = ""  # Empty env var
        secrets = {"GENX_API_KEY": "sk-from-db"}
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["text_generation"]["available"] is True
        os.environ.pop("GENX_API_KEY", None)

    def test_env_fallback_when_settings_empty(self):
        os.environ["GITHUB_PAT"] = "ghp_from_env"
        secrets = {}  # Nothing in DB
        summary = asyncio.run(async_capabilities_summary(make_secret_fn(secrets)))
        assert summary["github_integration"]["available"] is True
        os.environ.pop("GITHUB_PAT", None)
