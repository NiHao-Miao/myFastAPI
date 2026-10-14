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
    token: str
    user_info: UserInfoResponse = Field(..., alias="userInfo")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )

class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., alias="oldPassword", description="旧密码")
    new_password: str = Field(..., max_length=6, alias="newPassword", description="新密码")