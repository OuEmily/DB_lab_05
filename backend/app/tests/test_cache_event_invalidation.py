"""
LAB 05: Проверка починки через событийную инвалидацию.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.main import app
from app.infrastructure.db import SessionLocal
from app.infrastructure.redis_client import get_redis


@pytest.mark.asyncio
async def test_order_card_is_fresh_after_event_invalidation():
    """
    TODO: Реализовать сценарий:
    1) Прогреть кэш карточки заказа.
    2) Изменить заказ через mutate-with-event-invalidation.
    3) Убедиться, что ключ карточки инвалидирован.
    4) Повторный GET возвращает свежие данные из БД, а не stale cache.
    """
    order_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    async with SessionLocal() as session:
        await session.execute(
            text("INSERT INTO users (id, email, name, created_at) VALUES (:u, :e, 'Test Invalidation', NOW())"),
            {"u": user_id, "e": f"invalidation_{user_id}@test.com"}
        )
        await session.execute(
            text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:o, :u, 'created', 100.0, NOW())"),
            {"o": order_id, "u": user_id}
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.get(f"/api/cache-demo/orders/{order_id}/card")
        assert resp1.status_code == 200
        assert resp1.json()["total_amount"] == 100.0

        resp2 = await client.post(
            f"/api/cache-demo/orders/{order_id}/mutate-with-event-invalidation",
            json={"new_total_amount": 999.99}
        )
        assert resp2.status_code == 200

        redis = get_redis()
        cache_key = f"order_card:v1:{order_id}"
        exists = await redis.exists(cache_key)
        assert exists == 0

        resp3 = await client.get(f"/api/cache-demo/orders/{order_id}/card")
        assert resp3.status_code == 200
        assert resp3.json()["total_amount"] == 999.99