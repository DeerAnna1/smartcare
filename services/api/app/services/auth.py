"""认证与密码处理服务"""
import base64
import hashlib
import hmac
import json
import os
import time
from fastapi import HTTPException
from app.core.config import get_settings

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
JWT_ALG = "HS256"


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{_urlsafe_b64encode(salt)}${_urlsafe_b64encode(derived)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_b64, digest_b64 = stored_hash.split("$", 1)
        salt = _urlsafe_b64decode(salt_b64)
        expected = _urlsafe_b64decode(digest_b64)
    except ValueError:
        return False

    current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(current, expected)


def create_access_token(user_id: str, username: str) -> str:
    header = {"alg": JWT_ALG, "typ": "JWT"}
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    header_b64 = _urlsafe_b64encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    message = f"{header_b64}.{payload_b64}"
    secret = get_settings().AUTH_SECRET.encode("utf-8")
    signature = _urlsafe_b64encode(
        hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()
    )
    return f"{message}.{signature}"


def decode_access_token(token: str) -> dict:
    try:
        header_b64, payload_b64, signature = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="登录状态无效") from exc

    try:
        header = json.loads(_urlsafe_b64decode(header_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="登录状态无效") from exc
    if header.get("alg") != JWT_ALG:
        raise HTTPException(status_code=401, detail="登录状态无效")

    secret = get_settings().AUTH_SECRET.encode("utf-8")
    expected_signature = _urlsafe_b64encode(
        hmac.new(secret, f"{header_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="登录状态无效")

    try:
        payload = json.loads(_urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="登录状态无效") from exc

    if int(payload.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=401, detail="登录状态已过期")

    return payload
