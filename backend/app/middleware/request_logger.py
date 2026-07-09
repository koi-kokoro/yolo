"""Request logging middleware."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logger import get_logger

logger = get_logger(__name__)

SKIP_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/health",
)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Log request method, path, client IP, response status and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith(SKIP_PATH_PREFIXES):
            return await call_next(request)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        client_ip = request.client.host if request.client else "unknown"

        logger.info(
            "request method=%s path=%s client_ip=%s status_code=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            client_ip,
            response.status_code,
            duration_ms,
        )
        return response
