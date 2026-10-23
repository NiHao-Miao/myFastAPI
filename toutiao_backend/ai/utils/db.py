"""只读 MySQL 访问工具（pymysql）。

优先使用 .env 中的 DB_*；没有则复用 toutiao_backend/config/db_config.py
里的 ASYNC_DATABASE_URL。
"""
import sys
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy.engine import make_url

from .env import BACKEND_ROOT, get_env
from .logger_handler import logger


def _connection_params() -> dict[str, Any]:
    host = get_env("DB_HOST")
    user = get_env("DB_USER")
    password = get_env("DB_PASSWORD")
    database = get_env("DB_NAME")

    if host and user and database:
        return {
            "host": host,
            "port": int(get_env("DB_PORT", "3306") or 3306),
            "user": user,
            "password": password or "",
            "database": database,
        }

    # 复用后端现有数据库配置，避免再维护一份密码
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from config.db_config import ASYNC_DATABASE_URL  # type: ignore

    url = make_url(ASYNC_DATABASE_URL)
    return {
        "host": url.host or "localhost",
        "port": url.port or 3306,
        "user": url.username or "root",
        "password": url.password or "",
        "database": url.database or "news_app",
    }


def get_connection() -> pymysql.connections.Connection:
    params = _connection_params()
    return pymysql.connect(
        **params,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=30,
    )


@contextmanager
def get_cursor() -> Iterator[DictCursor]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    try:
        with get_cursor() as cursor:
            cursor.execute(sql, params or ())
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"[db]查询失败：{str(e)}；SQL={sql}；params={params}")
        raise


def fetch_one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


if __name__ == "__main__":
    print(_connection_params())
    print(fetch_one("SELECT COUNT(*) AS total FROM news"))
