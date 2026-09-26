"""One consistent error shape for every failure (standards section 2)."""

import logging
import re
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from signalforge.core.errors import (
    ArtifactValidationError,
    EditorKeyNotConfiguredError,
    RetryableError,
    SignalForgeError,
)
from signalforge.core.logging import current_correlation_id

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    # The catch-all handler runs outside the request-id middleware, after the
    # correlation contextvar is reset, so the id is read from request.state.
    rid = getattr(request.state, "request_id", None) or current_correlation_id()
    body = {"error": {"code": code, "message": message, "correlation_id": rid}}
    response = JSONResponse(body, status_code=status)
    if rid:
        response.headers[REQUEST_ID_HEADER] = rid
    return response


def _code_for(status: int) -> str:
    if status == 415:
        return "unsupported_media_type"
    return re.sub(r"\W+", "_", HTTPStatus(status).phrase.lower())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return error_response(request, 422, "validation_error", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(request, exc.status_code, _code_for(exc.status_code), str(exc.detail))

    @app.exception_handler(ArtifactValidationError)
    async def _artifact(request: Request, exc: ArtifactValidationError) -> JSONResponse:
        return error_response(request, 422, "validation_error", exc.message)

    @app.exception_handler(EditorKeyNotConfiguredError)
    async def _editor_key(request: Request, _: EditorKeyNotConfiguredError) -> JSONResponse:
        return error_response(
            request, 503, "editor_key_not_configured", "Editor writes are not configured"
        )

    @app.exception_handler(RetryableError)
    async def _retryable(request: Request, exc: RetryableError) -> JSONResponse:
        log.warning("temporary failure", extra={"error": str(exc)})
        return error_response(
            request, 503, "temporarily_unavailable", "Temporarily unavailable, retry later"
        )

    @app.exception_handler(SignalForgeError)
    async def _domain(request: Request, exc: SignalForgeError) -> JSONResponse:
        log.error("request failed", extra={"error": str(exc)})
        return error_response(request, 500, "internal_error", "Internal error")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, _: Exception) -> JSONResponse:
        # Logged once, here, at the boundary. The client gets no internals.
        log.exception(
            "unhandled error", extra={"request_id": getattr(request.state, "request_id", None)}
        )
        return error_response(request, 500, "internal_error", "Internal error")
