"""Temporary HTTP trigger for ingest. Registered only when the flag is on."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.deps import get_session
from signalforge.plugins.sources import SOURCE_NAMES, USER_AGENT, build_source
from signalforge.stages.ingest import IngestResult, run_ingest

router = APIRouter()

IngestRunner = Callable[[str, int], IngestResult]


class IngestOut(BaseModel):
    source: str
    fetched: int
    inserted: int
    stage_run_id: str


def get_ingest_runner(session: Annotated[Session, Depends(get_session)]) -> IngestRunner:
    def run(source: str, hours: int) -> IngestResult:
        with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
            return run_ingest(
                build_source(source, client),
                session,
                since=datetime.now(UTC) - timedelta(hours=hours),
            )

    return run


def require_token(request: Request, x_ingest_token: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.settings.ingest_token
    # Fail closed: no configured (or empty) token rejects everything.
    if expected is None or not expected.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid or missing ingest token")
    # compare_digest: constant-time; bytes so non-ASCII input cannot raise TypeError.
    supplied = (x_ingest_token or "").encode()
    if not secrets.compare_digest(supplied, expected.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing ingest token")


@router.post("/ingest/{source}", response_model=IngestOut, dependencies=[Depends(require_token)])
def ingest(
    source: str,
    runner: Annotated[IngestRunner, Depends(get_ingest_runner)],
    hours: Annotated[int, Query(ge=1, le=24 * 14)] = 24,
) -> IngestOut:
    if source not in SOURCE_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")
    result = runner(source, hours)
    return IngestOut(
        source=result.source,
        fetched=result.fetched,
        inserted=result.inserted,
        stage_run_id=str(result.stage_run_id),
    )
