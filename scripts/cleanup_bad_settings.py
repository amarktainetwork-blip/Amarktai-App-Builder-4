#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from pymongo import MongoClient


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY", "")
    if not key:
        raise SystemExit("SETTINGS_ENCRYPTION_KEY is required to scan encrypted settings.")
    try:
        decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
        if len(decoded) != 32:
            raise ValueError("decoded key length is not 32 bytes")
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"SETTINGS_ENCRYPTION_KEY is not a valid Fernet key: {type(exc).__name__}") from exc


def _status_for(doc: dict, fernet: Fernet) -> str:
    encrypted = doc.get("encrypted_value")
    if not encrypted:
        return "missing_encrypted_value"
    try:
        value = fernet.decrypt(str(encrypted).encode("utf-8")).decode("utf-8")
        return "ok" if value else "empty_plaintext"
    except InvalidToken:
        return "decrypt_failed"
    except Exception:
        return "decrypt_error"


def _scan_docs(docs: list[dict], fernet: Fernet) -> tuple[Counter[str], list, list[dict]]:
    counter: Counter[str] = Counter()
    bad_ids = []
    metadata = []
    for doc in docs:
        status = _status_for(doc, fernet)
        counter[status] += 1
        metadata.append({
            "key": doc.get("key", "<missing>"),
            "status": status,
            "stored_status": doc.get("status"),
            "updated_at": doc.get("updated_at"),
        })
        if status in {"decrypt_failed", "decrypt_error", "missing_encrypted_value"}:
            bad_ids.append(doc["_id"])
    return counter, bad_ids, metadata


def _delete_bad(collection, bad_ids: list) -> int:
    if not bad_ids:
        return 0
    result = collection.delete_many({"_id": {"$in": bad_ids}})
    return int(result.deleted_count)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan or delete undecryptable Amarktai encrypted settings.")
    parser.add_argument("--dry-run", action="store_true", help="Scan only. This is the default unless --delete-bad is provided.")
    parser.add_argument("--delete-bad", action="store_true", help="Delete settings that cannot be decrypted with the current key.")
    parser.add_argument("--collection", default="settings", help="Settings collection name. Default: settings")
    parser.add_argument("--backup-metadata", default="", help="Optional JSON path for masked metadata before deletion.")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "amarktai_builder")
    fernet = _fernet()
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    collection = client[db_name][args.collection]

    docs = list(collection.find({}, {"key": 1, "encrypted_value": 1, "updated_at": 1, "status": 1}))
    counter, bad_ids, metadata = _scan_docs(docs, fernet)

    print(json.dumps({
        "database": db_name,
        "collection": args.collection,
        "total": len(docs),
        "counts": dict(counter),
        "bad_count": len(bad_ids),
        "mode": "delete-bad" if args.delete_bad else "dry-run",
        "scanned_at": _now(),
    }, indent=2, default=str))

    if args.backup_metadata:
        backup_path = Path(args.backup_metadata)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps({"items": metadata, "exported_at": _now()}, indent=2, default=str), encoding="utf-8")
        print(f"masked metadata backup written: {backup_path}")

    if args.delete_bad:
        print(json.dumps({"deleted_count": _delete_bad(collection, bad_ids)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
