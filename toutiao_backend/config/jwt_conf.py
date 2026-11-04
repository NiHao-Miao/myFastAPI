"""JWT 相关配置，从 toutiao_backend/.env 读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# config/jwt_conf.py -> config -> toutiao_backend
# 用绝对路径加载 .env，避免从不同目录启动时找不到配置
BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BACKEND_ROOT / ".env", override=False)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数，当前值为：{raw}") from exc


JWT_SECRET_KEY = (os.getenv("JWT_SECRET_KEY") or "").strip()
JWT_ALGORITHM = (os.getenv("JWT_ALGORITHM") or "HS256").strip()
JWT_ISSUER = (os.getenv("JWT_ISSUER") or "toutiao-api").strip()
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = _get_int("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = _get_int("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7)

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "未配置 JWT_SECRET_KEY：请在 toutiao_backend/.env 中添加一行 "
        "JWT_SECRET_KEY=<随机字符串>"
    )
if len(JWT_SECRET_KEY) < 32:
    raise RuntimeError("JWT_SECRET_KEY 至少需要 32 个字符，建议使用 64 位十六进制")
if JWT_ALGORITHM != "HS256":
    raise RuntimeError("当前示例仅支持 HS256，请勿随意修改 JWT_ALGORITHM")
if JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    raise RuntimeError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")
if JWT_REFRESH_TOKEN_EXPIRE_DAYS <= 0:
    raise RuntimeError("JWT_REFRESH_TOKEN_EXPIRE_DAYS 必须大于 0")