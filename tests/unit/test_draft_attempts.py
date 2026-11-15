from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from signalforge.core.artifacts.article import ArticleDraft, ArticleTemplate, DraftStatus
from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.pipeline_state import MAX_DRAFT_ATTEMPTS


def test_the_cap_is_two() -> None:
    assert MAX_DRAFT_ATTEMPTS == 2


def test_attempts_column_defaults_to_zero_and_is_not_null() -> None:
    column = ArticleDraftRow.__table__.c.attempts
    assert not column.nullable
    assert column.default.arg == 0
    assert str(column.server_default.arg) == "0"


def test_insert_counts_each_attempt() -> None:
    seen: list[Any] = []

    def execute(statement: Any) -> SimpleNamespace:
        seen.append(statement)
        return SimpleNamespace(first=lambda: (1,))

    draft = ArticleDraft(
        card_id=uuid4(), status=DraftStatus.FAILED, template=ArticleTemplate.NEWS_BRIEF
    )
    ArticleDraftRepository(SimpleNamespace(execute=execute)).insert(  # type: ignore[arg-type]
        draft, cost_usd=Decimal("0"), calls=0, tokens=0
    )
    compiled = seen[0].compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    sql = str(compiled)
    assert "attempts = (article_drafts.attempts + " in sql
    assert 1 in compiled.params.values()  # first insert stores attempts = 1
    assert "article_drafts.status =" in sql  # drafted rows are still never replaced


def test_exhausted_drafts_are_not_returned_when_retrying() -> None:
    seen: list[Any] = []

    def execute(query: Any) -> SimpleNamespace:
        seen.append(query)
        return SimpleNamespace(all=lambda: [])

    ArticleDraftRepository(SimpleNamespace(execute=execute)).list_researched_undrafted(  # type: ignore[arg-type]
        1, retry_failed=True
    )
    assert "article_drafts.attempts >=" in str(seen[0].compile())


def test_a_failed_redraft_is_logged_and_keeps_the_revise() -> None:
    flushed: list[bool] = []
    row = SimpleNamespace(
        review_status="revise", review_note="Lead with the margin", review_log=[{"type": "review"}]
    )
    repo = ArticleDraftRepository(SimpleNamespace(flush=lambda: flushed.append(True)))  # type: ignore[arg-type]
    repo.record_failed_revision(row, "ProviderRejectedError: status=402")  # type: ignore[arg-type]
    event = row.review_log[-1]
    assert (event["type"], event["note"], event["error"]) == (
        "redraft_failed",
        "Lead with the margin",
        "ProviderRejectedError: status=402",
    )
    assert "at" in event
    assert row.review_status == "revise"
    assert flushed == [True]


def test_revisions_skip_cards_that_are_no_longer_accepted() -> None:
    seen: list[Any] = []

    def execute(query: Any) -> SimpleNamespace:
        seen.append(query)
        return SimpleNamespace(all=lambda: [])

    ArticleDraftRepository(SimpleNamespace(execute=execute)).list_revisions(5)  # type: ignore[arg-type]
    sql = str(seen[0].compile())
    assert "editor_decisions" in sql
    assert "decision =" in sql
