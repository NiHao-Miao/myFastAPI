from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class UserRequest(BaseModel):
    username: str
    password: str

class UserInfoBase(BaseModel):

    nickname: Optional[str] = Field(None, max_length=100, description="用户昵称")
    avatar: Optional[str] = Field(None, max_length=200, description="用户头像")
    gender: Optional[str] = Field(None, max_length=10, description="用户性别")
    bio: Optional[str] = Field(None, max_length=200, description="用户简介")

class UserInfoResponse(UserInfoBase):
    id: int
    username: str

    model_config = ConfigDict(
            from_attributes=True
        )


class UserAuthResponse(BaseModel):
    """登录/注册成功后的响应。"""

    access_token: str = Field(..., alias="accessToken", description="访问令牌（JWT）")
    refresh_token: str = Field(..., alias="refreshToken", description="刷新令牌，仅返回一次")
    token_type: str = Field("bearer", alias="tokenType", description="令牌类型")
    expires_in: int = Field(..., alias="expiresIn", description="访问令牌有效期（秒）")
    user_info: UserInfoResponse = Field(..., alias="userInfo")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class RefreshTokenRequest(BaseModel):
    """刷新/登出接口的请求体。"""

    refresh_token: str = Field(..., min_length=10, alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class TokenRefreshResponse(BaseModel):
    """刷新成功后的响应。"""

    access_token: str = Field(..., alias="accessToken")
    token_type: str = Field("bearer", alias="tokenType")
    expires_in: int = Field(..., alias="expiresIn")

    model_config = ConfigDict(populate_by_name=True)


class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., alias="oldPassword", description="旧密码")
    # 顺手修复：原来 max_length=6 会把 7 位以上的新密码全部判为非法
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=72,
        alias="newPassword",
        description="新密码",
    )