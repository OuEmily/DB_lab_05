"""Доменная сущность пользователя."""

import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import re
from .exceptions import InvalidEmailError


# TODO: Реализовать класс User
# - Использовать @dataclass
# - Поля: email, name, id, created_at
# - Реализовать валидацию email в __post_init__
# - Regex: r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

@dataclass
class User:
    email: str
    name: str = ""
    id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        reg = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(reg, self.email):
            raise InvalidEmailError("Введите корректный email адрес!")

