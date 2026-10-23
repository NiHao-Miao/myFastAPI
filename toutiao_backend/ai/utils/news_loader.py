"""解析导出的新闻 txt 文件，生成带 news_id 元数据的 Document。"""
import os
from typing import Any

from langchain_core.documents import Document

from .logger_handler import logger

FIELD_PREFIXES: dict[str, str] = {
    "【新闻ID】": "news_id",
    "【标题】": "title",
    "【分类】": "category",
    "【作者】": "author",
    "【发布时间】": "publish_time",
    "【摘要】": "description",
}

BODY_PREFIX = "【正文】"


def parse_news_text(filepath: str) -> tuple[dict[str, Any], str]:
    """解析新闻 txt，返回 (字段字典, 正文)。"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    fields: dict[str, Any] = {}
    body_lines: list[str] = []
    in_body = False

    for line in text.splitlines():
        if in_body:
            body_lines.append(line)
            continue

        if line.startswith(BODY_PREFIX):
            in_body = True
            continue

        for prefix, key in FIELD_PREFIXES.items():
            if line.startswith(prefix):
                fields[key] = line[len(prefix):].strip()
                break

    body = "\n".join(body_lines).strip()

    if "news_id" in fields:
        try:
            fields["news_id"] = int(str(fields["news_id"]).strip())
        except (TypeError, ValueError):
            logger.error(f"[news_loader]{filepath} 的新闻ID不是整数：{fields['news_id']!r}")
            fields.pop("news_id", None)

    return fields, body


def news_txt_loader(filepath: str) -> list[Document]:
    """读取单个新闻 txt，返回一个 Document。"""
    fields, body = parse_news_text(filepath)

    news_id = fields.get("news_id")
    title = fields.get("title", "")
    if news_id is None or not title:
        logger.error(f"[news_loader]{filepath} 缺少新闻ID或标题，跳过")
        return []

    description = fields.get("description", "")
    page_content = "\n".join(part for part in (title, description, body) if part).strip()
    if not page_content:
        logger.warning(f"[news_loader]{filepath} 没有有效正文，跳过")
        return []

    metadata = {
        "news_id": news_id,
        "title": title,
        "category": fields.get("category", ""),
        "author": fields.get("author", ""),
        "publish_time": fields.get("publish_time", ""),
        "source": os.path.basename(filepath),
    }
    return [Document(page_content=page_content, metadata=metadata)]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        docs = news_txt_loader(sys.argv[1])
        for doc in docs:
            print(doc.metadata)
            print(doc.page_content[:200])
    else:
        print("用法: python -m ai.utils.news_loader <news_0001.txt>")
