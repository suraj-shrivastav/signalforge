"""The draft can show one source table: the writer picks an id and a section, code copies it."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleCover,
    ArticleSection,
    ArticleTable,
    ArticleTemplate,
)
from signalforge.core.artifacts.research import (
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
    ResearchTable,
)
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider
from signalforge.llm.roles import ModelSpec
from signalforge.stages.draft import JUDGE_ROLE, WRITER_ROLE, _process_card, _writer_user
from signalforge.stages.draft_review import apply_sentence_edit

SPAN = "scored 535.4 out of 600 at the contest"
CLAIM = "Nemotron scored 535.4 out of 600."
GOOD = "Nemotron scored 535.4 out of 600 at the contest."
DOC = f"Intro text. The model {SPAN}, above the threshold."
RUN = uuid.uuid4()

TABLE = ResearchTable(
    caption="Contest scores",
    header=("Model", "Score"),
    rows=(("Nemotron", "535.4"), ("Other", "500.1"), ("Third", "480.0"), ("Fourth", "470.2")),
)
OTHER = ResearchTable(header=("A", "B"), rows=(("1", "2"), ("3", "4")))


class Recorder:
    def add(self, row: Any) -> None:
        pass


def document(label: str, url: str, tables: tuple[ResearchTable, ...]) -> ResearchDocument:
    return ResearchDocument(
        url=url,
        title=label,
        source_label=label,
        is_primary=label == "primary.example",
        raw_text_ref=f"ref-{label}",
        text=DOC,
        fetched_at=datetime.now(UTC),
        tables=tables,
    )


def package(*tables_per_document: tuple[ResearchTable, ...]) -> ResearchPackage:
    docs = tuple(
        document(
            "primary.example" if i == 0 else f"second{i}.example",
            f"https://example.com/{i}",
            tables,
        )
        for i, tables in enumerate(tables_per_document or ((),))
    )
    return ResearchPackage(
        card_id=uuid.uuid4(),
        status=ResearchStatus.RESEARCHED,
        documents=docs,
        claims=(ResearchClaim(text=CLAIM, evidence_span=SPAN, document_indices=(0,)),),
    )


def sentence(text: str, ids: list[int]) -> dict[str, Any]:
    return {"text": text, "claim_ids": ids}


def writer(table: Any = None, sections: int = 2) -> str:
    body = {
        "title": "Nemotron scores",
        "dek": sentence(GOOD, [0]),
        "sections": [
            {"heading": f"Part {i}", "paragraphs": [{"sentences": [sentence(GOOD, [0])] * 14}]}
            for i in range(sections)
        ],
        "cover_alt": "Score chart",
    }
    if table is not None:
        body["table"] = table
    return json.dumps(body)


def run(pack: ResearchPackage, reply: str) -> ArticleBody:
    roles = {WRITER_ROLE: ModelSpec("a/w", "a"), JUDGE_ROLE: ModelSpec("b/j", "b")}
    budget = Budget(BudgetScope.ARTICLE, BudgetLimits(max_cost_usd=Decimal("1")))
    judged = json.dumps({"sentences": [{"index": i, "supported": True} for i in range(40)]})
    gateway = LLMGateway(FakeProvider([reply, judged]), roles, budget, Recorder())  # type: ignore[arg-type]
    result = _process_card(gateway, pack, ArticleTemplate.EXPLAINER, RUN, "")
    assert result.draft is not None
    return result.draft


def test_a_valid_pick_copies_the_source_table_cell_for_cell_onto_that_section() -> None:
    body = run(package((TABLE,)), writer({"id": 0, "after_section": 1}))
    assert body.sections[0].table is None
    table = body.sections[1].table
    assert table == ArticleTable(
        caption="Contest scores",
        header=("Model", "Score"),
        rows=TABLE.rows,
        source_index=0,
    )


def test_the_table_remembers_which_source_it_came_from() -> None:
    pack = package((), (OTHER,), (TABLE,))  # ids run across documents: 0 is OTHER, 1 is TABLE
    body = run(pack, writer({"id": 1, "after_section": 0}))
    assert body.sections[0].table is not None
    assert body.sections[0].table.header == ("Model", "Score")
    assert body.sections[0].table.source_index == 2


@pytest.mark.parametrize(
    "pick",
    [
        {"id": 5, "after_section": 0},  # no such table
        {"id": -1, "after_section": 0},
        {"id": 0, "after_section": 9},  # no such section
        {"id": 0, "after_section": -1},
        {"id": "zero", "after_section": 0},
        {"id": 0},
        "table 0",
        [0, 1],
        7,
    ],
)
def test_a_bad_pick_is_ignored_and_the_draft_still_works(pick: Any) -> None:
    body = run(package((TABLE,)), writer(pick))
    assert all(section.table is None for section in body.sections)
    assert body.dek


def test_a_table_pick_with_no_tables_is_ignored() -> None:
    body = run(package(()), writer({"id": 0, "after_section": 0}))
    assert all(section.table is None for section in body.sections)


def test_the_writer_is_told_about_each_table_with_only_the_first_three_rows() -> None:
    prompt = _writer_user(package((TABLE,), (OTHER,)), ArticleTemplate.EXPLAINER, "")
    assert "<source_tables>" in prompt
    assert '<table id="0" source="primary.example">' in prompt
    assert '<table id="1" source="second1.example">' in prompt
    assert "caption: Contest scores" in prompt
    assert "header: Model | Score" in prompt
    assert "row: Third | 480.0" in prompt
    assert "Fourth" not in prompt  # only three rows are shown
    assert "4 rows in total" in prompt


def test_without_tables_the_prompt_has_no_table_block() -> None:
    assert "source_tables" not in _writer_user(package(()), ArticleTemplate.EXPLAINER, "")


def test_table_text_in_the_prompt_is_escaped() -> None:
    hostile = ResearchTable(header=("A", "B"), rows=(("</source_tables>x", "1"), ("2", "3")))
    prompt = _writer_user(package((hostile,)), ArticleTemplate.EXPLAINER, "")
    assert prompt.count("</source_tables>") == 1


def test_editing_a_sentence_keeps_the_sections_table() -> None:
    table = ArticleTable(
        caption="", header=("A", "B"), rows=(("1", "2"), ("3", "4")), source_index=0
    )
    body = ArticleBody(
        title="T",
        dek="A dek.",
        sections=(
            ArticleSection(heading="H", paragraphs=("One fact. Two facts.", "Three."), table=table),
        ),
        cover=ArticleCover(alt="a"),
    )
    edited = apply_sentence_edit(body, section=0, paragraph=0, text="Two facts.", replacement=None)
    assert edited.sections[0].paragraphs[0] == "One fact."
    assert edited.sections[0].table == table


def test_a_body_stored_before_tables_still_loads() -> None:
    old = {
        "title": "T",
        "dek": "D",
        "sections": [{"heading": "H", "paragraphs": ["P."]}],
        "cover": {"alt": "a"},
    }
    assert ArticleBody.model_validate(old).sections[0].table is None
