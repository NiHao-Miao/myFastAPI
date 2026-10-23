from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_chat import AiChat


async def create_chat(
    db: AsyncSession,
    user_id: int,
    message: str,
    response: str,
) -> AiChat:
    chat = AiChat(user_id=user_id, message=message, response=response)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


async def get_chat_list(
    db: AsyncSession,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
) -> list[AiChat]:
    stmt = (
        select(AiChat)
        .where(AiChat.user_id == user_id)
        .order_by(AiChat.created_at.desc(), AiChat.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_chats(db: AsyncSession, user_id: int) -> int:
    stmt = select(func.count(AiChat.id)).where(AiChat.user_id == user_id)
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def clear_chats(db: AsyncSession, user_id: int) -> int:
    stmt = sql_delete(AiChat).where(AiChat.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    return int(result.rowcount or 0)
