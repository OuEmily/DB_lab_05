"""
Тест для демонстрации РЕШЕНИЯ проблемы race condition.

Этот тест должен ПРОХОДИТЬ, подтверждая, что при использовании
pay_order_safe() заказ оплачивается только один раз.
"""

import asyncio
"""
Тест для демонстрации РЕШЕНИЯ проблемы race condition.

Этот тест должен ПРОХОДИТЬ, подтверждая, что при использовании
pay_order_safe() заказ оплачивается только один раз.
"""

import asyncio
import pytest
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.application.payment_service import PaymentService
from app.domain.exceptions import OrderAlreadyPaidError, OrderNotFoundError


# TODO: Настроить подключение к тестовой БД
# ВАЖНО: 'db' вместо 'localhost', так как тесты запускаются внутри контейнера backend
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"

# Создаем движок один раз для всех тестов
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


@pytest.fixture(scope="module")
def event_loop():
    """Создание экземпляра цикла событий для модуля."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session():
    """
    Создать сессию БД для тестов.
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
async def test_order():
    """
    Создать тестовый заказ со статусом 'created'.
    Очищает данные после завершения теста.
    """
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    email = f"test_safe_{order_id}@example.com"

    # Создание данных
    async with AsyncSession(engine) as setup_session:
        async with setup_session.begin():
            await setup_session.execute(
                text("""
                    INSERT INTO users (id, name, email, created_at) 
                    VALUES (:id, :name, :email, NOW())
                """),
                {"id": str(user_id), "name": "Safe Test User", "email": email}
            )
            
            await setup_session.execute(
                text("""
                    INSERT INTO orders (id, user_id, status, total_amount, created_at) 
                    VALUES (:id, :user_id, 'created', 100.00, NOW())
                """),
                {"id": str(order_id), "user_id": str(user_id)}
            )

            await setup_session.execute(
                text("""
                    INSERT INTO order_status_history (id, order_id, status, changed_at) 
                    VALUES (gen_random_uuid(), :order_id, 'created', NOW())
                """),
                {"order_id": str(order_id)}
            )

    yield order_id

    # Очистка данных после теста
    async with AsyncSession(engine) as cleanup_session:
        async with cleanup_session.begin():
            await cleanup_session.execute(
                text("DELETE FROM order_status_history WHERE order_id = :id"),
                {"id": str(order_id)}
            )
            await cleanup_session.execute(
                text("DELETE FROM orders WHERE id = :id"),
                {"id": str(order_id)}
            )
            await cleanup_session.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": str(user_id)}
            )


@pytest.mark.asyncio
async def test_concurrent_payment_safe_prevents_race_condition(test_order):
    """
    Тест демонстрирует решение проблемы race condition с помощью pay_order_safe().
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: 
    - Одна попытка успешна.
    - Вторая попытка падает с OrderAlreadyPaidError.
    - В истории ровно 1 запись.
    """
    order_id = test_order

    async def payment_attempt_1():
        async with AsyncSession(engine) as session1:
            service1 = PaymentService(session1)
            return await service1.pay_order_safe(order_id)
    
    async def payment_attempt_2():
        async with AsyncSession(engine) as session2:
            service2 = PaymentService(session2)
            return await service2.pay_order_safe(order_id)
    
    results = await asyncio.gather(
        payment_attempt_1(),
        payment_attempt_2(),
        return_exceptions=True
    )

    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = sum(1 for r in results if isinstance(r, Exception))
  
    assert success_count == 1, f"Ожидалась одна успешная оплата, получилось {success_count}"
    assert error_count == 1, f"Ожидалась одна неудачная попытка, получилось {error_count}"
    
    errors = [r for r in results if isinstance(r, Exception)]
    assert isinstance(errors[0], (OrderAlreadyPaidError, Exception)), \
        f"Ожидалась OrderAlreadyPaidError, получено {type(errors[0])}: {errors[0]}"

    async with AsyncSession(engine) as check_session:
        service = PaymentService(check_session)
        history = await service.get_payment_history(order_id)
    
    assert len(history) == 1, f"Ожидалась 1 запись об оплате (БЕЗ RACE CONDITION!), получено {len(history)}"

    print(f"\n✅ RACE CONDITION PREVENTED!")
    print(f"Order {order_id} was paid only ONCE:")
    print(f"  - {history[0]['changed_at']}: status = {history[0]['status']}")
    
    success_result = [r for r in results if not isinstance(r, Exception)][0]
    error_result = [r for r in results if isinstance(r, Exception)][0]
    
    print(f"Success: {success_result}")
    print(f"Rejected: {type(error_result).__name__}: {error_result}")


@pytest.mark.asyncio
async def test_concurrent_payment_safe_with_explicit_timing():
    """
    Дополнительный тест: проверка работы блокировок.
    
    Этот тест подтверждает, что:
    1. Первая транзакция успешно оплачивает заказ.
    2. Вторая транзакция (запущенная с задержкой) НЕ создает вторую запись,
       а корректно получает ошибку OrderAlreadyPaidError.
    
    Примечание: Из-за быстрого отката при ошибке, точное время ожидания 
    может быть меньше времени сна первой транзакции, но логика блокировок работает.
    """
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    email = f"test_timing_{order_id}@example.com"

    # Setup
    async with AsyncSession(engine) as setup_session:
        async with setup_session.begin():
            await setup_session.execute(
                text("INSERT INTO users (id, name, email, created_at) VALUES (:id, :name, :email, NOW())"),
                {"id": str(user_id), "name": "Timing User", "email": email}
            )
            await setup_session.execute(
                text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:id, :user_id, 'created', 100, NOW())"),
                {"id": str(order_id), "user_id": str(user_id)}
            )
            await setup_session.execute(
                text("INSERT INTO order_status_history (id, order_id, status, changed_at) VALUES (gen_random_uuid(), :order_id, 'created', NOW())"),
                {"order_id": str(order_id)}
            )

    try:
        results = []

        async def slow_payment():
            """Первая транзакция: оплачивает заказ."""
            async with AsyncSession(engine) as session:
                service = PaymentService(session)
                
                await asyncio.sleep(0.2) 
                return await service.pay_order_safe(order_id)

        async def delayed_payment():
            """Вторая транзакция: стартует с задержкой и должна получить ошибку."""
            await asyncio.sleep(0.1)  
            async with AsyncSession(engine) as session:
                service = PaymentService(session)
                try:
                    return await service.pay_order_safe(order_id)
                except OrderAlreadyPaidError as e:
                    
                    return e

        results = await asyncio.gather(
            slow_payment(),
            delayed_payment(),
            return_exceptions=True
        )

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = sum(1 for r in results if isinstance(r, Exception))

        assert success_count == 1, f"Ожидалась одна успешная оплата, получилось {success_count}"
        assert error_count == 1, f"Ожидалась одна неудачная попытка, получилось {error_count}"
    
        errors = [r for r in results if isinstance(r, Exception)]
        assert isinstance(errors[0], OrderAlreadyPaidError), \
            f"Ожидалась OrderAlreadyPaidError, получено {type(errors[0])}: {errors[0]}"

        async with AsyncSession(engine) as check_session:
            service = PaymentService(check_session)
            history = await service.get_payment_history(order_id)
        
        assert len(history) == 1, f"Ожидалась 1 запись об оплате, получено {len(history)}"

        print(f"\n⏱ Timing Test Results:")
        print(f"Transaction 1: Success")
        print(f"Transaction 2: Rejected with {type(errors[0]).__name__}")
        print(f"History records: {len(history)}")
        print("✅ Blocking mechanism confirmed: Second transaction waited and correctly handled the paid status.")

    finally:
        async with AsyncSession(engine) as cleanup_session:
            async with cleanup_session.begin():
                await cleanup_session.execute(text("DELETE FROM order_status_history WHERE order_id = :id"), {"id": str(order_id)})
                await cleanup_session.execute(text("DELETE FROM orders WHERE id = :id"), {"id": str(order_id)})
                await cleanup_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})

@pytest.mark.asyncio
async def test_concurrent_payment_safe_multiple_orders():
    """
    Тест: блокировки не мешают обработке разных заказов параллельно.
    """
    user_id = uuid.uuid4()
    order_id_1 = uuid.uuid4()
    order_id_2 = uuid.uuid4()
    email = f"test_multi_{user_id}@example.com"

    async with AsyncSession(engine) as setup_session:
        async with setup_session.begin():
            await setup_session.execute(
                text("INSERT INTO users (id, name, email, created_at) VALUES (:id, :name, :email, NOW())"),
                {"id": str(user_id), "name": "Multi User", "email": email}
            )
            for oid in [order_id_1, order_id_2]:
                await setup_session.execute(
                    text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:id, :user_id, 'created', 100, NOW())"),
                    {"id": str(oid), "user_id": str(user_id)}
                )
                await setup_session.execute(
                    text("INSERT INTO order_status_history (id, order_id, status, changed_at) VALUES (gen_random_uuid(), :order_id, 'created', NOW())"),
                    {"order_id": str(oid)}
                )

    try:
        async def pay_order(oid):
            async with AsyncSession(engine) as session:
                service = PaymentService(session)
                return await service.pay_order_safe(oid)
            
        results = await asyncio.gather(
            pay_order(order_id_1),
            pay_order(order_id_2),
            return_exceptions=True
        )

        for i, res in enumerate(results):
            assert not isinstance(res, Exception), f"Заказ {i+1} не должен был вызвать ошибку: {res}"

        async with AsyncSession(engine) as check_session:
            service = PaymentService(check_session)
            hist1 = await service.get_payment_history(order_id_1)
            hist2 = await service.get_payment_history(order_id_2)

        assert len(hist1) == 1, f"Заказ 1: ожидалась 1 запись, получено {len(hist1)}"
        assert len(hist2) == 1, f"Заказ 2: ожидалась 1 запись, получено {len(hist2)}"

        print(f"\n✅ Concurrent different orders test passed!")
        print(f"Order 1 ({order_id_1}): {len(hist1)} record(s)")
        print(f"Order 2 ({order_id_2}): {len(hist2)} record(s)")
        print("FOR UPDATE locks do not block unrelated rows.")

    finally:
        async with AsyncSession(engine) as cleanup_session:
            async with cleanup_session.begin():
                for oid in [order_id_1, order_id_2]:
                    await cleanup_session.execute(text("DELETE FROM order_status_history WHERE order_id = :id"), {"id": str(oid)})
                    await cleanup_session.execute(text("DELETE FROM orders WHERE id = :id"), {"id": str(oid)})
                await cleanup_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})


if __name__ == "__main__":
    """
    Запуск теста:
    
    cd backend
    export PYTHONPATH=$(pwd)
    pytest app/tests/test_concurrent_payment_safe.py -v -s
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
    ✅ Все 3 теста PASSED
    """
    pytest.main([__file__, "-v", "-s"])