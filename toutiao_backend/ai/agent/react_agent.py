"""新闻 ReAct Agent：保留 AgentRAG 的 create_agent + tools + middleware 结构。"""
import asyncio
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessageChunk

from ..model.factory import get_chat_model
from ..utils.prompt_loader import load_system_prompts
from .tools.middleware import briefing_prompt_switch, log_before_model, monitor_tool
from .tools.news_tools import (
    fill_context_for_briefing,
    get_current_date,
    get_latest_news,
    get_news_detail,
    list_news_categories,
    rag_summarize,
    search_news,
)


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=get_chat_model(),
            system_prompt=load_system_prompts(),
            tools=[
                rag_summarize,
                search_news,
                get_latest_news,
                get_news_detail,
                list_news_categories,
                get_current_date,
                fill_context_for_briefing,
            ],
            middleware=[monitor_tool, log_before_model, briefing_prompt_switch],
        )

    async def astream_events(self, query: str):
        """流式输出：delta 为回答增量，sources 为本次引用新闻。"""
        context = {"briefing": False, "sources": []}
        input_dict = {"messages": [{"role": "user", "content": query}]}
        in_tool_call_stream = False

        async for chunk, _metadata in self.agent.astream(
            input_dict,
            stream_mode="messages",
            context=context,
        ):
            if not isinstance(chunk, AIMessageChunk):
                continue

            # 工具调用消息不推给前端；如果此前已经推过“答案草稿”，
            # 发一个 reset 让前端清空，避免草稿和最终答案拼在一起。
            if getattr(chunk, "tool_call_chunks", None):
                if not in_tool_call_stream:
                    yield {"type": "reset"}
                    in_tool_call_stream = True
                continue
            in_tool_call_stream = False

            content = chunk.content
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            if content:
                yield {"type": "delta", "content": content}

        yield {"type": "sources", "sources": context.get("sources", [])}


async def _main():
    query = sys.argv[1] if len(sys.argv) > 1 else "最近有什么科技新闻？"
    agent = ReactAgent()
    async for event in agent.astream_events(query):
        if event["type"] == "delta":
            print(event["content"], end="", flush=True)
        elif event["type"] == "reset":
            print("\n[reset]\n", end="", flush=True)
        elif event["type"] == "sources":
            print("\n\n来源：")
            for source in event["sources"]:
                print(source)


if __name__ == "__main__":
    asyncio.run(_main())
