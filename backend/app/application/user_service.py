"""Сервис для работы с пользователями."""

import uuid
from typing import Optional, List

from app.domain.user import User
from app.domain.exceptions import EmailAlreadyExistsError, UserNotFoundError


class UserService:
    """Сервис для операций с пользователями."""

    def __init__(self, repo):
        self.repo = repo

    # TODO: Реализовать register(email, name) -> User
    # 1. Проверить что email не занят
    # 2. Создать User
    # 3. Сохранить через repo.save()
    async def register(self, email: str, name: str = "") -> User:
        user_email_exists = await self.repo.find_by_email(email)
        if user_email_exists:
            raise EmailAlreadyExistsError(f"User with such email {email}, already exists!")
        user = User(email=email, name=name)
        await self.repo.save(user)
        return user

    # TODO: Реализовать get_by_id(user_id) -> User
    async def get_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User with ID {user_id} was not found!")
        return user

    # TODO: Реализовать get_by_email(email) -> Optional[User]
    async def get_by_email(self, email: str) -> Optional[User]:
        user = await self.repo.find_by_email(email)
        if not user:
            raise UserNotFoundError(f"User with such email {email}, does not exists!")
        return user

    # TODO: Реализовать list_users() -> List[User]
    async def list_users(self) -> List[User]:
        return await self.repo.find_all()