"""
LAB 04: Проверка идемпотентного повтора запроса.

Цель:
При повторном запросе с тем же Idempotency-Key вернуть
кэшированный результат без повторного списания.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.db import SessionLocal
from sqlalchemy import text


@pytest.mark.asyncio
async def test_retry_with_same_key_returns_cached_response():
    """
    TODO: Реализовать тест.

    Рекомендуемые шаги:
    1) Создать заказ в статусе created.
    2) Сделать первый POST /api/payments/retry-demo (mode='unsafe')
       с заголовком Idempotency-Key: fixed-key-123.
    3) Повторить тот же POST с тем же ключом и тем же payload.
    4) Проверить:
       - второй ответ пришёл из кэша (через признак, который вы добавите,
         например header X-Idempotency-Replayed=true),
       - в order_status_history только одно событие paid,
       - в idempotency_keys есть запись completed с response_body/status_code.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        order_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        idempotency_key = f"fixed-key-{order_id}"
        
        async with SessionLocal() as session:
            await session.execute(
                text("INSERT INTO users (id, email, name, created_at) VALUES (:u, :e, 'Test', NOW())"), 
                {"u": user_id, "e": f"{user_id}@mail.com"}
            )
            await session.execute(
                text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:o, :u, 'created', 100.0, NOW())"),
                {"o": order_id, "u": user_id}
            )
            await session.commit()
            
        payload = {"order_id": order_id, "mode": "unsafe"}
        headers = {"Idempotency-Key": idempotency_key}
        
        res1 = await client.post("/api/payments/retry-demo", json=payload, headers=headers)
        assert res1.status_code == 200
        
        res2 = await client.post("/api/payments/retry-demo", json=payload, headers=headers)
        
        assert res2.status_code == 200
        assert res2.headers.get("X-Idempotency-Replayed") == "true"
        assert res1.json() == res2.json()
        
        async with SessionLocal() as session:
            history_result = await session.execute(
                text("SELECT status FROM order_status_history WHERE order_id = :o AND status = 'paid'"), 
                {"o": order_id}
            )
            paid_count = len(history_result.fetchall())
            assert paid_count == 1
            
            idem_result = await session.execute(
                text("SELECT status, status_code, response_body FROM idempotency_keys WHERE idempotency_key = :k"),
                {"k": idempotency_key}
            )
            idem_record = idem_result.mappings().first()
            assert idem_record is not None
            assert idem_record["status"] == "completed"
            assert idem_record["status_code"] == 200
            assert idem_record["response_body"] is not None


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_conflict():
    """
    TODO: Реализовать негативный тест.

    Один и тот же Idempotency-Key нельзя использовать с другим payload.
    Ожидается 409 Conflict (или эквивалентная бизнес-ошибка).
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Idempotency-Key": "shared-conflict-key-123"}
        
        payload_1 = {"order_id": str(uuid.uuid4()), "mode": "unsafe"}
        payload_2 = {"order_id": str(uuid.uuid4()), "mode": "safe"}
        
        await client.post("/api/payments/retry-demo", json=payload_1, headers=headers)
        
        res2 = await client.post("/api/payments/retry-demo", json=payload_2, headers=headers)
        
        assert res2.status_code == 409
        assert "different payload" in res2.json()["detail"].lower()