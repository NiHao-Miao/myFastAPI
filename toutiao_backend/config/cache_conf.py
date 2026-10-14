from datetime import datetime
import json
from typing import Any

import redis.asyncio as redis

REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=0

# 创建 Redis 的连接对象
redis_client = redis.Redis(
    host=REDIS_HOST,  # Redis 服务器的主机地址
    port=REDIS_PORT,  # Redis 端口号
    db=REDIS_DB,  # Redis 数据库编号，0~15
    decode_responses=True,  # 是否将字节数据解码为字符串
    protocol=2
)

async def get_cache(key: str):
   try:
    return await redis_client.get(key)
   except Exception as e:
     print(f"Error occurred while fetching cache for key {key}: {e}")
     return None

async def get_json_cache(key: str):
   try:
    result = await redis_client.get(key)
    if result:
        return json.loads(result)
    return None
   except Exception as e:
     print(f"Error occurred while fetching JSON cache for key {key}: {e}")
     return None

async def set_cache(key:str, value:Any, expire: int = 3600):
    try:
       if isinstance(value, (dict, list)):
           value = json.dumps(value, ensure_ascii=False)
       await redis_client.setex(key, expire, value)
       return True
    except Exception as e:
       print(f"Error occurred while setting cache for key {key}: {e}")
       return False