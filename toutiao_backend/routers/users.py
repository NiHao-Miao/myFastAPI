from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from models.users import User
from utils.auth import get_current_user
from utils.response import success_response
from schemas.users import UserAuthResponse, UserChangePasswordRequest, UserInfoBase, UserInfoResponse, UserRequest
from crud import users
from config.db_config import get_db

router = APIRouter(prefix="/api/user", tags=["users"])

@router.post("/register")
async def registers(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    # 注册逻辑：验证用户是否存在 ——》 创建用户 ——》 生成token ——》 响应结果
    # 检查用户是否已存在
    existing_user = await users.get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    user = await users.create_users(db,user_data)
    token = await users.create_user_token(db, user.id)
    response_data = UserAuthResponse(token=token, user_info=UserInfoResponse.model_validate(user))
    return success_response(message="User registered successfully", data=response_data)

@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await users.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = await users.create_user_token(db, user.id)
    response_data = UserAuthResponse(token=token, user_info=UserInfoResponse.model_validate(user))
    return success_response(message="User logged in successfully", data=response_data)

@router.get("/info")
async def get_user_info(user: User = Depends(get_current_user)):
    return success_response(message="User registered successfully", data=UserInfoResponse.model_validate(user))

@router.put("/update")
async def update_user_info(user_data: UserInfoBase, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    update = await users.update_user_info(db, user.username, user_data)
    return success_response(message="User updated successfully", data=UserInfoResponse.model_validate(update))

@router.put("/password")
async def change_password(password_data: UserChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    change_pwd = await users.change_password(db, user, password_data.old_password, password_data.new_password)
    if not change_pwd:
        raise HTTPException(status_code=400, detail="Invalid old password")
    return success_response(message="Password updated successfully")

