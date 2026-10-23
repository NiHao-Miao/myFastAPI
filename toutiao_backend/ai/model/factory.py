"""模型工厂：OpenAI 兼容协议接入 DashScope / 阿里云 MaaS。"""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..utils.config_handler import rag_conf
from ..utils.env import (
    get_api_key,
    get_base_url,
    get_embedding_model,
    get_model_id,
    get_request_timeout,
)

_chat_model: ChatOpenAI | None = None
_embed_model: OpenAIEmbeddings | None = None


def get_chat_model() -> ChatOpenAI:
    global _chat_model
    if _chat_model is None:
        _chat_model = ChatOpenAI(
            model=get_model_id(rag_conf.get("chat_model_name")),
            base_url=get_base_url(),
            api_key=get_api_key(),
            temperature=float(rag_conf.get("temperature", 0.2)),
            timeout=get_request_timeout(int(rag_conf.get("request_timeout", 120))),
            max_retries=2,
            streaming=True,
        )
    return _chat_model


def get_embed_model() -> OpenAIEmbeddings:
    global _embed_model
    if _embed_model is None:
        _embed_model = OpenAIEmbeddings(
            model=get_embedding_model(rag_conf.get("embedding_model_name", "text-embedding-v4")),
            base_url=get_base_url(),
            api_key=get_api_key(),
            check_embedding_ctx_length=False,
            chunk_size=10,
            max_retries=2,
        )
    return _embed_model


if __name__ == "__main__":
    print(get_chat_model().model_name)
    print(get_embed_model().model)
