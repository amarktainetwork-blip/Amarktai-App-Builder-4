from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from config import SECRET_KEYS, effective_fernet_key

logger = logging.getLogger("amarktai.settings")


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


async def safe_get_secret(db, key: str, env_fallback: bool = True) -> dict:
    """Resolve a secret without letting bad encrypted settings crash runtime status.

    Returns a structured result and never exposes encrypted values.
    """
    if key not in SECRET_KEYS:
        raise ValueError(f"Unsupported secret key: {key}")

    env_value = os.environ.get(key) or None
    try:
        doc = await db.settings.find_one({"key": key}, {"_id": 0})
    except Exception as exc:
        if env_fallback and env_value:
            return {
                "value": env_value,
                "source": "env",
                "configured": True,
                "error": "settings_lookup_failed",
            }
        return {
            "value": None,
            "source": "missing",
            "configured": False,
            "error": f"settings_lookup_failed: {type(exc).__name__}",
        }

    if doc and doc.get("encrypted_value"):
        try:
            value = decrypt_value(doc["encrypted_value"])
            if value:
                return {
                    "value": value,
                    "source": "settings",
                    "configured": True,
                    "updated_at": doc.get("updated_at"),
                }
        except Exception:
            logger.warning("Stored setting for %s could not be decrypted; falling back to env", key)
            try:
                await db.settings.update_one(
                    {"key": key},
                    {"$set": {"status": "decrypt_failed", "decrypt_failed_at": _now()}},
                )
            except Exception:
                pass
            if env_fallback and env_value:
                return {
                    "value": env_value,
                    "source": "env",
                    "configured": True,
                    "updated_at": doc.get("updated_at"),
                    "error": "decrypt_failed",
                    "stored_status": "decrypt_failed",
                }
            return {
                "value": None,
                "source": "decrypt_failed",
                "configured": False,
                "updated_at": doc.get("updated_at"),
                "error": "Stored setting cannot be decrypted with the configured key",
                "stored_status": "decrypt_failed",
            }

    if env_fallback and env_value:
        return {"value": env_value, "source": "env", "configured": True}
    return {"value": None, "source": "missing", "configured": False}


async def get_secret(db, key: str) -> str | None:
    return (await safe_get_secret(db, key, env_fallback=True)).get("value") or None


async def settings_status(db, key: str) -> dict:
    resolved = await safe_get_secret(db, key, env_fallback=True)
    value = resolved.get("value")
    return {
        "configured": bool(value),
        "set": bool(value),
        "preview": mask_secret(value),
        "source": resolved.get("source"),
        "status": resolved.get("stored_status") or resolved.get("source"),
        "error": resolved.get("error"),
        "updated_at": resolved.get("updated_at"),
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
