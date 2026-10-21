from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.published import PublishedArticleRepository
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


def get_article_repository(request: Request) -> Iterator[ArticleDraftRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield ArticleDraftRepository(session)


def get_published_repository(request: Request) -> Iterator[PublishedArticleRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield PublishedArticleRepository(session)
