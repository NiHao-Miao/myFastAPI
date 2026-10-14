from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from schemas.base import NewsItemBase

class FavoriteCheckResponse(BaseModel):
    is_favorite: bool = Field(..., alias="isFavorite")

class FavoriteAddRequest(BaseModel):
    news_id: int = Field(..., alias="newsId")

class FavoriteNewsItemResponse(NewsItemBase):
    favorite_time: datetime = Field(..., alias="favoriteTime")
    favorite_id: int = Field(..., alias="favoriteId")

class FavoriteListResponse(BaseModel):
    list: list[FavoriteNewsItemResponse]
    total:int
    has_more:bool = Field(alias="hasMore")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )