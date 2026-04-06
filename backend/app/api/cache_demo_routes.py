"""Cache consistency demo endpoints for LAB 05."""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import get_db
from app.infrastructure.redis_client import get_redis


router = APIRouter(prefix="/api/cache-demo", tags=["cache-demo"])


class UpdateOrderRequest(BaseModel):
    """Payload для изменения заказа в demo-сценариях."""

    new_total_amount: float


@router.get("/catalog")
async def get_catalog(use_cache: bool = True, db: AsyncSession = Depends(get_db)) -> Any:
    """
    TODO: Кэш каталога товаров в Redis.

    Требования:
    1) При use_cache=true читать/писать Redis.
    2) При cache miss грузить из БД и класть в кэш.
    3) Добавить TTL.

    Примечание:
    В текущей схеме можно строить "каталог" как агрегат по order_items.product_name.
    """
    redis = get_redis()
    cache_key = "catalog:v1"

    if use_cache:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await db.execute(text("""
        SELECT
            oi.product_name,
            count(*) AS order_lines,
            sum(oi.quantity) AS sold_qty,
            round(avg(oi.price)::numeric, 2) AS avg_price
        FROM order_items oi
        GROUP BY oi.product_name
        ORDER BY sold_qty DESC
        LIMIT 100
    """))
    catalog = [dict(row._mapping) for row in result.fetchall()]

    await redis.set(cache_key, json.dumps(catalog), ex=300)
    return catalog


@router.get("/orders/{order_id}/card")
async def get_order_card(
    order_id: uuid.UUID,
    use_cache: bool = True,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    TODO: Кэш карточки заказа в Redis.

    Требования:
    1) Ключ вида order_card:v1:{order_id}.
    2) При use_cache=true возвращать данные из кэша.
    3) При miss грузить из БД и сохранять в кэш.
    """
    redis = get_redis()
    cache_key = f"order_card:v1:{order_id}"

    if use_cache:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await db.execute(
        text("""
            SELECT id, user_id, status, total_amount, created_at
            FROM orders
            WHERE id = :id
        """),
        {"id": order_id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    order_data = dict(row._mapping)
    order_data["id"] = str(order_data["id"])
    order_data["user_id"] = str(order_data["user_id"])
    order_data["created_at"] = order_data["created_at"].isoformat()
    order_data["total_amount"] = float(order_data["total_amount"])

    await redis.set(cache_key, json.dumps(order_data), ex=300)
    return order_data


@router.post("/orders/{order_id}/mutate-without-invalidation")
async def mutate_without_invalidation(
    order_id: uuid.UUID,
    payload: UpdateOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    TODO: Намеренно сломанный сценарий консистентности.

    Нужно:
    1) Изменить заказ в БД.
    2) НЕ инвалидировать кэш.
    3) Показать, что последующий GET /orders/{id}/card может вернуть stale data.
    """
    result = await db.execute(
        text("""
            UPDATE orders
            SET total_amount = :total_amount
            WHERE id = :id
            RETURNING id
        """),
        {"id": order_id, "total_amount": payload.new_total_amount}
    )
    row = result.fetchone()
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"status": "updated_without_invalidation", "order_id": str(order_id)}


@router.post("/orders/{order_id}/mutate-with-event-invalidation")
async def mutate_with_event_invalidation(
    order_id: uuid.UUID,
    payload: UpdateOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    TODO: Починка через событийную инвалидацию.

    Нужно:
    1) Изменить заказ в БД.
    2) Сгенерировать событие OrderUpdated.
    3) Обработчик события должен инвалидировать связанные cache keys:
       - order_card:v1:{order_id}
       - catalog:v1 (если изменение влияет на каталог/агрегаты)
    """
    result = await db.execute(
        text("""
            UPDATE orders
            SET total_amount = :total_amount
            WHERE id = :id
            RETURNING id
        """),
        {"id": order_id, "total_amount": payload.new_total_amount}
    )
    row = result.fetchone()
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    redis = get_redis()
    await redis.delete(f"order_card:v1:{order_id}")
    await redis.delete("catalog:v1")

    return {"status": "updated_with_event_invalidation", "order_id": str(order_id)}