"""
Тест для демонстрации ПРОБЛЕМЫ race condition.

Этот тест должен ПРОХОДИТЬ, подтверждая, что при использовании
pay_order_unsafe() возникает двойная оплата.
"""

import asyncio
import pytest
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.application.payment_service import PaymentService


# TODO: Настроить подключение к тестовой БД
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"

engine = create_async_engine(DATABASE_URL, echo=False)

@pytest.fixture
async def db_session():
    """
    Создать сессию БД для тестов.
    
    TODO: Реализовать фикстуру:
    1. Создать engine
    2. Создать session maker
    3. Открыть сессию
    4. Yield сессию
    5. Закрыть сессию после теста
    """
    async_session_maker = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()

@pytest.fixture
async def test_order(db_session):
    """
    Создать тестовый заказ со статусом 'created'.
    
    TODO: Реализовать фикстуру:
    1. Создать тестового пользователя
    2. Создать тестовый заказ со статусом 'created'
    3. Записать начальный статус в историю
    4. Вернуть order_id
    5. После теста - очистить данные
    """
    # TODO: Реализовать создание тестового заказа
    
    user_id = uuid.uuid4()
    email = f"test_{uuid.uuid4()}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO users (id, name, email) VALUES (:id, :name, :email)"
        ),
        {"id": str(user_id), "name": "Test User", "email": email}
    )
    
    order_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO orders (id, user_id, status, total_amount) VALUES (:id, :user_id, 'created', 100)"
        ),
        {"id": str(order_id), "user_id": str(user_id)}
    )
   
    await db_session.execute(
        text(
            "INSERT INTO order_status_history (id, order_id, status, changed_at) "
            "VALUES (gen_random_uuid(), :order_id, 'created', NOW())"
        ),
        {"order_id": str(order_id)}
    )
    await db_session.commit()

    yield order_id
    
    await db_session.rollback() 
    
    await db_session.execute(text("DELETE FROM order_status_history WHERE order_id = :id"), {"id": order_id})
    await db_session.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db_session.commit()
    
@pytest.mark.asyncio
async def test_concurrent_payment_unsafe_demonstrates_race_condition(db_session, test_order):
    """
    Тест демонстрирует проблему race condition при использовании pay_order_unsafe().
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: Тест ПРОХОДИТ, подтверждая, что заказ был оплачен дважды.
    Это показывает, что метод pay_order_unsafe() НЕ защищен от конкурентных запросов.
    
    TODO: Реализовать тест следующим образом:
    
    1. Создать два экземпляра PaymentService с РАЗНЫМИ сессиями
       (это имитирует два независимых HTTP-запроса)
       
    2. Запустить два параллельных вызова pay_order_unsafe():
       
       async def payment_attempt_1():
           service1 = PaymentService(session1)
           return await service1.pay_order_unsafe(order_id)
           
       async def payment_attempt_2():
           service2 = PaymentService(session2)
           return await service2.pay_order_unsafe(order_id)
           
       results = await asyncio.gather(
           payment_attempt_1(),
           payment_attempt_2(),
           return_exceptions=True
       )
       
    3. Проверить историю оплат:
       
       service = PaymentService(session)
       history = await service.get_payment_history(order_id)
       
       # ОЖИДАЕМ ДВЕ ЗАПИСИ 'paid' - это и есть проблема!
       assert len(history) == 2, "Ожидалось 2 записи об оплате (RACE CONDITION!)"
       
    4. Вывести информацию о проблеме:
       
       print(f"⚠️ RACE CONDITION DETECTED!")
       print(f"Order {order_id} was paid TWICE:")
       for record in history:
           print(f"  - {record['changed_at']}: status = {record['status']}")
    """
    # TODO: Реализовать тест, демонстрирующий race condition
    order_id = test_order  
   
    async def payment_attempt_1():
        async with AsyncSession(engine) as session1:
            service1 = PaymentService(session1)
            return await service1.pay_order_unsafe(order_id)

    async def payment_attempt_2():
        async with AsyncSession(engine) as session2:
            service2 = PaymentService(session2)
            return await service2.pay_order_unsafe(order_id)
        
    results = await asyncio.gather(
        payment_attempt_1(),
        payment_attempt_2(),
        return_exceptions=True,
    )

    for i, result in enumerate(results, start=1):
        if isinstance(result, Exception):
            print(f"Попытка {i} завершилась ошибкой: {result}")
        else:
            print(f"Попытка {i} успешна: {result}")

    async with AsyncSession(engine) as session:
        history_service = PaymentService(session)
        history = await history_service.get_payment_history(order_id)
        paid_history = [h for h in history if h['status'] == 'paid']

    assert len(history) == 2, "Ожидалось 2 записи об оплате (RACE CONDITION!)"
    print(f"⚠️ RACE CONDITION DETECTED!")
    print(f"Order {order_id} was paid TWICE:")
    for record in paid_history:
        print(f"  - {record['changed_at']}: status = {record['status']}")

@pytest.mark.asyncio
async def test_concurrent_payment_unsafe_both_succeed(test_order):  
    """
    Дополнительный тест: проверить, что ОБЕ транзакции успешно завершились.
    
    TODO: Реализовать проверку, что:
    1. Обе попытки оплаты вернули успешный результат
    2. Ни одна не выбросила исключение
    3. Обе записали в историю
    
    Это подтверждает, что проблема не в ошибках, а в race condition.
    """
    # TODO: Реализовать проверку успешности обеих транзакций

    order_id = test_order 
    
    async def payment_attempt(order_id: uuid.UUID):
        async with AsyncSession(engine) as session:
            service = PaymentService(session)
            return await service.pay_order_unsafe(order_id)
   
    results = await asyncio.gather(
        payment_attempt(order_id),
        payment_attempt(order_id),
        return_exceptions=True,
    )

    for i, result in enumerate(results, start=1):
        assert not isinstance(result, Exception), f"Попытка {i} завершилась ошибкой: {result}"
    
    error_count = sum(1 for r in results if isinstance(r, Exception))
    assert error_count == 0, f"Ожидалось 0 ошибок, получили {error_count}"
   
    async with AsyncSession(engine) as session:
        history_service = PaymentService(session)
        history = await history_service.get_payment_history(order_id)
        paid_history = [h for h in history if h['status'] == 'paid']
    
    assert len(history) == 2, f"Ожидалось 2 записи об оплате, получили {len(history)}"

    print("\n✅ ОБЕ транзакции pay_order_unsafe завершились успешно!")
    print(f"Order {order_id} has {len(history)} payment records in history:")
    for record in paid_history:
        print(f"  - {record['changed_at']}: status = {record['status']}")
    

if __name__ == "__main__":
    """
    Запуск теста:
    
    cd backend
    export PYTHONPATH=$(pwd)
    pytest app/tests/test_concurrent_payment_unsafe.py -v -s
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
    ✅ test_concurrent_payment_unsafe_demonstrates_race_condition PASSED
    
    Вывод должен показывать:
    ⚠️ RACE CONDITION DETECTED!
    Order XXX was paid TWICE:
      - 2024-XX-XX: status = paid
      - 2024-XX-XX: status = paid
    """
    pytest.main([__file__, "-v", "-s"])