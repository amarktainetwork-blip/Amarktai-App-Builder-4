"""JWT auth and admin user management helpers for Amarktai App Builder."""
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


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "status": user.get("status", "active"),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def make_token(user: dict) -> dict:
    if user.get("status", "active") != "active":
        raise HTTPException(403, "User is disabled")
    secret = os.environ["JWT_SECRET"]
    algo = os.environ.get("JWT_ALGO", "HS256")
    ttl = int(os.environ.get("JWT_TTL_HOURS", "168"))
    exp = datetime.now(timezone.utc) + timedelta(hours=ttl)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, secret, algorithm=algo)
    return {"token": token, "expires_at": exp.isoformat(), "user": public_user(user)}


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
    return request.query_params.get("token")


async def require_user(request: Request) -> dict:
    tok = _extract_token(request)
    if not tok:
        raise HTTPException(401, "Missing bearer token")
    claims = decode_token(tok)
    db = request.app.state.db
    user = await db.users.find_one({"id": claims["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User no longer exists")
    if user.get("status", "active") != "active":
        raise HTTPException(403, "User is disabled")
    claims["role"] = user.get("role", claims.get("role", "user"))
    claims["email"] = user.get("email", claims.get("email"))
    return claims


async def require_admin(claims: dict = Depends(require_user)) -> dict:
    if claims.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return claims


async def seed_admin(db) -> None:
    email = (os.environ.get("ADMIN_EMAIL") or "admin@amarktai.local").lower().strip()
    pwd = os.environ.get("ADMIN_PASSWORD") or "amarktai-admin-local"
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    now = _now_iso()
    if existing:
        updates = {}
        if existing.get("role") != "admin":
            updates["role"] = "admin"
        if existing.get("status") != "active":
            updates["status"] = "active"
        if updates:
            updates["updated_at"] = now
            await db.users.update_one({"id": existing["id"]}, {"$set": updates})
        return
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(pwd),
        "role": "admin",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(dict(user))


CurrentUser = Depends(require_user)
