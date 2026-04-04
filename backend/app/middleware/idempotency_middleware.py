"""Idempotency middleware template for LAB 04."""

import hashlib
import json
import datetime
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db import SessionLocal


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware для идемпотентности POST-запросов оплаты.

    Идея:
    - Клиент отправляет `Idempotency-Key` в header.
    - Если запрос с таким ключом уже выполнялся для того же endpoint и payload,
      middleware возвращает кэшированный ответ (без повторного списания).
    """

    def __init__(self, app, ttl_seconds: int = 24 * 60 * 60):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        TODO: Реализовать алгоритм.

        Рекомендуемая логика:
        1) Пропускать только целевые запросы:
           - method == POST
           - path в whitelist для платежей
        2) Читать Idempotency-Key из headers.
           Если ключа нет -> обычный call_next(request)
        3) Считать request_hash (например sha256 от body).
        4) В транзакции:
           - проверить запись в idempotency_keys
           - если completed и hash совпадает -> вернуть кэш (status_code + body)
           - если key есть, но hash другой -> вернуть 409 Conflict
           - если ключа нет -> создать запись processing
        5) Выполнить downstream request через call_next.
        6) Сохранить response в idempotency_keys со статусом completed.
        7) Вернуть response клиенту.

        Дополнительно:
        - обработайте кейс конкурентных одинаковых ключей
          (уникальный индекс + retry/select existing).
        """
        idempotency_key = request.headers.get("idempotency-key")
        
        if not idempotency_key or request.method != "POST":
            return await call_next(request)

        body = await request.body()
        
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive

        request_hash = self.build_request_hash(body)
        method = request.method
        path = request.url.path

        async with SessionLocal() as session:
            stmt = text("""
                SELECT status, status_code, response_body, request_hash
                FROM idempotency_keys
                WHERE idempotency_key = :key AND request_method = :method AND request_path = :path
            """)
            result = await session.execute(stmt, {"key": idempotency_key, "method": method, "path": path})
            record = result.mappings().first()

            if record:
                if record["request_hash"] != request_hash:
                    return JSONResponse(status_code=409, content={"detail": "Idempotency key reused with different payload"})
                
                if record["status"] == "completed":
                    return JSONResponse(
                        status_code=record["status_code"],
                        content=record["response_body"],
                        headers={"X-Idempotency-Replayed": "true"}
                    )
                    
                if record["status"] == "processing":
                    return JSONResponse(status_code=409, content={"detail": "Request is already processing"})

            expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.ttl_seconds)
            try:
                insert_stmt = text("""
                    INSERT INTO idempotency_keys (idempotency_key, request_method, request_path, request_hash, status, expires_at)
                    VALUES (:key, :method, :path, :hash, 'processing', :expires_at)
                """)
                await session.execute(insert_stmt, {
                    "key": idempotency_key, "method": method, "path": path,
                    "hash": request_hash, "expires_at": expires_at
                })
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return JSONResponse(status_code=409, content={"detail": "Concurrent request conflict"})

        response = await call_next(request)

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        new_response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )

        try:
            body_obj = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError:
            body_obj = {"raw": response_body.decode("utf-8")}

        async with SessionLocal() as session:
            update_stmt = text("""
                UPDATE idempotency_keys
                SET status = 'completed', status_code = :status_code, response_body = :body
                WHERE idempotency_key = :key AND request_method = :method AND request_path = :path
            """)
            await session.execute(update_stmt, {
                "status_code": response.status_code,
                "body": self.encode_response_payload(body_obj),
                "key": idempotency_key, "method": method, "path": path
            })
            await session.commit()

        return new_response

    @staticmethod
    def build_request_hash(raw_body: bytes) -> str:
        """Стабильный хэш тела запроса для проверки reuse ключа с другим payload."""
        return hashlib.sha256(raw_body).hexdigest()

    @staticmethod
    def encode_response_payload(body_obj) -> str:
        """Сериализация response body для сохранения в idempotency_keys."""
        return json.dumps(body_obj, ensure_ascii=False)