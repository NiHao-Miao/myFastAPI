"""单次 AI 问答编排：Agent 流式事件 → SSE → 保存 ai_chat。"""
import json

from config.db_config import AsyncSessionLocal
from crud.ai_chat import create_chat

from .agent.react_agent import ReactAgent
from .utils.logger_handler import logger

_agent: ReactAgent | None = None


def get_agent() -> ReactAgent:
    global _agent
    if _agent is None:
        _agent = ReactAgent()
    return _agent


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat(user_id: int, message: str):
    """yield SSE 字符串；完成后写入 ai_chat。"""
    yield sse("status", {"stage": "thinking", "message": "正在检索新闻库..."})

    answer_parts: list[str] = []
    sources: list[dict] = []

    try:
        agent = get_agent()
        async for event in agent.astream_events(message):
            event_type = event.get("type")
            if event_type == "reset":
                # 与前端保持一致：草稿被清空，历史里也不应保存草稿
                answer_parts.clear()
                yield sse("reset", {})
            elif event_type == "delta":
                content = event.get("content", "")
                if content:
                    answer_parts.append(content)
                    yield sse("delta", {"content": content})
            elif event_type == "sources":
                sources = event.get("sources", [])
                if sources:
                    yield sse("sources", {"sources": sources})
    except Exception as e:
        logger.error(f"[ai.service]流式回答失败：{str(e)}", exc_info=True)
        yield sse("error", {"message": "AI 服务暂时不可用，请稍后重试。"})
        return

    answer = "".join(answer_parts).strip()
    if not answer:
        answer = "抱歉，我暂时无法回答这个问题，请换一种问法或稍后重试。"
        yield sse("delta", {"content": answer})

    chat_id = None
    try:
        async with AsyncSessionLocal() as db:
            chat = await create_chat(db, user_id, message, answer)
            chat_id = chat.id
    except Exception as e:
        logger.error(f"[ai.service]保存聊天记录失败：{str(e)}", exc_info=True)

    yield sse("done", {"chatId": chat_id, "saved": chat_id is not None})
