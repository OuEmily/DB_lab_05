"""Доменные сущности заказа."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import (
    OrderAlreadyPaidError,
    OrderCancelledError,
    InvalidQuantityError,
    InvalidPriceError,
    InvalidAmountError,
)


# TODO: Реализовать OrderStatus (str, Enum)
# Значения: CREATED, PAID, CANCELLED, SHIPPED, COMPLETED
class OrderStatus(str, Enum):
    CREATED = 'created'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    SHIPPED = 'shipped'
    COMPLETED = 'completed'

# TODO: Реализовать OrderItem (dataclass)
# Поля: product_name, price, quantity, id, order_id
# Свойство: subtotal (price * quantity)
# Валидация: quantity > 0, price >= 0

@dataclass
class OrderItem:
    product_name: str
    price: Decimal
    quantity: int
    order_id: Optional[uuid.UUID] = None
    id: Optional[uuid.UUID] = None

    def __post_init__(self):
        if self.quantity <= 0:
            raise InvalidQuantityError(f'Проверьте количество товара, не может быть отрицательным: {self.quantity}!')
        if self.price < 0:
            raise InvalidPriceError(f'Проверьте цену товара, не может быть отрицательной: {self.price}!')
        if self.id is None:
            self.id = uuid.uuid4()

    @property
    def subtotal(self):
        return self.price * self.quantity

# TODO: Реализовать OrderStatusChange (dataclass)
# Поля: order_id, status, changed_at, id
@dataclass
class OrderStatusChange:
    order_id: Optional[uuid.UUID]
    status: OrderStatus
    changed_at: Optional[datetime] = None
    id: Optional[uuid.UUID] = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.changed_at is None:
            self.changed_at = datetime.now()
        
# TODO: Реализовать Order (dataclass)
# Поля: user_id, id, status, total_amount, created_at, items, status_history
# Методы:
#   - add_item(product_name, price, quantity) -> OrderItem
#   - pay() -> None  [КРИТИЧНО: нельзя оплатить дважды!]
#   - cancel() -> None
#   - ship() -> None
#   - complete() -> None
@dataclass
class Order:
    user_id: Optional[uuid.UUID] = None
    id: Optional[uuid.UUID] = None
    status: OrderStatus = OrderStatus.CREATED
    total_amount: Decimal = Decimal('0')
    created_at: Optional[datetime] = None
    items: List[OrderItem] = field(default_factory=list)
    status_history: List[OrderStatusChange] = field(default_factory=list)

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        self.status_history.append(OrderStatusChange(order_id=self.id, status=self.status))
    
    def pay(self):
        if self.status == OrderStatus.PAID:
            raise OrderAlreadyPaidError(f"Order {self.id} is already paid!")
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(f"Order {self.id}! is cancelled")
        self.status = OrderStatus.PAID
        self.status_history.append(OrderStatusChange(order_id=self.id, status=self.status))

    def cancel(self):
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(f'Order {self.id} is already cancelled!')
        if self.status == OrderStatus.PAID:
            raise OrderAlreadyPaidError(f"Order {self.id} is already paid!")
        self.status = OrderStatus.CANCELLED
        self.status_history.append(OrderStatusChange(order_id=self.id, status=self.status))
    
    def ship(self):
        if self.status != OrderStatus.PAID:
            raise ValueError(f"Order {self.status} must be paid before shipping!")
        if self.status == OrderStatus.SHIPPED:
            raise ValueError(f'Order {self.id} is already shipped!')
        self.status = OrderStatus.SHIPPED
        self.status_history.append(OrderStatusChange(order_id=self.id, status=self.status))
    
    def complete(self):
        if self.status != OrderStatus.SHIPPED:
            raise ValueError(f"Order {self.id} must be shipped before completion")
        if self.status == OrderStatus.COMPLETED:
            raise ValueError(f'Order {self.id} is already completed')
        self.status = OrderStatus.COMPLETED
        self.status_history.append(OrderStatusChange(order_id=self.id, status=self.status))
    
    def add_item(self, product_name: str, price: Decimal, quantity: int) -> OrderItem:
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError("Order {self.id} is already cancelled!")
        item = OrderItem(product_name=product_name, price=price, quantity=quantity, order_id=self.id)
        self.items.append(item)
        self.total_amount += item.subtotal
        if self.total_amount < 0:
            self.total_amount -= item.subtotal
            raise InvalidAmountError(f"Order total cannot be negative!")
        return item