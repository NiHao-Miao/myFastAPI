"""JWT 访问令牌的生成/解析，以及刷新令牌的生成/哈希。"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from config.jwt_conf import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET_KEY,
)


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    """生成访问令牌，返回 (token, 有效期秒数)。"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),          # JWT 规范要求 sub 是字符串
        "username": username,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60


def create_refresh_token() -> tuple[str, datetime]:
    """生成刷新令牌，返回 (明文, 过期时间)。

    明文只返回给客户端；数据库只保存它的 SHA-256 哈希。
    过期时间用本地 naive datetime，和 MySQL DATETIME 的比较方式保持一致。
    """
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return token, expires_at


def hash_refresh_token(token: str) -> str:
    """刷新令牌是高熵随机串，用 SHA-256 足够，不需要 bcrypt。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict[str, Any]:
    """解析并校验访问令牌；失败时抛 PyJWT 的异常。"""
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],   # 固定算法，防止 alg 混淆攻击
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "iss", "sub", "type"]},
        leeway=10,                    # 容忍 10 秒时钟偏差
    )