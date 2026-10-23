from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户提问")

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("提问不能为空")
        return value


class AiChatItem(BaseModel):
    id: int
    message: str
    response: str
    created_at: datetime = Field(..., alias="createdAt")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class AiChatHistoryData(BaseModel):
    list: list[AiChatItem]
    total: int
    has_more: bool = Field(..., alias="hasMore")

    model_config = ConfigDict(
        populate_by_name=True,
    )
