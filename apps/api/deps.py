from collections.abc import Iterator

from fastapi import Request

from signalforge.db.repositories.signals import SignalRepository
from signalforge.db.session import session_scope


def get_signal_repository(request: Request) -> Iterator[SignalRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield SignalRepository(session)
