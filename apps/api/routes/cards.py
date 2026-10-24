"""Card queue (open read) and editor decisions (key-protected write)."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from apps.api.auto_pipeline import run_after_accept
from apps.api.deps import get_card_repository
from apps.api.schemas import CardOut, DecisionIn, DecisionOut, QueueSignalOut
from signalforge.core.errors import EditorKeyNotConfiguredError
from signalforge.db.repositories.cards import CardRepository, QueueItem
from signalforge.stages.cards import PROMPT_VERSION

router = APIRouter()
log = logging.getLogger(__name__)


def require_editor_key(
    request: Request, x_editor_key: Annotated[str | None, Header()] = None
) -> None:
    """Accept the editor key or the agent key; record which one in request.state.actor."""
    settings = request.app.state.settings
    keys = {
        actor: key.get_secret_value()
        for actor, key in (("editor", settings.editor_api_key), ("agent", settings.agent_api_key))
        if key is not None and key.get_secret_value()
    }
    # Fail closed: with no key configured nothing is accepted.
    if not keys:
        log.warning("editor key not configured; refusing decision write")
        raise EditorKeyNotConfiguredError("editor key not configured")
    # Bytes so non-ASCII input cannot raise TypeError; same body for missing and wrong.
    supplied = (x_editor_key or "").encode()
    for actor, key in keys.items():
        if secrets.compare_digest(supplied, key.encode()):
            request.state.actor = actor
            return
    raise HTTPException(status_code=401, detail="Invalid or missing editor key")


async def decision_body(request: Request) -> DecisionIn:
    """Parsed after auth (dependency order), so unauthenticated callers never see 422s."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != "application/json" and not (
        media.startswith("application/") and media.endswith("+json")
    ):
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")
    try:
        return DecisionIn.model_validate(await request.json())
    except ValidationError as exc:
        errors = [
            {"loc": ("body", *e["loc"]), "msg": e["msg"]}
            for e in exc.errors(include_url=False, include_context=False)
        ]
        raise RequestValidationError(errors) from exc
    except ValueError as exc:
        raise RequestValidationError([{"loc": ("body",), "msg": "invalid JSON"}]) from exc


def _card_out(item: QueueItem) -> CardOut:
    c = item.card
    return CardOut(
        id=c.id,
        schema_version=c.schema_version,
        what_happened=c.what_happened,
        why_it_matters=c.why_it_matters,
        novelty=c.novelty,
        signal_strength=c.signal_strength,
        coverage_gap=c.coverage_gap,
        suggested_angle=c.suggested_angle,
        format=c.format,
        evergreen_score=c.evergreen_score,
        confidence=c.confidence,
        risk_flags=list(c.risk_flags),
        prompt_version=c.prompt_version,
        model=c.model,
        signal=QueueSignalOut(
            id=c.signal_id,
            title=item.signal_title,
            source=item.source,
            canonical_url=item.canonical_url,
        ),
        score=c.score,
        wildcard=item.wildcard,
        status=cast(Any, item.status),
        created_at=c.created_at,
    )


@router.get("/cards/queue", response_model=list[CardOut])
def card_queue(
    repo: Annotated[CardRepository, Depends(get_card_repository)],
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> list[CardOut]:
    since = datetime.now(UTC) - timedelta(days=days)
    return [
        _card_out(i)
        for i in repo.queue(
            prompt_version=PROMPT_VERSION,
            limit=limit,
            wildcard_slots=min(2, limit // 2),
            since=since,
        )
    ]


@router.post(
    "/cards/{card_id}/decision",
    response_model=DecisionOut,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DecisionIn.model_json_schema()}},
        }
    },
    dependencies=[Depends(require_editor_key)],
)
def add_decision(
    card_id: UUID,
    body: Annotated[DecisionIn, Depends(decision_body)],
    request: Request,
    background: BackgroundTasks,
    # scope="function": commit runs before the response is sent, so a failed commit is a 500.
    repo: Annotated[CardRepository, Depends(get_card_repository, scope="function")],
) -> DecisionOut:
    if not repo.exists(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    try:
        row = repo.add_decision(
            card_id, body.decision, body.reason_tags, body.note, body.decision_ms
        )
    except IntegrityError as exc:  # card deleted between exists() and insert
        raise HTTPException(status_code=404, detail="Card not found") from exc
    settings = request.app.state.settings
    if body.decision == "accepted" and settings.auto_pipeline_on_accept:
        background.add_task(run_after_accept, settings)
    return DecisionOut(
        id=row.id,
        card_id=row.topic_card_id,
        decision=cast(Any, row.decision),
        reason_tags=list(row.reason_tags),
        note=row.note,
        decision_ms=row.decision_ms,
        decided_at=row.decided_at,
    )
