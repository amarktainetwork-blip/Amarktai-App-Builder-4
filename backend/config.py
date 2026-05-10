from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet


APP_NAME = "Amarktai App Builder"
ASSISTANT_NAME = "Amarktai Wingman"
AGENTS_NAME = "Amarktai Coding Agents"
ROUTER_NAME = "GenX Router"

DEV_FERNET_KEY = "YW1hcmt0YWktZGV2LWZlcm5ldC1rZXktMzItYnl0ZSE="
REQUIRED_ENV = [
    "APP_ENV",
    "GENX_API_KEY",
    "JWT_SECRET",
    "ADMIN_EMAIL",
    "ADMIN_PASSWORD",
    "SETTINGS_ENCRYPTION_KEY",
    "MONGO_URL",
    "DB_NAME",
    "CORS_ORIGINS",
]
SECRET_KEYS = {"GENX_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY"}


def app_env() -> str:
    return (os.environ.get("APP_ENV") or "development").lower().strip()


def is_production() -> bool:
    return app_env() == "production"


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def cors_origins() -> list[str]:
    raw = get_env("CORS_ORIGINS", "http://localhost:8080,http://localhost:3000") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def valid_fernet_key(value: str | None) -> bool:
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
        Fernet(value.encode("utf-8"))
        return len(decoded) == 32
    except Exception:
        return False


def effective_fernet_key() -> str | None:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if key:
        return key
    if not is_production():
        return DEV_FERNET_KEY
    return None


@dataclass
class ConfigCheck:
    name: str
    status: str
    detail: str
    severity: str = "info"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "severity": self.severity,
        }


def validate_static_config() -> list[ConfigCheck]:
    checks: list[ConfigCheck] = []
    env = app_env()
    checks.append(ConfigCheck("APP_ENV", "PASS", env))

    if is_production():
        missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
        checks.append(ConfigCheck(
            "required production env",
            "FAIL" if missing else "PASS",
            f"Missing: {', '.join(missing)}" if missing else "All required production variables are present.",
            "blocker" if missing else "info",
        ))
    else:
        checks.append(ConfigCheck(
            "development defaults",
            "WARN",
            "Development mode permits local defaults. Production must provide explicit secrets.",
            "warning",
        ))

    jwt_secret = os.environ.get("JWT_SECRET") or ""
    jwt_ok = len(jwt_secret) >= 32
    checks.append(ConfigCheck(
        "JWT_SECRET strength",
        "PASS" if jwt_ok else ("FAIL" if is_production() else "WARN"),
        "At least 32 characters." if jwt_ok else "Set JWT_SECRET to a random value of at least 32 characters.",
        "blocker" if is_production() and not jwt_ok else "warning",
    ))

    admin_email = os.environ.get("ADMIN_EMAIL") or ""
    admin_password = os.environ.get("ADMIN_PASSWORD") or ""
    admin_ok = bool(admin_email) and len(admin_password) >= 12
    checks.append(ConfigCheck(
        "admin credentials",
        "PASS" if admin_ok else ("FAIL" if is_production() else "WARN"),
        "Configured." if admin_ok else "Set ADMIN_EMAIL and an ADMIN_PASSWORD of at least 12 characters.",
        "blocker" if is_production() and not admin_ok else "warning",
    ))

    key = effective_fernet_key()
    enc_ok = valid_fernet_key(key)
    checks.append(ConfigCheck(
        "SETTINGS_ENCRYPTION_KEY",
        "PASS" if enc_ok else ("FAIL" if is_production() else "WARN"),
        "Valid encryption key." if enc_ok else "Set a Fernet-compatible SETTINGS_ENCRYPTION_KEY.",
        "blocker" if is_production() and not enc_ok else "warning",
    ))

    origins = cors_origins()
    cors_ok = "*" not in origins and bool(origins)
    checks.append(ConfigCheck(
        "CORS_ORIGINS",
        "PASS" if cors_ok else ("FAIL" if is_production() else "WARN"),
        ", ".join(origins) if origins else "No origins configured.",
        "blocker" if is_production() and not cors_ok else "warning",
    ))
    return checks


def assert_startup_config() -> None:
    failures = [c for c in validate_static_config() if c.status == "FAIL" and c.severity == "blocker"]
    if failures:
        details = "; ".join(f"{c.name}: {c.detail}" for c in failures)
        raise RuntimeError(f"Production configuration is not safe: {details}")
