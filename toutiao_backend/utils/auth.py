from fastapi import Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from config.db_config import get_db
from crud import users

async def get_current_user(
        authorization: str = Header(..., alias="Authorization"),
        db: AsyncSession = Depends(get_db)
):
    token = authorization.replace("Bearer ", "")
    user = await users.get_user_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
