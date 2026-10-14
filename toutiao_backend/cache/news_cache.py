from typing import Any, Dict, List, Optional

from config.cache_conf import get_json_cache, set_cache


CATEGORIES_KEY = "news:categories"
NEWS_LIST_PREKEY = "news:list"
async def get_cached_categories():
    return await get_json_cache(CATEGORIES_KEY)

async def set_cached_categories(data: List[Dict[str, Any]], expire: int = 7200):
    return await set_cache(CATEGORIES_KEY, data, expire)

async def set_cache_news_list(category_id: Optional[int], page: int, page_size: int, news_list: List[Dict[str, Any]], expire: int = 1000):
    category_part = category_id if category_id is not None else "all"
    key = f"{NEWS_LIST_PREKEY}:{category_part}:{page}:{page_size}"
    return await set_cache(key, news_list, expire)

async def get_cache_news_list(category_id: Optional[int], page: int, page_size: int):
    category_part = category_id if category_id is not None else "all"
    key = f"{NEWS_LIST_PREKEY}:{category_part}:{page}:{page_size}"
    return await get_json_cache(key)