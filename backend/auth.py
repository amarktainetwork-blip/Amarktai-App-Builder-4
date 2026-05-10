"""JWT-based auth for AmarktAI Network — single-admin model with seeded user."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def make_token(user: dict) -> dict:
    secret = os.environ["JWT_SECRET"]
    algo = os.environ.get("JWT_ALGO", "HS256")
    ttl = int(os.environ.get("JWT_TTL_HOURS", "168"))
    exp = datetime.now(timezone.utc) + timedelta(hours=ttl)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user.get("role", "admin"),
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, secret, algorithm=algo)
    return {"token": token, "expires_at": exp.isoformat(),
            "user": {"id": user["id"], "email": user["email"], "role": user.get("role", "admin")}}


def decode_token(token: str) -> dict:
    secret = os.environ["JWT_SECRET"]
    algo = os.environ.get("JWT_ALGO", "HS256")
    try:
        return jwt.decode(token, secret, algorithms=[algo])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # Fallback: WebSocket / EventSource use ?token= query param.
    return request.query_params.get("token")


async def require_user(request: Request) -> dict:
    tok = _extract_token(request)
    if not tok:
        raise HTTPException(401, "Missing bearer token")
    return decode_token(tok)


async def seed_admin(db) -> None:
    """Idempotent: ensure an admin user exists so a fresh deploy can log in."""
    email = (os.environ.get("ADMIN_EMAIL") or "admin@amarktai.local").lower().strip()
    pwd = os.environ.get("ADMIN_PASSWORD") or "amarktai-admin"
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        return
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(pwd),
        "role": "admin",
        "created_at": _now_iso(),
    }
    await db.users.insert_one(dict(user))


CurrentUser = Depends(require_user)
