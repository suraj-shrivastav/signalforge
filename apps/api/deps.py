from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.signals import SignalRepository
from signalforge.db.session import session_scope


def get_signal_repository(request: Request) -> Iterator[SignalRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield SignalRepository(session)


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


def get_card_repository(request: Request) -> Iterator[CardRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield CardRepository(session)
