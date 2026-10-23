"""读取 ai/prompts 下的三个提示词。"""
from .config_handler import prompts_conf
from .logger_handler import logger
from .path_tool import get_abs_path


def _read_prompt(config_key: str, label: str) -> str:
    try:
        prompt_path = get_abs_path(prompts_conf[config_key])
    except KeyError as e:
        logger.error(f"[prompt_loader]在 prompts.yml 中没有 {config_key} 配置项")
        raise e

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[prompt_loader]读取{label}失败：{str(e)}")
        raise e


def load_system_prompts() -> str:
    return _read_prompt("main_prompt_path", "主提示词")


def load_rag_prompts() -> str:
    return _read_prompt("rag_summarize_prompt_path", "RAG 总结提示词")


def load_briefing_prompts() -> str:
    return _read_prompt("briefing_prompt_path", "新闻简报提示词")
