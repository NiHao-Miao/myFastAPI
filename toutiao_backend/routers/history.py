from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from utils.response import success_response
from schemas.history import HistoryAddRequest, HistoryListResponse
from config.db_config import get_db
from models.users import User
from utils.auth import get_current_user
from crud import history

router = APIRouter(prefix="/api/history", tags=["History"])

@router.get("/")
async def root():
    return {"message": "History API"}

@router.post("/add")
async def add_history(
    data: HistoryAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):  
    if await history.check_history(db, user.id, data.news_id):
        return success_response(message="History already exists", data=None)
    result = await history.add_history(db, user.id, data.news_id)
    return success_response(message="History added successfully", data={"historyId": result.id})

@router.get("/list")
async def get_history_list(
    page: int = Query(1, ge=1),
    pagesize: int = Query(10, ge=1, le=100, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Implementation for fetching history list
    rows, total = await history.get_history_list(db, user.id, page, pagesize)
    history_list = [{
        "id": news_id,          # 前端用 item.id 跳详情/删除 → 新闻ID
        "title": title,
        "image": image,
        "author": author,
        "category_id": category_id,
        "views": views,
        "publish_time": publish_time,   # schema alias publishTime
        "view_time": view_time,         # schema alias viewTime
    } for news_id, title, image, author, category_id, views, publish_time, view_time in rows]
    has_more = total > page * pagesize
    data = HistoryListResponse(list=history_list, total=total, has_more=has_more)

    return success_response(message="History list fetched successfully", data=data)

# routers/history.py：把 /remove 整段替换为
@router.delete("/delete/{news_id}")
async def delete_history(
    news_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ok = await history.delete_history(db, user.id, news_id)
    if not ok:
        raise HTTPException(status_code=404, detail="History not found")
    return success_response(message="History deleted successfully")
@router.delete("/clear")
async def clear_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await history.clear_history(db, user.id)
    return success_response(message=f"History list {result} cleared successfully")