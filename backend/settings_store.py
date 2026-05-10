from __future__ import annotations

import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from config import SECRET_KEYS, effective_fernet_key


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    key = effective_fernet_key()
    if not key:
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode("utf-8"))


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def encrypt_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored setting cannot be decrypted with the configured key") from exc


async def get_secret(db, key: str) -> str | None:
    if key not in SECRET_KEYS:
        raise ValueError(f"Unsupported secret key: {key}")
    doc = await db.settings.find_one({"key": key}, {"_id": 0})
    if doc and doc.get("encrypted_value"):
        value = decrypt_value(doc["encrypted_value"])
        if value:
            return value
    return os.environ.get(key) or None


async def settings_status(db, key: str) -> dict:
    value = await get_secret(db, key)
    stored = await db.settings.find_one({"key": key}, {"_id": 0, "updated_at": 1})
    source = "settings" if stored else ("env" if os.environ.get(key) else None)
    return {
        "configured": bool(value),
        "set": bool(value),
        "preview": mask_secret(value),
        "source": source,
        "updated_at": stored.get("updated_at") if stored else None,
    }


async def save_secret(db, key: str, value: str, user_id: str | None = None) -> None:
    if key not in SECRET_KEYS:
        raise ValueError(f"Unsupported secret key: {key}")
    now = _now()
    await db.settings.update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "encrypted_value": encrypt_value(value),
                "updated_at": now,
                "updated_by": user_id,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def clear_secret(db, key: str) -> None:
    if key not in SECRET_KEYS:
        raise ValueError(f"Unsupported secret key: {key}")
    await db.settings.delete_one({"key": key})
