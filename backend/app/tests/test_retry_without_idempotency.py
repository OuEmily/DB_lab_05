"""
LAB 04: Демонстрация проблемы retry без идемпотентности.

Сценарий:
1) Клиент отправил запрос на оплату.
2) До получения ответа "сеть оборвалась" (моделируем повтором запроса).
3) Клиент повторил запрос БЕЗ Idempotency-Key.
4) В unsafe-режиме возможна двойная оплата.
"""

import pytest
import uuid
import asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.db import SessionLocal
from sqlalchemy import text


@pytest.mark.asyncio
async def test_retry_without_idempotency_can_double_pay():
    """
    TODO: Реализовать тест.

    Рекомендуемые шаги:
    1) Создать заказ в статусе created.
    2) Выполнить две параллельные попытки POST /api/payments/retry-demo
       с mode='unsafe' и БЕЗ заголовка Idempotency-Key.
    3) Проверить историю order_status_history:
       - paid-событий больше 1 (или иная метрика двойного списания).
    4) Вывести понятный отчёт в stdout:
       - сколько попыток
       - сколько paid в истории
       - почему это проблема.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        order_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
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
        
        await asyncio.gather(
            client.post("/api/payments/retry-demo", json=payload),
            client.post("/api/payments/retry-demo", json=payload)
        )
        
        async with SessionLocal() as session:
            result = await session.execute(
                text("SELECT status FROM order_status_history WHERE order_id = :o AND status = 'paid'"), 
                {"o": order_id}
            )
            paid_count = len(result.fetchall())
            
        print("\n--- Отчет: Retry без идемпотентности ---")
        print("Количество попыток оплаты: 2 (параллельно)")
        print(f"Количество записей 'paid' в истории: {paid_count}")
        print("Почему это проблема: Произошло двойное списание (race condition).")
        print("Без Idempotency-Key сервер обработал оба запроса как независимые.")
        
        assert paid_count > 1
