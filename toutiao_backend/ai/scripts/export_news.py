"""从 MySQL 导出新闻为 AgentRAG 可处理的 txt 文件。

用法（在 toutiao_backend 目录下）：
    python -m ai.scripts.export_news
    python -m ai.scripts.export_news --dry-run
    python -m ai.scripts.export_news --output-dir ai/data/news
"""
import argparse
from datetime import date, datetime
from pathlib import Path

from ..utils.config_handler import chroma_conf
from ..utils.db import fetch_all
from ..utils.path_tool import get_abs_path

NEWS_SQL = """
SELECT n.id, n.title, n.description, n.content, n.author,
       n.category_id, c.name AS category, n.publish_time
FROM news n
JOIN news_category c ON c.id = n.category_id
ORDER BY n.id
"""


def _format_time(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def _one_line(value) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").strip()


def _normalize_body(value) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def render_news(row: dict) -> str:
    return "\n".join(
        [
            f"【新闻ID】{row['id']}",
            f"【标题】{_one_line(row.get('title'))}",
            f"【分类】{_one_line(row.get('category'))}",
            f"【作者】{_one_line(row.get('author') or '未知')}",
            f"【发布时间】{_format_time(row.get('publish_time'))}",
            f"【摘要】{_one_line(row.get('description'))}",
            "【正文】",
            _normalize_body(row.get("content")),
            "",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="从 MySQL 导出新闻为 txt")
    parser.add_argument(
        "--output-dir",
        default=get_abs_path(chroma_conf["data_path"]),
        help="输出目录，默认 ai/data/news",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    parser.add_argument("--no-clean", action="store_true", help="不清理数据库中已不存在的旧文件")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = fetch_all(NEWS_SQL)
    expected_stems: set[str] = set()
    written = unchanged = skipped_empty = 0

    for row in rows:
        news_id = int(row["id"])
        stem = f"news_{news_id:04d}"
        expected_stems.add(stem)
        body = _normalize_body(row.get("content"))
        if not body:
            skipped_empty += 1
            print(f"[跳过] news_id={news_id} 正文为空")
            continue

        filepath = output_dir / f"{stem}.txt"
        content = render_news(row)
        if filepath.exists() and filepath.read_text(encoding="utf-8") == content:
            unchanged += 1
            continue

        if args.dry_run:
            print(f"[dry-run] {filepath}")
            continue

        filepath.write_text(content, encoding="utf-8")
        written += 1

    removed = 0
    if not args.no_clean:
        for filepath in output_dir.glob("news_*.txt"):
            if filepath.stem not in expected_stems:
                if args.dry_run:
                    print(f"[dry-run] 删除过期文件 {filepath}")
                else:
                    filepath.unlink()
                removed += 1

    print("=" * 50)
    print(f"数据库新闻数：{len(rows)}")
    print(f"写入/更新文件数：{written}")
    print(f"内容未变跳过：{unchanged}")
    print(f"空正文跳过：{skipped_empty}")
    print(f"清理过期文件：{removed}")
    print(f"输出目录：{output_dir}")


if __name__ == "__main__":
    main()
