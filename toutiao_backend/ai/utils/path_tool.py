"""为 ai 包提供统一的绝对路径（根目录 = toutiao_backend/ai）。"""
from pathlib import Path


def get_project_root() -> str:
    """返回 ai 包根目录：toutiao_backend/ai。"""
    return str(Path(__file__).resolve().parents[1])


def get_abs_path(relative_path: str) -> str:
    """把 ai 包内的相对路径转换为绝对路径。"""
    return str(Path(get_project_root()) / relative_path)


if __name__ == "__main__":
    print(get_abs_path("config/chroma.yml"))
