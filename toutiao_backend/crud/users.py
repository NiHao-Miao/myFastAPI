"""用户数据访问层：账号查询/创建、刷新令牌签发与撤销、密码修改。"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.users import UserInfoBase, UserRequest
from models.users import User, UserToken
from utils import security
from utils.jwt import create_refresh_token, hash_refresh_token
#根据用户名查询数据库
async def get_user_by_username(db: AsyncSession, username: str):
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    return result.scalar_one_or_none()
#创建用户
async def create_users(db: AsyncSession, user_data: UserRequest):
    hashed_psw = security.hash_password(user_data.password)
    user = User(username=user_data.username, password=hashed_psw)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

#生成token
async def issue_refresh_token(db: AsyncSession, user_id: int) -> str:
    """为用户签发刷新令牌，返回明文；数据库只存哈希。

    单会话策略：登录时删掉该用户旧的刷新令牌，旧设备需要重新登录。
    如果以后要多设备同时在线，把 DELETE 去掉，改为每次 INSERT 即可。
    """
    raw_token, expires_at = create_refresh_token()
    token_hash = hash_refresh_token(raw_token)

    await db.execute(delete(UserToken).where(UserToken.user_id == user_id))
    db.add(
        UserToken(
            user_id=user_id,
            token=token_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return raw_token


async def get_user_by_refresh_token(db: AsyncSession, raw_token: str) -> User | None:
    """用明文刷新令牌换用户；无效或过期返回 None。"""
    token_hash = hash_refresh_token(raw_token)
    query = select(UserToken).where(UserToken.token == token_hash)
    result = await db.execute(query)
    row = result.scalar_one_or_none()

    if row is None:
        return None

    if row.expires_at <= datetime.now():
        # 过期行顺手清理，避免表里堆积垃圾
        await db.delete(row)
        await db.commit()
        return None

    return await db.get(User, row.user_id)


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> bool:
    """删除指定的刷新令牌（登出）。返回是否真的删到了。"""
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(delete(UserToken).where(UserToken.token == token_hash))
    await db.commit()
    return (result.rowcount or 0) > 0


async def revoke_all_refresh_tokens(db: AsyncSession, user_id: int) -> None:
    """撤销该用户所有刷新令牌（改密、强制下线）。"""
    await db.execute(delete(UserToken).where(UserToken.user_id == user_id))
    await db.commit()


async def authenticate_user(db: AsyncSession, username: str, password: str):
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not security.verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

async def update_user_info(db: AsyncSession, username: str, user_data: UserInfoBase):
    query = update(User).where(User.username == username).values(**user_data.model_dump(exclude_unset=True, exclude_none=True))
    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")

    updated_user = await get_user_by_username(db, username)
    return updated_user

async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str):
    if not security.verify_password(old_password, user.password):
        return False

    hashed_new_pwd = security.hash_password(new_password)
    user.password = hashed_new_pwd
    db.add(user)
    await db.execute(delete(UserToken).where(UserToken.user_id == user.id))
    await db.commit()
    await db.refresh(user)
    return True


    