from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.favorite import FavoriteAddRequest, FavoriteCheckResponse, FavoriteListResponse
from crud import favorite
from config.db_config import get_db
from models.users import User
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/favorite", tags=["favorite"])

@router.get("/")
async def root():
    return {"message": "Welcome to the favorite API"}

@router.get("/check")
async def check_favorite(
    news_id: int = Query(..., alias="newsId"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    is_favorite = await favorite.check_favorite(db, user.id, news_id)
    return success_response(message="Favorite checked successfully", data=FavoriteCheckResponse(isFavorite=is_favorite))

@router.post("/add")
async def add_favorite(data: FavoriteAddRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Implementation for adding a favorite
    result = await favorite.add_favorite(db, user.id, data.news_id)
    return success_response(message="Favorite added successfully", data=result)

@router.delete("/remove")
async def remove_favorite(
    news_id: int = Query(..., alias="newsId"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await favorite.delete_favorite(db, user.id, news_id)
    if not result:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return success_response(message="Favorite removed successfully")

@router.get("/list")
async def get_favorite_list(
    page: int = Query(1, ge = 1),
    pagesize: int = Query(10, ge = 1, le = 100, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    rows, total = await favorite.get_favorite_list(db, user.id, page, pagesize)
    favorite_list = [{
        **news.__dict__,
        "favorite_time": favorite_time,
        "favorite_id": favorite_id
    } for news, favorite_time, favorite_id in rows]
    has_more = total > page * pagesize
    data = FavoriteListResponse(list=favorite_list, total=total, hasMore=has_more)
    return success_response(message="Favorite list retrieved successfully", data=data)

@router.delete("/clear")
async def clear_favorite(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await favorite.clear_favorite_list(db, user.id)
    return success_response(message=f"Favorite list {result} cleared successfully")