"""Global exception handlers for FastAPI."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import JWTError

from app.core.logger import get_logger

logger = get_logger(__name__)


def _error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    content = {
        "success": False,
        "code": code,
        "message": message,
    }
    if details is not None:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        logger.warning(
            "HTTP exception: method=%s path=%s status_code=%s detail=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return _error_response(
            status_code=exc.status_code,
            code="HTTP_ERROR",
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "Validation error: method=%s path=%s errors=%s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        return _error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数校验失败",
            details=exc.errors(),
        )

    @app.exception_handler(JWTError)
    async def jwt_exception_handler(request: Request, exc: JWTError) -> JSONResponse:
        logger.warning(
            "JWT error: method=%s path=%s error=%s",
            request.method,
            request.url.path,
            exc,
        )
        return _error_response(
            status_code=401,
            code="AUTH_ERROR",
            message="无效的认证凭据",
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception: method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return _error_response(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误",
        )
