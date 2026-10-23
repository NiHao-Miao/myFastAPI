"""文件工具：MD5、目录扫描、txt 读取（新闻数据只使用 txt）。"""
import hashlib
import os

from langchain_core.documents import Document

from .logger_handler import logger


def get_file_md5_hex(filepath: str) -> str | None:
    if not os.path.exists(filepath):
        logger.error(f"[md5计算]文件{filepath}不存在")
        return None

    if not os.path.isfile(filepath):
        logger.error(f"[md5计算]路径{filepath}不是文件")
        return None

    md5_obj = hashlib.md5()
    chunk_size = 4096
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)
        return md5_obj.hexdigest()
    except Exception as e:
        logger.error(f"计算文件{filepath}md5失败，{str(e)}")
        return None


def listdir_with_allowed_type(path: str, allowed_types: tuple[str, ...]) -> tuple[str, ...]:
    files: list[str] = []

    if not os.path.isdir(path):
        logger.error(f"[listdir_with_allowed_type]{path}不是文件夹")
        return tuple()

    for filename in sorted(os.listdir(path)):
        if filename.endswith(allowed_types):
            files.append(os.path.join(path, filename))

    return tuple(files)


def txt_loader(filepath: str) -> list[Document]:
    """通用 txt 读取；新闻文件请使用 news_loader。"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return [Document(page_content=content, metadata={"source": os.path.basename(filepath)})]
