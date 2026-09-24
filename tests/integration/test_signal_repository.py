from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration

BASE = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def signal(n: int, *, source: str = "hackernews") -> RawSignal:
    return RawSignal(
        source=source,
        source_type="community",
        canonical_url=f"https://example.com/{n}",
        title=f"Title {n}",
        published_at=BASE + timedelta(minutes=n),
    )


def test_insert_new_is_idempotent(db_session: Session) -> None:
    repo = SignalRepository(db_session)
    batch = [signal(1), signal(2)]
    assert repo.insert_new(batch) == 2
    assert repo.insert_new(batch) == 0


def test_duplicate_urls_inside_one_batch_insert_once(db_session: Session) -> None:
    assert SignalRepository(db_session).insert_new([signal(1), signal(1)]) == 1


def test_empty_batch_inserts_nothing(db_session: Session) -> None:
    assert SignalRepository(db_session).insert_new([]) == 0


def test_list_is_newest_first_and_pages_without_gaps_or_repeats(db_session: Session) -> None:
    repo = SignalRepository(db_session)
    repo.insert_new([signal(n) for n in range(1, 6)])

    first = repo.list_page(limit=2)
    assert [s.title for s in first.items] == ["Title 5", "Title 4"]
    assert first.next_cursor is not None

    second = repo.list_page(limit=2, cursor=first.next_cursor)
    assert [s.title for s in second.items] == ["Title 3", "Title 2"]

    last = repo.list_page(limit=2, cursor=second.next_cursor)
    assert [s.title for s in last.items] == ["Title 1"]
    assert last.next_cursor is None


def test_list_filters_by_source(db_session: Session) -> None:
    repo = SignalRepository(db_session)
    repo.insert_new([signal(1), signal(2, source="rss")])
    assert [s.source for s in repo.list_page(limit=10, source="rss").items] == ["rss"]


def test_garbage_cursor_is_a_validation_error(db_session: Session) -> None:
    with pytest.raises(ArtifactValidationError):
        SignalRepository(db_session).list_page(limit=5, cursor="not-a-cursor")
