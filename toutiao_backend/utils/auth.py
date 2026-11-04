"""从请求头解析 JWT，并把 token 中的用户 ID 还原成数据库用户。"""

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_config import get_db
from models.users import User
from utils.jwt import decode_access_token

# auto_error=False：没有 Authorization 头时返回 None，由我们自己抛 401
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization 头中解析 JWT，返回当前用户。

    优先使用 HTTPBearer 解析出的 credentials；如果没有，再兼容旧格式
    `Authorization: <token>`（不带 Bearer 前缀），方便前端分步改造。
    """
    token = credentials.credentials if credentials else None

    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value.strip()
        else:
            token = authorization.strip()

    if not token:
        raise _unauthorized("缺少身份凭证，请先登录")

    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError:
        raise _unauthorized("登录已过期，请重新登录")
    except InvalidTokenError:
        raise _unauthorized("身份凭证无效")

    if payload.get("type") != "access":
        raise _unauthorized("身份凭证类型错误")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("身份凭证内容无效")

    user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized("用户不存在或已被删除")

    return user