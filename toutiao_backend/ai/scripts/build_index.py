"""构建/更新新闻向量库。

用法（在 toutiao_backend 目录下）：
    python -m ai.scripts.build_index --rebuild
    python -m ai.scripts.build_index
    python -m ai.scripts.build_index --query "新年贺词"
"""
import argparse
import json

from ..rag.vector_store import VectorStoreService


def main():
    parser = argparse.ArgumentParser(description="构建新闻 Chroma 向量库")
    parser.add_argument("--rebuild", action="store_true", help="清空并全量重建")
    parser.add_argument("--query", default="", help="构建后执行一次检索测试")
    args = parser.parse_args()

    service = VectorStoreService()
    result = service.load_document(rebuild=args.rebuild)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.query:
        print("=" * 50)
        print(f"检索：{args.query}")
        docs = service.search(args.query)
        for doc in docs:
            print(doc.metadata)
            print(doc.page_content[:200])
            print("-" * 30)


if __name__ == "__main__":
    main()
