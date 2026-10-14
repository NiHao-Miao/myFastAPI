
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import News
from models.history import History

async def check_history(db: AsyncSession, user_id: int, news_id: int):
    stmt = select(History).where(History.user_id == user_id, History.news_id == news_id)
    result = await db.execute(stmt)
    existed =  result.scalar_one_or_none()
    if existed:
        existed.view_time = datetime.now()
        await db.commit()
        await db.refresh(existed)
        return existed


async def add_history(db: AsyncSession, user_id: int, news_id: int):
    add_his = History(user_id=user_id, news_id=news_id)
    db.add(add_his)
    await db.commit()
    await db.refresh(add_his)
    return add_his

async def get_history_list(db: AsyncSession, user_id: int, page: int, pagesize: int):
    stmt = select(func.count(History.id)).where(History.user_id == user_id)
    total = await db.execute(stmt)
    total = total.scalar()

    offset = (page - 1) * pagesize
    stmt = (
        select(History.news_id, News.title, News.image, News.author,
               News.category_id, News.views, News.publish_time, History.view_time)
        .join(News, News.id == History.news_id)
        .where(History.user_id == user_id)
        .order_by(History.view_time.desc())
        .offset(offset)
        .limit(pagesize)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return rows, total

async def delete_history(db: AsyncSession, user_id: int, news_id: int):
    stmt = delete(History).where(History.user_id == user_id, History.news_id == news_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

async def clear_history(db: AsyncSession, user_id: int):
    stmt = delete(History).where(History.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
