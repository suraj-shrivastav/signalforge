import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.models.signals import Signal


@dataclass(frozen=True)
class SignalPage:
    items: list[Signal]
    next_cursor: str | None


def _encode_cursor(signal: Signal) -> str:
    raw = f"{signal.published_at.isoformat()}|{signal.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        published_at, signal_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(published_at), uuid.UUID(signal_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ArtifactValidationError("Invalid cursor") from exc


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_new(self, signals: Sequence[RawSignal]) -> int:
        """Insert signals with an unseen canonical URL and return how many were new.

        Signals are immutable, so a known URL is skipped, not updated. That makes
        re-running an ingest safe.
        """
        if not signals:
            return 0
        rows = [
            {
                "id": s.id,
                "schema_version": s.schema_version,
                "source": s.source,
                "source_type": s.source_type,
                "canonical_url": s.canonical_url,
                "title": s.title,
                "published_at": s.published_at,
                "summary": s.summary,
                "entities": list(s.entities),
                "topics": list(s.topics),
                "metadata": s.metadata,
                "content_hash": s.content_hash,
                "produced_by": s.produced_by,
            }
            for s in signals
        ]
        statement = (
            insert(Signal)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["canonical_url"])
            .returning(Signal.id)
        )
        return len(self._session.execute(statement).all())

    def list_page(
        self, *, limit: int, cursor: str | None = None, source: str | None = None
    ) -> SignalPage:
        """Newest first. Keyset paging, so pages stay stable while new rows arrive."""
        query = select(Signal).order_by(Signal.published_at.desc(), Signal.id.desc())
        if source is not None:
            query = query.where(Signal.source == source)
        if cursor is not None:
            published_at, signal_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(Signal.published_at, Signal.id) < tuple_(published_at, signal_id)  # type: ignore[arg-type]
            )
        # One extra row tells us whether another page exists without a count query.
        rows = list(self._session.scalars(query.limit(limit + 1)))
        items = rows[:limit]
        next_cursor = _encode_cursor(items[-1]) if len(rows) > limit else None
        return SignalPage(items=items, next_cursor=next_cursor)
