"""FastAPI app factory. Run: ``uv run uvicorn --factory apps.api.main:create_app``."""

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from apps.api.errors import REQUEST_ID_HEADER, register_error_handlers
from apps.api.routes import agent, articles, cards, ingest, public, signals
from signalforge.core.config import Settings, get_settings
from signalforge.core.logging import configure_logging, correlation_id
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.stale_runs import sweep_stale_runs

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def resolve_request_id(supplied: str) -> str:
    """Echo a safe client id, else generate one (fullmatch: `$` allows a trailing newline)."""
    return supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Transaction-mode connection: the API's transactions are short (ADR-0003).
        engine = create_db_engine(settings, ConnectionMode.TRANSACTION)
        app.state.session_factory = create_session_factory(engine)
        # A restart kills in-flight stage threads; free their rows so cards retry (not wait).
        # Startup must never fail because of the sweep.
        try:
            with app.state.session_factory() as session:
                result = sweep_stale_runs(session, datetime.now(UTC))
            if result.stage_runs or result.research or result.drafts:
                logging.getLogger(__name__).warning("swept stale runs", extra=asdict(result))
        except SQLAlchemyError as exc:
            logging.getLogger(__name__).warning(
                "stale-run sweep failed", extra={"error": type(exc).__name__}
            )
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
        rid = resolve_request_id(supplied)
        request.state.request_id = rid
        with correlation_id(rid):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(signals.router)
    app.include_router(cards.router)
    app.include_router(articles.router)
    app.include_router(agent.router)
    app.include_router(public.router)
    if settings.ingest_endpoint_enabled:
        app.include_router(ingest.router)
    return app
