"""读取 ai/config 下的 yaml 配置。"""
from typing import Any

import yaml

from .path_tool import get_abs_path


def _load_yaml(config_path: str, encoding: str = "utf-8") -> dict[str, Any]:
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader) or {}


def load_rag_config(config_path: str = get_abs_path("config/rag.yml")) -> dict[str, Any]:
    return _load_yaml(config_path)


def load_chroma_config(config_path: str = get_abs_path("config/chroma.yml")) -> dict[str, Any]:
    return _load_yaml(config_path)


def load_prompts_config(config_path: str = get_abs_path("config/prompts.yml")) -> dict[str, Any]:
    return _load_yaml(config_path)


rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()


if __name__ == "__main__":
    print(rag_conf)
    print(chroma_conf)
    print(prompts_conf)
