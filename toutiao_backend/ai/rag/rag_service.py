"""RAG 总结服务：检索新闻参考，让模型只基于参考新闻总结。"""
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from ..model.factory import get_chat_model
from ..utils.prompt_loader import load_rag_prompts
from .vector_store import VectorStoreService


class RagSummarizeService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_template = PromptTemplate.from_template(load_rag_prompts())
        self.model = get_chat_model()
        self.chain = self.prompt_template | self.model | StrOutputParser()

    def retriever_docs(self, query: str) -> list[Document]:
        return self.retriever.invoke(query)

    def rag_summarize(self, query: str) -> tuple[str, list[dict]]:
        context_docs = self.retriever_docs(query)
        if not context_docs:
            return "当前新闻库中暂无相关报道。", []

        context_parts: list[str] = []
        sources: list[dict] = []
        seen_news: set[int] = set()

        for doc in context_docs:
            metadata = doc.metadata or {}
            news_id = metadata.get("news_id")
            ref_index = len(context_parts) + 1
            context_parts.append(
                "\n".join(
                    [
                        f"【参考资料{ref_index}】",
                        f"标题：{metadata.get('title', '')}",
                        f"分类：{metadata.get('category', '')}",
                        f"发布时间：{metadata.get('publish_time', '')}",
                        f"作者：{metadata.get('author', '')}",
                        f"内容：{doc.page_content}",
                    ]
                )
            )

            if news_id is not None and news_id not in seen_news:
                seen_news.add(news_id)
                sources.append(
                    {
                        "index": ref_index,
                        "newsId": news_id,
                        "title": metadata.get("title", ""),
                        "category": metadata.get("category", ""),
                        "author": metadata.get("author", ""),
                        "publishTime": metadata.get("publish_time", ""),
                    }
                )

        context = "\n\n".join(context_parts)
        answer = self.chain.invoke({"input": query, "context": context})
        return answer.strip(), sources


if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "2024年新年贺词讲了什么？"
    rag = RagSummarizeService()
    answer, sources = rag.rag_summarize(query)
    print(answer)
    print("\n来源：")
    for source in sources:
        print(source)
