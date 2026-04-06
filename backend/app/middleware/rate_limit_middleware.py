"""Rate limiting middleware template for LAB 05."""

from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.redis_client import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting для endpoint оплаты.

    Цель:
    - защита от DDoS/шторма запросов;
    - защита от случайных повторных кликов пользователя.
    """

    def __init__(self, app, limit_per_window: int = 5, window_seconds: int = 10):
        super().__init__(app)
        self.limit_per_window = limit_per_window
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        TODO: Реализовать Redis rate limiting.

        Рекомендуемая логика:
        1) Применять только к endpoint оплаты:
           - /api/orders/{order_id}/pay
           - /api/payments/retry-demo
        2) Сформировать subject:
           - user_id (если есть), иначе client IP.
        3) Использовать Redis INCR + EXPIRE:
           - key = rate_limit:pay:{subject}
           - если counter > limit_per_window -> 429 Too Many Requests.
        4) Для прохождения запроса добавить в ответ headers:
           - X-RateLimit-Limit
           - X-RateLimit-Remaining
        """
        
        path = request.url.path
        if not (path.endswith("/pay") or path.endswith("/retry-demo")):
            return await call_next(request)

        user_id = request.headers.get("X-User-Id")
        subject = user_id if user_id else (request.client.host if request.client else "unknown")

        redis = get_redis()
        key = f"rate_limit:pay:{subject}"

        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self.window_seconds, nx=True)
            results = await pipe.execute()

        current_count = results[0]

        if current_count > self.limit_per_window:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"}
            )

        response = await call_next(request)

        remaining = max(0, self.limit_per_window - current_count)
        response.headers["X-RateLimit-Limit"] = str(self.limit_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response