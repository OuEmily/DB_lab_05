"""Cache service template for LAB 05."""

import json
from typing import Any


class CacheService:
    """
    Сервис кэширования каталога и карточки заказа.

    TODO:
    - реализовать методы через Redis client + БД;
    - добавить TTL и версионирование ключей.
    """

    def __init__(self, redis_client: Any, repository: Any):
        self.redis = redis_client
        self.repository = repository
        self.ttl = 300

    async def get_catalog(self, *, use_cache: bool = True) -> list[dict[str, Any]]:
        """
        TODO:
        1) Попытаться вернуть catalog из Redis.
        2) При miss загрузить из БД.
        3) Положить в Redis с TTL.
        """
        cache_key = "catalog:v1"
        
        if use_cache:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
                
        catalog_data = await self.repository.get_all_catalog_items()
        
        await self.redis.set(cache_key, json.dumps(catalog_data), ex=self.ttl)
        return catalog_data

    async def get_order_card(self, order_id: str, *, use_cache: bool = True) -> dict[str, Any]:
        """
        TODO:
        1) Попытаться вернуть карточку заказа из Redis.
        2) При miss загрузить из БД.
        3) Положить в Redis с TTL.
        """
        cache_key = f"order_card:v1:{order_id}"
        
        if use_cache:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)

        order_data = await self.repository.get_order_by_id(order_id)
        
        await self.redis.set(cache_key, json.dumps(order_data), ex=self.ttl)
        return order_data

    async def invalidate_order_card(self, order_id: str) -> None:
        """TODO: Удалить ключ карточки заказа из Redis."""
        cache_key = f"order_card:v1:{order_id}"
        await self.redis.delete(cache_key)

    async def invalidate_catalog(self) -> None:
        """TODO: Удалить ключ каталога из Redis."""
        await self.redis.delete("catalog:v1")