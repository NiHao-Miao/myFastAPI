"""用户认证接口。

令牌分工：
- accessToken：JWT，短期有效，放在 Authorization: Bearer <token> 中访问业务接口；
- refreshToken：随机字符串，长期有效，数据库只存 SHA-256 哈希，用于换取新的 accessToken。

登录/注册会同时返回两个令牌；刷新和登出只需要 refreshToken。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_config import get_db
from crud import users
from models.users import User
from schemas.users import (
    RefreshTokenRequest,
    TokenRefreshResponse,
    UserAuthResponse,
    UserChangePasswordRequest,
    UserInfoBase,
    UserInfoResponse,
    UserRequest,
)
from utils.auth import get_current_user
from utils.jwt import create_access_token
from utils.response import success_response

router = APIRouter(prefix="/api/user", tags=["users"])


def build_auth_response(user: User, refresh_token: str) -> UserAuthResponse:
    """把 User + 刷新令牌组装成登录响应。"""
    access_token, expires_in = create_access_token(user.id, user.username)
    return UserAuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_info=UserInfoResponse.model_validate(user),
    )


@router.post("/register")
async def registers(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    # 注册逻辑：验证用户是否存在 ——》 创建用户 ——》 生成token ——》 响应结果
    # 检查用户是否已存在
    existing_user = await users.get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    user = await users.create_users(db,user_data)
    refresh_token = await users.issue_refresh_token(db, user.id)
    response_data = build_auth_response(user, refresh_token)
    return success_response(message="User registered successfully", data=response_data)


@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await users.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 单会话策略：issue_refresh_token 会先删除该用户旧记录，再写入新哈希
    refresh_token = await users.issue_refresh_token(db, user.id)
    response_data = build_auth_response(user, refresh_token)
    return success_response(message="User logged in successfully", data=response_data)


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """用刷新令牌换新的访问令牌。"""
    user = await users.get_user_by_refresh_token(db, payload.refresh_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    access_token, expires_in = create_access_token(user.id, user.username)
    data = TokenRefreshResponse(access_token=access_token, expires_in=expires_in)
    return success_response(message="Token refreshed", data=data)


@router.post("/logout")
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """登出：删除服务端刷新令牌。访问令牌会在到期后自然失效。"""
    await users.revoke_refresh_token(db, payload.refresh_token)
    return success_response(message="Logged out successfully")


@router.get("/info")
async def get_user_info(user: User = Depends(get_current_user)):
    return success_response(message="User info fetched successfully", data=UserInfoResponse.model_validate(user))


@router.put("/update")
async def update_user_info(user_data: UserInfoBase, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    update = await users.update_user_info(db, user.username, user_data)
    return success_response(message="User updated successfully", data=UserInfoResponse.model_validate(update))


@router.put("/password")
async def change_password(password_data: UserChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # change_password 内部会撤销该用户的全部 refreshToken，强制其他会话重新登录
    change_pwd = await users.change_password(db, user, password_data.old_password, password_data.new_password)
    if not change_pwd:
        raise HTTPException(status_code=400, detail="Invalid old password")
    return success_response(message="Password updated successfully")

