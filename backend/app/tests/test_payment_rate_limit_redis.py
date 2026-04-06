"""
LAB 05: Rate limiting endpoint оплаты через Redis.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.redis_client import get_redis


@pytest.mark.asyncio
async def test_payment_endpoint_rate_limit():
    """
    TODO: Реализовать тест.

    Рекомендуемая проверка:
    1) Сделать N запросов оплаты в пределах одного окна.
    2) Проверить, что первые <= limit проходят.
    3) Следующие запросы получают 429 Too Many Requests.
    4) Проверить заголовки X-RateLimit-Limit / X-RateLimit-Remaining.
    """
    order_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    redis = get_redis()
    await redis.delete(f"rate_limit:pay:{user_id}")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        limit = 5
        
        for i in range(limit):
            response = await client.post(
                f"/api/orders/{order_id}/pay",
                headers={"X-User-Id": user_id}
            )
            assert response.status_code != 429
            assert response.headers["X-RateLimit-Limit"] == str(limit)
            assert response.headers["X-RateLimit-Remaining"] == str(limit - (i + 1))
        
        response_429 = await client.post(
            f"/api/orders/{order_id}/pay",
            headers={"X-User-Id": user_id}
        )
        assert response_429.status_code == 429
        assert response_429.json() == {"detail": "Too Many Requests"}