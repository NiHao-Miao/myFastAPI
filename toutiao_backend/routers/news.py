from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from config.db_config import get_db
from crud import news, news_cache
#创建路由APIRouter实例
#prefix路由前缀
#tag 分组标签
router = APIRouter(prefix="/api/news", tags=["news"])

#接口实现流程
#1.模块化路由  api接口规范文档
#2.定义模块类  数据库表
#3.在crud文件里面创建文件,封装操作数据库的方法
#4.在路由处理函数里面调用crud封装好的方法,响应结果

@router.get("/categories")
async def get_categories(skip:int = 0, limit:int = 100, db: AsyncSession = Depends(get_db)):
    categories = await news_cache.get_categories(db, skip, limit)
    return {
        "code": 200,
        "message": "success",
        "data": categories
    }

@router.get("/list")
async def get_news_list(
    category_id: int = Query(..., alias="categoryId"),
    page: int = 1,
    page_size: int = Query(10, le=100, alias="pageSize"),
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    #思路:处理分页规则  查询新闻列表  计算总量  计算是否还有更多
    news_list = await news_cache.get_news_list(db, category_id, offset, page_size)
    total = await news.get_news_count(db, category_id)
    has_more = (offset + len(news_list) < total)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "list": news_list,
            "total": total,
            "hasMore": has_more
        }
    }

@router.get("/detail")
async def get_news_detail(
    news_id: int = Query(..., alias="id"),
    db: AsyncSession = Depends(get_db)
):
    news_detail = await news.get_news_detail(db, news_id)
    if not news_detail:
        raise HTTPException(status_code=404, detail="News not found")
    views_res = await news.increase_news_views(db, news_detail.id)
    if not views_res:
        raise HTTPException(status_code=500, detail="Failed to update news views")\

    related_news = await news.get_related_news(db, news_detail.id, news_detail.category_id)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": news_detail.id,
            "title": news_detail.title,
            "content": news_detail.content,
            "image": news_detail.image,
            "author": news_detail.author,
            "publishTime": news_detail.publish_time,
            "category_id": news_detail.category_id,
            "views": news_detail.views,
            "relatedNews": related_news
        }
    }