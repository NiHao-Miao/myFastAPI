"""Agent 中间件：日志、来源捕获、简报提示词切换。"""
import json
import re
from typing import Callable

from langchain.agents import AgentState
from langchain.agents.middleware import (
    ModelRequest,
    before_model,
    dynamic_prompt,
    wrap_tool_call,
)
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from ...utils.logger_handler import logger
from ...utils.prompt_loader import load_briefing_prompts, load_system_prompts
from .source_marker import SOURCE_MARKER


@wrap_tool_call
async def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    tool_name = request.tool_call["name"]
    logger.info(f"[tool monitor]执行工具：{tool_name}")
    logger.info(f"[tool monitor]传入参数：{request.tool_call['args']}")

    try:
        result = await handler(request)

        if isinstance(result, ToolMessage) and isinstance(result.content, str):
            if SOURCE_MARKER in result.content:
                clean_content, raw_sources = result.content.split(SOURCE_MARKER, 1)
                try:
                    payload = json.loads(raw_sources)
                    new_sources = payload.get("sources", [])
                    context = request.runtime.context
                    existing = context.setdefault("sources", [])
                    index_by_news_id = context.setdefault("source_index_by_news_id", {})
                    next_index = int(context.get("source_counter", 0))
                    local_to_global: dict[int, int] = {}

                    for item in new_sources:
                        news_id = item.get("newsId")
                        local_index = int(item.get("index", 0))
                        if news_id in index_by_news_id:
                            global_index = index_by_news_id[news_id]
                        else:
                            next_index += 1
                            global_index = next_index
                            index_by_news_id[news_id] = global_index
                            item["index"] = global_index
                            existing.append(item)
                        local_to_global[local_index] = global_index

                    context["source_counter"] = next_index

                    # 把工具内部的 [1]/[2] 统一改成全局编号，保证模型最终
                    # 回答里的编号与前端来源卡片一致。
                    def _renumber(match: re.Match) -> str:
                        local_index = int(match.group(1))
                        if local_index in local_to_global:
                            return f"[{local_to_global[local_index]}]"
                        return match.group(0)

                    clean_content = re.sub(r"\[(\d+)\]", _renumber, clean_content)
                except Exception as e:
                    logger.warning(f"[tool monitor]解析来源失败：{str(e)}")

                result = ToolMessage(
                    content=clean_content.strip(),
                    tool_call_id=result.tool_call_id,
                    name=result.name,
                )

        if tool_name == "fill_context_for_briefing":
            request.runtime.context["briefing"] = True

        logger.info(f"[tool monitor]工具{tool_name}调用成功")
        return result
    except Exception as e:
        logger.error(f"工具{tool_name}调用失败，原因：{str(e)}", exc_info=True)
        raise


@before_model
def log_before_model(state: AgentState, runtime: Runtime):
    logger.info(f"[log_before_model]即将调用模型，带有{len(state['messages'])}条消息。")
    last_message = state["messages"][-1]
    content = getattr(last_message, "content", "")
    logger.debug(f"[log_before_model]{type(last_message).__name__} | {str(content)[:300]}")
    return None


@dynamic_prompt
def briefing_prompt_switch(request: ModelRequest):
    if request.runtime.context.get("briefing", False):
        return load_briefing_prompts()
    return load_system_prompts()
