from __future__ import annotations

import os
import sys

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


class FakeSettingsCollection:
    def __init__(self, docs=None):
        self.docs = {doc["key"]: dict(doc) for doc in (docs or [])}
        self.updated = []

    async def find_one(self, query, projection=None):
        return self.docs.get(query.get("key"))

    async def update_one(self, query, update, upsert=False):
        key = query.get("key")
        self.updated.append((query, update))
        if key in self.docs and "$set" in update:
            self.docs[key].update(update["$set"])


class FakeUsersCollection:
    async def find_one(self, query, projection=None):
        return {"id": "admin-1"}


class FakeDB:
    def __init__(self, settings_docs=None, ping_ok=True):
        self.settings = FakeSettingsCollection(settings_docs)
        self.users = FakeUsersCollection()
        self.ping_ok = ping_ok

    async def command(self, name):
        if not self.ping_ok:
            raise RuntimeError("mongo down")
        return {"ok": 1}


def clear_provider_env(monkeypatch):
    for key in [
        "GENX_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY", "PIXABAY_API_KEY",
        "QWEN_API_KEY", "QWEN_MODEL_CHAT", "QWEN_MODEL_CODE", "QWEN_MODEL_IMAGE",
        "QWEN_MODEL_VIDEO", "QWEN_MODEL_AUDIO",
    ]:
        monkeypatch.delenv(key, raising=False)


async def fake_resolver_from_db(fake_db, key):
    from settings_store import safe_get_secret
    return await safe_get_secret(fake_db, key, env_fallback=True)


def test_safe_get_secret_decrypt_failure_falls_back_to_env(monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    from settings_store import safe_get_secret

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    bad_value = Fernet(old_key.encode()).encrypt(b"old-secret").decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("GENX_API_KEY", "env-genx-key")
    fake_db = FakeDB([{"key": "GENX_API_KEY", "encrypted_value": bad_value}])

    result = asyncio.run(safe_get_secret(fake_db, "GENX_API_KEY"))

    assert result["value"] == "env-genx-key"
    assert result["source"] == "env"
    assert result["configured"] is True
    assert result["error"] == "decrypt_failed"
    assert fake_db.settings.docs["GENX_API_KEY"]["status"] == "decrypt_failed"


def test_capability_truth_models_unavailable_when_provider_key_missing(monkeypatch):
    import asyncio
    from app.services.capability_truth_service import CapabilityTruthService

    clear_provider_env(monkeypatch)
    fake_db = FakeDB()
    service = CapabilityTruthService(lambda key: fake_resolver_from_db(fake_db, key))
    truth = asyncio.run(service.build())

    assert truth["providers"]["genx"]["configured"] is False
    assert truth["capabilities"]["text_generation"]["available"] is False
    genx_models = [m for m in truth["models"] if m["provider"] == "genx"]
    assert genx_models
    assert all(m["available"] is False for m in genx_models)
    assert all(m["unavailable_reason"] == "GENX_API_KEY not configured" for m in genx_models)


def test_configured_but_not_live_tested_is_not_available(monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    from app.services.capability_truth_service import CapabilityTruthService

    clear_provider_env(monkeypatch)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    encrypted = Fernet(key.encode()).encrypt(b"settings-genx-key").decode()
    fake_db = FakeDB([{"key": "GENX_API_KEY", "encrypted_value": encrypted}])
    service = CapabilityTruthService(lambda key: fake_resolver_from_db(fake_db, key))
    truth = asyncio.run(service.build())

    assert truth["providers"]["genx"]["configured"] is True
    assert truth["providers"]["genx"]["live_status"] == "not_tested"
    assert truth["capabilities"]["text_generation"]["available"] is False
    assert truth["capabilities"]["text_generation"]["configured"] is True
    genx_models = [m for m in truth["models"] if m["provider"] == "genx"]
    assert all(m["available"] is False for m in genx_models)


def test_live_ok_provider_marks_models_available(monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    from app.services.capability_truth_service import CapabilityTruthService

    clear_provider_env(monkeypatch)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    encrypted = Fernet(key.encode()).encrypt(b"settings-genx-key").decode()
    fake_db = FakeDB([{"key": "GENX_API_KEY", "encrypted_value": encrypted}])
    service = CapabilityTruthService(
        lambda key: fake_resolver_from_db(fake_db, key),
        cached_probes={"genx": {"status": "key_present_live_ok", "probed_at": "2026-05-13T00:00:00+00:00"}},
    )
    truth = asyncio.run(service.build())

    assert truth["providers"]["genx"]["live_status"] == "live_ok"
    assert truth["capabilities"]["text_generation"]["available"] is True
    genx_models = [m for m in truth["models"] if m["provider"] == "genx"]
    assert all(m["available"] is True for m in genx_models)


def test_qwen_models_unavailable_without_qwen_key(monkeypatch):
    import asyncio
    from app.services.capability_truth_service import CapabilityTruthService

    clear_provider_env(monkeypatch)
    monkeypatch.setenv("QWEN_MODEL_CHAT", "qwen3-max")
    fake_db = FakeDB()
    service = CapabilityTruthService(lambda key: fake_resolver_from_db(fake_db, key))
    truth = asyncio.run(service.build())

    assert truth["providers"]["qwen"]["configured"] is False
    qwen_models = [m for m in truth["models"] if m["provider"] == "qwen"]
    assert qwen_models
    assert all(m["available"] is False for m in qwen_models)
    assert all(m["unavailable_reason"] == "QWEN_API_KEY not configured" for m in qwen_models)


def test_capabilities_endpoint_does_not_crash_with_corrupt_setting(monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    import server

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    bad_value = Fernet(old_key.encode()).encrypt(b"old-secret").decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", new_key)
    monkeypatch.delenv("GENX_API_KEY", raising=False)
    monkeypatch.setattr(server, "db", FakeDB([{"key": "GENX_API_KEY", "encrypted_value": bad_value}]))

    result = asyncio.run(server.capabilities_status())

    assert "summary" in result
    assert result["providers"]["genx"]["source"] == "decrypt_failed"
    assert result["summary"]["text_generation"]["available"] is False
    assert result["errors"] == []


def test_readiness_missing_genx_returns_structured_fail(monkeypatch):
    import asyncio
    import server

    clear_provider_env(monkeypatch)
    monkeypatch.setattr(server, "db", FakeDB())

    result = asyncio.run(server.readiness())

    assert result["overall"] == "FAIL"
    assert result["blockers"]
    assert any(check["name"] == "GenX API key" and check["status"] == "FAIL" for check in result["checks"])
    assert "providers" in result


def test_readiness_refreshes_provider_probe_cache(monkeypatch):
    import asyncio
    import server

    calls = []

    async def fake_probe_all_providers(**kwargs):
        calls.append(kwargs)
        server._probe_svc._CACHE["all_providers"] = {
            "genx": {"provider": "genx", "status": "key_present_live_ok", "probed_at": "2026-05-13T00:00:00+00:00"},
            "github": {"provider": "github", "status": "key_missing", "probed_at": "2026-05-13T00:00:00+00:00"},
            "brave": {"provider": "brave", "status": "key_missing", "probed_at": "2026-05-13T00:00:00+00:00"},
            "pixabay": {"provider": "pixabay", "status": "key_missing", "probed_at": "2026-05-13T00:00:00+00:00"},
            "qwen": {"provider": "qwen", "status": "key_missing", "probed_at": "2026-05-13T00:00:00+00:00"},
        }
        return server._probe_svc._CACHE["all_providers"]

    clear_provider_env(monkeypatch)
    monkeypatch.setenv("GENX_API_KEY", "env-genx-key")
    monkeypatch.setattr(server, "db", FakeDB())
    monkeypatch.setattr(server.GenXProvider, "list_models", lambda self: asyncio.sleep(0, result=["model"]))
    monkeypatch.setattr(server._probe_svc, "probe_all_providers", fake_probe_all_providers)
    server._probe_svc._CACHE.clear()

    result = asyncio.run(server.readiness())

    assert calls
    assert calls[0]["force_refresh"] is True
    assert result["providers"]["genx"]["live_status"] == "live_ok"
    server._probe_svc._CACHE.clear()


def test_readiness_mongo_issue_returns_structured_error(monkeypatch):
    import asyncio
    import server

    clear_provider_env(monkeypatch)
    monkeypatch.setattr(server, "db", FakeDB(ping_ok=False))

    result = asyncio.run(server.readiness())

    assert result["overall"] == "FAIL"
    assert any(check["name"] == "Mongo ping" and check["status"] == "FAIL" for check in result["checks"])


def test_cleanup_bad_settings_status_detection():
    from cryptography.fernet import Fernet
    from scripts.cleanup_bad_settings import _status_for

    key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    good = Fernet(key).encrypt(b"secret").decode()
    bad = Fernet(other_key).encrypt(b"secret").decode()
    fernet = Fernet(key)

    assert _status_for({"encrypted_value": good}, fernet) == "ok"
    assert _status_for({"encrypted_value": bad}, fernet) == "decrypt_failed"
    assert _status_for({}, fernet) == "missing_encrypted_value"


def test_cleanup_bad_settings_scan_and_delete_helpers():
    from cryptography.fernet import Fernet
    from scripts.cleanup_bad_settings import _delete_bad, _scan_docs

    class Result:
        deleted_count = 0

    class Collection:
        def __init__(self):
            self.deleted_query = None

        def delete_many(self, query):
            self.deleted_query = query
            result = Result()
            result.deleted_count = len(query["_id"]["$in"])
            return result

    key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    docs = [
        {"_id": "ok", "key": "GENX_API_KEY", "encrypted_value": Fernet(key).encrypt(b"secret").decode()},
        {"_id": "bad", "key": "QWEN_API_KEY", "encrypted_value": Fernet(other_key).encrypt(b"secret").decode()},
        {"_id": "malformed", "key": "PIXABAY_API_KEY"},
    ]

    counter, bad_ids, metadata = _scan_docs(docs, Fernet(key))
    assert counter["ok"] == 1
    assert counter["decrypt_failed"] == 1
    assert counter["missing_encrypted_value"] == 1
    assert bad_ids == ["bad", "malformed"]
    assert all("encrypted_value" not in row for row in metadata)

    collection = Collection()
    assert _delete_bad(collection, bad_ids) == 2
    assert collection.deleted_query == {"_id": {"$in": ["bad", "malformed"]}}
