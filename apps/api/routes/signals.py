from typing import Annotated

from fastapi import APIRouter, Depends, Query

from apps.api.deps import get_signal_repository
from apps.api.schemas import SignalListOut, SignalOut
from signalforge.db.repositories.signals import SignalRepository

router = APIRouter()


@router.get("/signals", response_model=SignalListOut)
def list_signals(
    repo: Annotated[SignalRepository, Depends(get_signal_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    source: str | None = None,
) -> SignalListOut:
    page = repo.list_page(limit=limit, cursor=cursor, source=source)
    return SignalListOut(
        items=[SignalOut.from_row(row) for row in page.items], next_cursor=page.next_cursor
    )
