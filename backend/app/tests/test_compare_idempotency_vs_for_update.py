"""
LAB 04: Сравнение подходов
1) FOR UPDATE (решение из lab_02)
2) Idempotency-Key + middleware (lab_04)
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.db import SessionLocal
from sqlalchemy import text


@pytest.mark.asyncio
async def test_compare_for_update_and_idempotency_behaviour():
    """
    TODO: Реализовать сравнительный тест/сценарий.

    Минимум сравнения:
    1) Повтор запроса с mode='for_update':
       - защита от гонки на уровне БД,
       - повтор может вернуть бизнес-ошибку "already paid".
    2) Повтор запроса с mode='unsafe' + Idempotency-Key:
       - второй вызов возвращает тот же кэшированный успешный ответ,
         без повторного списания.

    В конце добавьте вывод:
    - чем отличаются цели и UX двух подходов,
    - почему они не взаимоисключающие и могут использоваться вместе.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_id = str(uuid.uuid4())
        order_for_update = str(uuid.uuid4())
        order_idempotent = str(uuid.uuid4())

        async with SessionLocal() as session:
            await session.execute(
                text("INSERT INTO users (id, email, name, created_at) VALUES (:u, :e, 'Test', NOW())"),
                {"u": user_id, "e": f"{user_id}@mail.com"}
            )
            await session.execute(
                text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:o, :u, 'created', 100.0, NOW())"),
                {"o": order_for_update, "u": user_id}
            )
            await session.execute(
                text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:o, :u, 'created', 200.0, NOW())"),
                {"o": order_idempotent, "u": user_id}
            )
            await session.commit()

        # 1) Повтор запроса с mode='for_update' 
        payload_for_update = {"order_id": order_for_update, "mode": "for_update"}
        
        res1_first = await client.post("/api/payments/retry-demo", json=payload_for_update)
        assert res1_first.json()["success"] is True

        res1_second = await client.post("/api/payments/retry-demo", json=payload_for_update)
        assert res1_second.json()["success"] is False
        assert "already" in res1_second.json()["message"].lower()

        # 2) Повтор запроса с mode='unsafe' + Idempotency-Key
        payload_idempotent = {"order_id": order_idempotent, "mode": "unsafe"}
        headers = {"Idempotency-Key": f"key-{order_idempotent}"}
        
        res2_first = await client.post("/api/payments/retry-demo", json=payload_idempotent, headers=headers)
        assert res2_first.json()["success"] is True

        res2_second = await client.post("/api/payments/retry-demo", json=payload_idempotent, headers=headers)
        assert res2_second.json()["success"] is True
        assert res2_second.headers.get("X-Idempotency-Replayed") == "true"

    print("FOR UPDATE защищает БД от параллельных транзакций (Race Condition).")
    print("Idempotency-Key защищает клиента от повторных действий при retry-запросах.")
    print("UX (пользовательский опыт): При повторе запроса FOR UPDATE выдает ошибку, "
          "а Idempotency-Key отдает закэшированный успешный результат")
    print("Итог: Они не взаимоисключающие. FOR UPDATE работает на нижнем уровне, а Idempotency-Key — на верхнем (API).")
    
