"""新闻 Agent 工具：语义检索 + MySQL 结构化查询。"""
import json
from datetime import date, datetime

from langchain_core.tools import tool

from ...rag.rag_service import RagSummarizeService
from ...utils.db import fetch_all
from ...utils.logger_handler import logger
from .source_marker import SOURCE_MARKER

_rag_service: RagSummarizeService | None = None


def get_rag_service() -> RagSummarizeService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagSummarizeService()
    return _rag_service


_NEWS_SELECT = """
SELECT n.id, n.title, n.description, n.content, n.author,
       n.category_id, c.name AS category, n.publish_time
FROM news n
JOIN news_category c ON c.id = n.category_id
"""


def _format_time(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def _sources_from_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "index": index,
            "newsId": row["id"],
            "title": row.get("title", ""),
            "category": row.get("category", ""),
            "author": row.get("author") or "",
            "publishTime": _format_time(row.get("publish_time")),
        }
        for index, row in enumerate(rows, start=1)
    ]


def _with_sources(text: str, rows: list[dict]) -> str:
    payload = {"sources": _sources_from_rows(rows)}
    return f"{text}{SOURCE_MARKER}{json.dumps(payload, ensure_ascii=False)}"


def _rows_to_text(rows: list[dict]) -> str:
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        description = (row.get("description") or "").strip()
        content = (row.get("content") or "").strip().replace("\n", " ")
        snippet = content[:300] + ("……" if len(content) > 300 else "")
        lines.append(
            "\n".join(
                [
                    f"[{index}] {row.get('title', '')}",
                    f"分类：{row.get('category', '')} | 发布时间：{_format_time(row.get('publish_time'))} | 作者：{row.get('author') or '未知'}",
                    f"摘要：{description or '无'}",
                    f"内容片段：{snippet or '无'}",
                ]
            )
        )
    return "\n\n".join(lines)


def _validate_date(value: str, field_name: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"{field_name} 格式应为 YYYY-MM-DD，收到：{value}") from e
    return value


def _query_news(
    keyword: str = "",
    category: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5,
) -> list[dict]:
    conditions: list[str] = []
    params: list = []

    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        conditions.append("(n.title LIKE %s OR n.description LIKE %s OR n.content LIKE %s)")
        params.extend([like, like, like])

    category = (category or "").strip()
    if category:
        if category.isdigit():
            conditions.append("n.category_id = %s")
            params.append(int(category))
        else:
            conditions.append("c.name = %s")
            params.append(category)

    start_date = _validate_date(start_date, "start_date")
    end_date = _validate_date(end_date, "end_date")
    if start_date:
        conditions.append("n.publish_time >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("n.publish_time < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.append(end_date)

    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 5

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"{_NEWS_SELECT} WHERE {where} ORDER BY n.publish_time DESC, n.id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(sql, params)


@tool(description="从新闻向量库中语义检索新闻，并基于检索到的新闻内容总结回答。适合介绍、解释、归纳类问题。")
def rag_summarize(query: str) -> str:
    try:
        answer, sources = get_rag_service().rag_summarize(query)
        payload = {"sources": sources}
        return f"{answer}{SOURCE_MARKER}{json.dumps(payload, ensure_ascii=False)}"
    except Exception as e:
        logger.error(f"[rag_summarize]失败：{str(e)}", exc_info=True)
        return "检索新闻向量库失败，请稍后重试。"


@tool(description="按关键词、分类、起止日期检索新闻。keyword 可为空；category 传分类名称或分类ID；日期格式 YYYY-MM-DD；limit 最大10。")
def search_news(
    keyword: str = "",
    category: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5,
) -> str:
    try:
        rows = _query_news(keyword, category, start_date, end_date, limit)
        if not rows:
            return "未检索到相关新闻。"
        return _with_sources(_rows_to_text(rows), rows)
    except Exception as e:
        logger.error(f"[search_news]失败：{str(e)}", exc_info=True)
        return f"检索新闻失败：{str(e)}"


@tool(description="获取最新新闻，可按分类筛选。适合“今天有什么新闻”“最新科技新闻”“最近发生了什么”。category 可为空；limit 最大10。")
def get_latest_news(category: str = "", limit: int = 5) -> str:
    try:
        rows = _query_news(keyword="", category=category, limit=limit)
        if not rows:
            return "未检索到相关新闻。"
        return _with_sources(_rows_to_text(rows), rows)
    except Exception as e:
        logger.error(f"[get_latest_news]失败：{str(e)}", exc_info=True)
        return f"获取最新新闻失败：{str(e)}"


@tool(description="按新闻ID获取单篇新闻的完整正文，适合需要详细解读某条新闻时使用。")
def get_news_detail(news_id: int) -> str:
    try:
        rows = fetch_all(f"{_NEWS_SELECT} WHERE n.id = %s LIMIT 1", (int(news_id),))
        if not rows:
            return f"未找到 ID 为 {news_id} 的新闻。"
        row = rows[0]
        content = (row.get("content") or "").strip()
        if len(content) > 4000:
            content = content[:4000] + "……"
        text = "\n".join(
            [
                f"标题：{row.get('title', '')}",
                f"分类：{row.get('category', '')}",
                f"发布时间：{_format_time(row.get('publish_time'))}",
                f"作者：{row.get('author') or '未知'}",
                f"摘要：{row.get('description') or '无'}",
                f"正文：{content}",
            ]
        )
        return _with_sources(text, rows)
    except Exception as e:
        logger.error(f"[get_news_detail]失败：{str(e)}", exc_info=True)
        return f"获取新闻详情失败：{str(e)}"


@tool(description="获取新闻分类列表（分类ID和名称）。当用户提到分类但不确定分类名称时先调用。")
def list_news_categories() -> str:
    try:
        rows = fetch_all("SELECT id, name FROM news_category ORDER BY sort_order, id")
        if not rows:
            return "新闻分类为空。"
        return "\n".join(f"{row['id']}. {row['name']}" for row in rows)
    except Exception as e:
        logger.error(f"[list_news_categories]失败：{str(e)}", exc_info=True)
        return f"获取新闻分类失败：{str(e)}"


@tool(description="获取当前日期，格式 YYYY-MM-DD。用户提到今天、最近、本周时先调用。")
def get_current_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@tool(description="无入参。仅当用户明确要求生成今日新闻简报/新闻日报时调用，用于触发简报提示词切换。")
def fill_context_for_briefing() -> str:
    return "已切换到新闻简报场景。"
