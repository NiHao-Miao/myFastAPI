from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from schemas.base import NewsItemBase
class HistoryAddRequest(BaseModel):
    news_id: int = Field(..., alias="newsId")

class HistoryNewsItemResponse(NewsItemBase):
    view_time: datetime = Field(..., alias="viewTime")

class HistoryListResponse(BaseModel):
    list: list[HistoryNewsItemResponse]
    total:int
    has_more:bool = Field(alias="hasMore")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )