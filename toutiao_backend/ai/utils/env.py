"""加载并读取 toutiao_backend/.env 中的模型配置。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# ai/utils/env.py -> ai/utils -> ai -> toutiao_backend
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"

# 不覆盖已经存在的系统环境变量，方便 Docker/CI 注入
load_dotenv(dotenv_path=ENV_FILE, override=False)


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def get_api_key() -> str:
    key = get_env("OPENAI_API_KEY") or get_env("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError(
            "未配置模型 API Key：请在 toutiao_backend/.env 中设置 "
            "OPENAI_API_KEY 或 DASHSCOPE_API_KEY"
        )
    return key


def get_base_url() -> str:
    return get_env(
        "BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def get_model_id(default: str | None = None) -> str:
    return get_env("MODEL_ID", default) or "qwen3.8-max"


def get_embedding_model(default: str = "text-embedding-v4") -> str:
    return get_env("EMBEDDING_MODEL", default) or default


def get_request_timeout(default: int = 120) -> int:
    raw = get_env("AI_REQUEST_TIMEOUT")
    try:
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    print("env file:", ENV_FILE, "exists:", ENV_FILE.exists())
    print("base_url:", get_base_url())
    print("model_id:", get_model_id())
    print("embedding_model:", get_embedding_model())
    print("api_key_set:", bool(get_api_key()))
