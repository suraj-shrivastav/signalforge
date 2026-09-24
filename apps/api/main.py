"""FastAPI app factory. Run: ``uv run uvicorn --factory apps.api.main:create_app``."""

import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from apps.api.errors import REQUEST_ID_HEADER, register_error_handlers
from apps.api.routes import signals
from signalforge.core.config import Settings, get_settings
from signalforge.core.logging import configure_logging, correlation_id
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Transaction-mode connection: the API's transactions are short (ADR-0003).
        engine = create_db_engine(settings, ConnectionMode.TRANSACTION)
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="SignalForge API", lifespan=lifespan)
    app.state.settings = settings
    register_error_handlers(app)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        rid = supplied if _SAFE_REQUEST_ID.match(supplied) else str(uuid.uuid4())
        request.state.request_id = rid
        with correlation_id(rid):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(signals.router)
    return app
