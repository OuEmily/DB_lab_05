"""Реализация репозиториев с использованием SQLAlchemy."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User
from app.domain.order import Order, OrderItem, OrderStatus, OrderStatusChange


class UserRepository:
    """Репозиторий для User."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # TODO: Реализовать save(user: User) -> None
    # Используйте INSERT ... ON CONFLICT DO UPDATE
    async def save(self, user: User) -> None:
        query = text("""
                      INSERT INTO users (id, email, name, created_at)
                      VALUES (:id, :email, :name, :created_at)
                      ON CONFLICT (id) DO UPDATE
                      SET email = EXCLUDED.email, name = EXCLUDED.name, created_at = EXCLUDED.created_at
                    """)
        await self.session.execute(query, {"id": user.id,"email": user.email, "name": user.name, 'created_at': user.created_at})
        await self.session.commit()

    # TODO: Реализовать find_by_id(user_id: UUID) -> Optional[User]
    async def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        query = text("""
                      SELECT * FROM users
                      WHERE id = :id                    
                    """)
        result = await self.session.execute(query, {"id": user_id})
        row = result.fetchone()
        if not row:
            return None
        
        return User(id=row.id, email=row.email, name=row.name, created_at=row.created_at)


    # TODO: Реализовать find_by_email(email: str) -> Optional[User]
    async def find_by_email(self, email: str) -> Optional[User]:
        query = text("""
                      SELECT * FROM users
                      WHERE email = :email                    
                    """)
        result = await self.session.execute(query, {"email": email})
        row = result.fetchone()
        if not row:
            return None
        
        return User(id=row.id, email=row.email, name=row.name, created_at=row.created_at)

    # TODO: Реализовать find_all() -> List[User]
    async def find_all(self) -> List[User]:
        query = text("""
                      SELECT id, email, name, created_at FROM users                    
                    """)
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [User(id=row.id, email=row.email, name=row.name, created_at=row.created_at) for row in rows]

class OrderRepository:
    """Репозиторий для Order."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # TODO: Реализовать save(order: Order) -> None
    # Сохранить заказ, товары и историю статусов
    async def save(self, order: Order) -> None:
        query_order = text("""
                     INSERT INTO orders (id, user_id, status, total_amount, created_at)
                     VALUES (:id, :user_id, :status, :total_amount, :created_at)
                     ON CONFLICT (id) DO UPDATE
                     SET status = EXCLUDED.status, total_amount = EXCLUDED.total_amount
                    """)
        await self.session.execute(query_order, {"id": order.id, "user_id": order.user_id,
                                                "status": order.status.value, 'total_amount': float(order.total_amount),
                                                "created_at" : order.created_at})
        
        query_item = text(""" 
                          INSERT INTO orders_items (id, order_id, product_name, price, quantity)
                          VALUES (:id, :order_id, :product_name, :price, :quantity)
                          ON CONFLICT (id) DO NOTHING
                    """)
        for item in order.items:
            await self.session.execute(query_item, {"id": item.id, "order_id": order.id,
                                                    "product_name": item.product_name,
                                                    "price": float(item.price), "quantity": item.quantity})
            
        query_history = text("""
                              INSERT INTO order_status_history (id, order_id, status, changed_at)
                              VALUES (:id, :order_id, :status, :changed_at)
                              ON CONFLICT (id) DO NOTHING
                            """)
        for stat in order.status_history:
            await self.session.execute(query_history, {"id": stat.id, "order_id": order.id,
                                                       "status": stat.status.value, 
                                                       "changed_at": stat.changed_at})
        await self.session.commit()

    # TODO: Реализовать find_by_id(order_id: UUID) -> Optional[Order]
    # Загрузить заказ со всеми товарами и историей
    # Используйте object.__new__(Order) чтобы избежать __post_init__
    async def find_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        query_order = text("""
                            SELECT id, user_id, status, total_amount, created_at
                            FROM orders
                            WHERE id = :ids
                        """)
        result = await self.session.execute(query_order, {"id": order_id})
        row = result.fetchone()

        if not row:
            return None
        
        query_items = text("""
                            SELECT id, product_name, price, quantity, order_id 
                            FROM order_items 
                            WHERE order_id = :id
                        """)
        result_items = await self.session.execute(query_items, {"id": order_id})
        items_rows = result_items.fetchall()

        items = [OrderItem(id=r.id, product_name=r.product_name, price=Decimal(str(r.price)), quantity=r.quantity, order_id=r.order_id) for r in items_rows]

        query_history = text("""
                              SELECT id, order_id, status, changed_at 
                              FROM order_status_history 
                              WHERE order_id = :id
                              ORDER BY changed_at ASC
                            """)
        result_history = await self.session.execute(query_history, {"id": order_id})
        history_rows = result_history.fetchall()

        status_history = [OrderStatusChange(id=r.id, order_id=r.order_id, status=OrderStatus(r.status), changed_at=r.changed_at) for r in history_rows]

        order = object.__new__(Order)
        order.id = row.id
        order.user_id = row.user_id
        order.status = OrderStatus(row.status) 
        order.total_amount = Decimal(str(row.total_amount)) 
        order.created_at = row.created_at
        order.items = items
        order.status_history = status_history

        return order

    # TODO: Реализовать find_by_user(user_id: UUID) -> List[Order]
    async def find_by_user(self, user_id: uuid.UUID) -> List[Order]:
        query_orders = text("""
                            SELECT id, user_id, status, total_amount, created_at
                            FROM orders
                            WHERE user_id = :user_id
                            """)
        result = await self.session.execute(query_orders, {"user_id": user_id})
        order_rows = result.fetchall() 

        all_orders = [] 

        for row in order_rows:
            query_items = text("""
                                SELECT id, product_name, price, quantity, order_id 
                                FROM order_items 
                                WHERE order_id = :id
                            """)
            res_items = await self.session.execute(query_items, {"id": row.id})
            items = [OrderItem(id=r.id, product_name=r.product_name, price=Decimal(str(r.price)), 
                               quantity=r.quantity, order_id=r.order_id) for r in res_items.fetchall()]

            query_history = text("""
                                 SELECT id, order_id, status, changed_at 
                                 FROM order_status_history 
                                 WHERE order_id = :id
                                 ORDER BY changed_at ASC
                                """)
            res_hist = await self.session.execute(query_history, {"id": row.id})
            status_history = [OrderStatusChange(id=r.id, order_id=r.order_id, status=OrderStatus(r.status),
                                                 changed_at=r.changed_at) for r in res_hist.fetchall()]

            order = object.__new__(Order)
            order.id = row.id
            order.user_id = row.user_id
            order.status = OrderStatus(row.status)
            order.total_amount = Decimal(str(row.total_amount))
            order.created_at = row.created_at
            order.items = items
            order.status_history = status_history
           
            all_orders.append(order)

        return all_orders
    
    # TODO: Реализовать find_all() -> List[Order]
    async def find_all(self) -> List[Order]:
        query_orders = text("""
                            SELECT id, user_id, status, total_amount, created_at
                            FROM orders
                            """)
        result = await self.session.execute(query_orders)
        order_rows = result.fetchall() 

        all_orders = [] 

        for row in order_rows:
            query_items = text("""
                                SELECT id, product_name, price, quantity, order_id 
                                FROM order_items 
                                WHERE order_id = :id
                            """)
            res_items = await self.session.execute(query_items, {"id": row.id})
            items = [OrderItem(id=r.id, product_name=r.product_name, price=Decimal(str(r.price)), 
                               quantity=r.quantity, order_id=r.order_id) for r in res_items.fetchall()]

            query_history = text("""
                                 SELECT id, order_id, status, changed_at 
                                 FROM order_status_history 
                                 WHERE order_id = :id
                                 ORDER BY changed_at ASC
                                """)
            res_hist = await self.session.execute(query_history, {"id": row.id})
            status_history = [OrderStatusChange(id=r.id, order_id=r.order_id, status=OrderStatus(r.status),
                                                 changed_at=r.changed_at) for r in res_hist.fetchall()]

            order = object.__new__(Order)
            order.id = row.id
            order.user_id = row.user_id
            order.status = OrderStatus(row.status)
            order.total_amount = Decimal(str(row.total_amount))
            order.created_at = row.created_at
            order.items = items
            order.status_history = status_history
           
            all_orders.append(order)

        return all_orders