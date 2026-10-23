"""新闻向量库：沿用 AgentRAG 的 txt → 切片 → Chroma 链路。"""
import os

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..model.factory import get_embed_model
from ..utils.config_handler import chroma_conf
from ..utils.file_handler import get_file_md5_hex, listdir_with_allowed_type
from ..utils.logger_handler import logger
from ..utils.news_loader import news_txt_loader
from ..utils.path_tool import get_abs_path


class VectorStoreService:
    def __init__(self):
        self.vector_store = self._create_store()
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def _create_store(self) -> Chroma:
        return Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=get_embed_model(),
            persist_directory=get_abs_path(chroma_conf["persist_directory"]),
        )

    def _reset_collection(self):
        try:
            self.vector_store.delete_collection()
            logger.info("[向量库]旧 collection 已删除")
        except Exception as e:
            logger.warning(f"[向量库]删除 collection 失败（可能本来不存在）：{str(e)}")
        self.vector_store = self._create_store()

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

    def search(self, query: str, k: int | None = None) -> list[Document]:
        return self.vector_store.similarity_search(query, k=k or chroma_conf["k"])

    def count(self) -> int:
        result = self.vector_store.get(include=["metadatas"])
        return len(result.get("ids", []))

    def load_document(self, rebuild: bool = False) -> dict:
        """读取 data/news/*.txt，切片后写入 Chroma。

        - rebuild=True：清空 collection 和 MD5 记录，全量重建；
        - rebuild=False：按文件 MD5 增量，内容变化的新闻先按 news_id 删除旧向量；
        - 每次都会清理数据库中已不存在新闻的向量。
        """
        data_path = get_abs_path(chroma_conf["data_path"])
        md5_store_path = get_abs_path(chroma_conf["md5_hex_store"])
        os.makedirs(os.path.dirname(md5_store_path), exist_ok=True)

        if rebuild:
            self._reset_collection()
            if os.path.exists(md5_store_path):
                os.remove(md5_store_path)

        existing_md5: set[str] = set()
        if os.path.exists(md5_store_path):
            with open(md5_store_path, "r", encoding="utf-8") as f:
                existing_md5 = {line.strip() for line in f if line.strip()}

        allowed_files = listdir_with_allowed_type(
            data_path,
            tuple(chroma_conf["allow_knowledge_file_type"]),
        )
        if not allowed_files:
            logger.warning(f"[加载知识库]{data_path} 下没有可处理的 txt 文件")
            return {"files": 0, "added": 0, "skipped": 0, "failed": 0, "vectors": self.count()}

        current_news_ids: set[int] = set()
        docs_to_add: list[Document] = []
        news_ids_to_delete: set[int] = set()
        new_md5s: list[str] = []
        added = skipped = failed = 0

        for path in allowed_files:
            try:
                documents = news_txt_loader(path)
                if not documents:
                    logger.warning(f"[加载知识库]{path} 没有有效文本内容，跳过")
                    failed += 1
                    continue

                news_id = documents[0].metadata.get("news_id")
                if news_id is None:
                    logger.warning(f"[加载知识库]{path} 缺少 news_id，跳过")
                    failed += 1
                    continue
                news_id = int(news_id)
                current_news_ids.add(news_id)

                md5_hex = get_file_md5_hex(path)
                if not md5_hex:
                    failed += 1
                    continue

                if not rebuild and md5_hex in existing_md5:
                    skipped += 1
                    continue

                split_docs: list[Document] = self.spliter.split_documents(documents)
                if not split_docs:
                    logger.warning(f"[加载知识库]{path} 分片后没有有效文本内容，跳过")
                    failed += 1
                    continue

                docs_to_add.extend(split_docs)
                news_ids_to_delete.add(news_id)
                new_md5s.append(md5_hex)
                added += 1
                logger.debug(f"[加载知识库]{path} 已加入待写入队列（news_id={news_id}）")
            except Exception as e:
                failed += 1
                logger.error(f"[加载知识库]{path} 加载失败：{str(e)}", exc_info=True)

        # 同一新闻内容更新时，先批量删除旧向量，避免重复命中旧内容
        if news_ids_to_delete:
            try:
                self.vector_store.delete(
                    where={"news_id": {"$in": sorted(news_ids_to_delete)}}
                )
            except Exception as e:
                logger.warning(f"[加载知识库]批量删除旧向量失败，改为逐条删除：{str(e)}")
                for news_id in sorted(news_ids_to_delete):
                    try:
                        self.vector_store.delete(where={"news_id": news_id})
                    except Exception as inner:
                        logger.warning(f"[加载知识库]删除 news_id={news_id} 旧向量失败：{str(inner)}")

        if docs_to_add:
            try:
                self.vector_store.add_documents(docs_to_add)
                with open(md5_store_path, "a", encoding="utf-8") as f:
                    for md5_hex in new_md5s:
                        f.write(md5_hex + "\n")
                logger.info(f"[向量库]批量写入 {len(docs_to_add)} 个切片，涉及 {added} 条新闻")
            except Exception as e:
                failed += added
                added = 0
                logger.error(f"[向量库]批量写入失败：{str(e)}", exc_info=True)

        self._cleanup_stale_vectors(current_news_ids)

        result = {
            "files": len(allowed_files),
            "added": added,
            "skipped": skipped,
            "failed": failed,
            "vectors": self.count(),
        }
        logger.info(f"[向量库]加载完成：{result}")
        return result

    def _cleanup_stale_vectors(self, current_news_ids: set[int]):
        """删除数据库中已不存在的 news_id 对应的向量。"""
        try:
            existing = self.vector_store.get(include=["metadatas"])
            ids = existing.get("ids", [])
            metadatas = existing.get("metadatas", [])
            stale_ids = []
            for doc_id, metadata in zip(ids, metadatas):
                news_id = (metadata or {}).get("news_id")
                if news_id not in current_news_ids:
                    stale_ids.append(doc_id)
            if stale_ids:
                self.vector_store.delete(ids=stale_ids)
                logger.info(f"[向量库]已清理 {len(stale_ids)} 条过期新闻向量")
        except Exception as e:
            logger.error(f"[向量库]清理过期向量失败：{str(e)}", exc_info=True)


if __name__ == "__main__":
    import sys

    vs = VectorStoreService()
    if len(sys.argv) > 1:
        for doc in vs.search(sys.argv[1]):
            print(doc.metadata)
            print(doc.page_content[:200])
            print("-" * 30)
    else:
        print("当前向量数：", vs.count())
