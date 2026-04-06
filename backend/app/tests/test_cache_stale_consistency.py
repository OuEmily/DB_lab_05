"""
LAB 05: Демонстрация неконсистентности кэша.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.main import app
from app.infrastructure.db import SessionLocal


@pytest.mark.asyncio
async def test_stale_order_card_when_db_updated_without_invalidation():
    """
    TODO: Реализовать сценарий:
    1) Прогреть кэш карточки заказа (GET /api/cache-demo/orders/{id}/card?use_cache=true).
    2) Изменить заказ в БД через endpoint mutate-without-invalidation.
    3) Повторно запросить карточку с use_cache=true.
    4) Проверить, что клиент получает stale данные из кэша.
    """
    order_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    async with SessionLocal() as session:
        await session.execute(
            text("INSERT INTO users (id, email, name, created_at) VALUES (:u, :e, 'Test Stale', NOW())"),
            {"u": user_id, "e": f"stale_{user_id}@test.com"}
        )
        await session.execute(
            text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:o, :u, 'created', 100.0, NOW())"),
            {"o": order_id, "u": user_id}
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")
        assert resp1.status_code == 200
        assert resp1.json()["total_amount"] == 100.0

        resp2 = await client.post(
            f"/api/cache-demo/orders/{order_id}/mutate-without-invalidation",
            json={"new_total_amount": 500.0}
        )
        assert resp2.status_code == 200

        resp3 = await client.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")
        assert resp3.status_code == 200
        assert resp3.json()["total_amount"] == 100.0

        async with SessionLocal() as session:
            result = await session.execute(
                text("SELECT total_amount FROM orders WHERE id = :o"),
                {"o": order_id}
            )
            db_amount = result.scalar()
            assert db_amount == 500.0