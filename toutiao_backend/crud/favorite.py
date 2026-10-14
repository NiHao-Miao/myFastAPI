from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import News
from models.favorite import Favorite
async def check_favorite(db: AsyncSession, user_id: int, news_id: int):
    stmt = select(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None

async def add_favorite(db: AsyncSession, user_id: int, news_id: int):

    result = Favorite(user_id=user_id, news_id=news_id)
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result

async def delete_favorite(db: AsyncSession, user_id: int, news_id: int):
    stmt = delete(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

async def get_favorite_list(db: AsyncSession, user_id: int, page: int, pagesize: int):
    count_stmt = select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
    total = await db.execute(count_stmt)
    total = total.scalar()

    offset = (page - 1) * pagesize
    stmt = select(News, Favorite.created_at.label("favorite_time"), Favorite.id.label("favorite_id")).join(Favorite, Favorite.news_id == News.id).where(Favorite.user_id == user_id).order_by(News.created_at.desc()).offset(offset).limit(pagesize)
    result = await db.execute(stmt)
    rows = result.all()
    return rows, total

async def clear_favorite_list(db: AsyncSession, user_id: int):
    stmt = delete(Favorite).where(Favorite.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0