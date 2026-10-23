from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai.service import stream_chat
from ai.utils.env import get_api_key
from config.db_config import get_db
from crud import ai_chat
from models.users import User
from schemas.ai_chat import AiChatItem, AiChatRequest
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat")
async def chat(
    payload: AiChatRequest,
    user: User = Depends(get_current_user),
):
    try:
        get_api_key()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return StreamingResponse(
        stream_chat(user.id, payload.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/history")
async def chat_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    items = await ai_chat.get_chat_list(db, user.id, offset, page_size)
    total = await ai_chat.count_chats(db, user.id)
    data = {
        "list": [
            AiChatItem.model_validate(item).model_dump(mode="json", by_alias=True)
            for item in items
        ],
        "total": total,
        "hasMore": offset + len(items) < total,
    }
    return success_response(data=data)


@router.delete("/chat/history")
async def clear_chat_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await ai_chat.clear_chats(db, user.id)
    return success_response(message="清空成功", data={"deleted": deleted})
