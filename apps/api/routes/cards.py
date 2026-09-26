"""Card queue (open read) and editor decisions (key-protected write)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from apps.api.deps import get_card_repository
from apps.api.schemas import CardOut, DecisionIn, DecisionOut, QueueSignalOut
from signalforge.core.errors import EditorKeyNotConfiguredError
from signalforge.db.repositories.cards import CardRepository, QueueItem

router = APIRouter()


def require_editor_key(
    request: Request, x_editor_key: Annotated[str | None, Header()] = None
) -> None:
    expected = request.app.state.settings.editor_api_key
    # Fail closed: an unset or empty key never accepts writes.
    if expected is None or not expected.get_secret_value():
        raise EditorKeyNotConfiguredError("editor key not configured")
    # Bytes so non-ASCII input cannot raise TypeError; same body for missing and wrong.
    supplied = (x_editor_key or "").encode()
    if not secrets.compare_digest(supplied, expected.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing editor key")


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
        status=item.status,
        created_at=c.created_at,
    )


@router.get("/cards/queue", response_model=list[CardOut])
def card_queue(
    repo: Annotated[CardRepository, Depends(get_card_repository)],
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> list[CardOut]:
    since = datetime.now(UTC) - timedelta(days=days)
    return [_card_out(i) for i in repo.queue(limit=limit, since=since)]


@router.post(
    "/cards/{card_id}/decision",
    response_model=DecisionOut,
    status_code=201,
    dependencies=[Depends(require_editor_key)],
)
def add_decision(
    card_id: UUID,
    body: DecisionIn,
    repo: Annotated[CardRepository, Depends(get_card_repository)],
) -> DecisionOut:
    if not repo.exists(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    row = repo.add_decision(card_id, body.decision, body.reason_tags, body.note, body.decision_ms)
    return DecisionOut(
        id=row.id,
        card_id=row.topic_card_id,
        decision=row.decision,
        reason_tags=list(row.reason_tags),
        note=row.note,
        decision_ms=row.decision_ms,
        decided_at=row.decided_at,
    )
