import pytest

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleCover,
    ArticleFlag,
    ArticleSection,
    FlagKind,
)
from signalforge.core.errors import ArtifactValidationError
from signalforge.stages.draft_review import apply_sentence_edit


def flag(section: int, paragraph: int, text: str) -> ArticleFlag:
    return ArticleFlag(section=section, paragraph=paragraph, text=text, kind=FlagKind.NUMBER)


def body(*, flags: tuple[ArticleFlag, ...] = ()) -> ArticleBody:
    return ArticleBody(
        title="T",
        dek="A dek. Odd dek.",
        sections=(
            ArticleSection(
                heading="One",
                paragraphs=("Keep this. Fix this.", "Only bad."),
                citations=((0,), (1,)),
            ),
            ArticleSection(heading="Two", paragraphs=("Last para. Also bad.",)),
        ),
        cover=ArticleCover(alt="a"),
        flags=flags,
    )


def test_replace_clears_only_that_flag_and_fixes_dashes() -> None:
    start = body(flags=(flag(0, 0, "Fix this."), flag(1, 0, "Also bad.")))
    out = apply_sentence_edit(
        start, section=0, paragraph=0, text="Fix this.", replacement="Done — now."
    )
    assert out.sections[0].paragraphs[0] == "Keep this. Done, now."
    assert [f.text for f in out.flags] == ["Also bad."]
    assert out.sections[0].citations == ((0,), (1,))


def test_deleting_the_last_sentence_removes_the_paragraph_and_shifts_flags() -> None:
    start = body(flags=(flag(0, 1, "Only bad."), flag(0, 0, "Fix this.")))
    out = apply_sentence_edit(start, section=0, paragraph=1, text="Only bad.", replacement=None)
    assert out.sections[0].paragraphs == ("Keep this. Fix this.",)
    assert out.sections[0].citations == ((0,),)
    assert [f.text for f in out.flags] == ["Fix this."]


def test_deleting_inside_a_paragraph_keeps_the_rest() -> None:
    out = apply_sentence_edit(body(), section=1, paragraph=0, text="Also bad.", replacement=None)
    assert out.sections[1].paragraphs == ("Last para.",)


def test_dek_can_be_replaced_not_deleted() -> None:
    out = apply_sentence_edit(
        body(), section=-1, paragraph=-1, text="Odd dek.", replacement="Fine."
    )
    assert out.dek == "A dek. Fine."
    with pytest.raises(ArtifactValidationError):
        apply_sentence_edit(body(), section=-1, paragraph=-1, text="Odd dek.", replacement=None)


@pytest.mark.parametrize(
    ("section", "paragraph", "text", "replacement"),
    [
        (5, 0, "x", "y"),
        (0, 9, "x", "y"),
        (0, 0, "Not here.", "y"),
        (0, 0, "Fix this.", "   "),
        (1, 0, "Last para. Also bad.", None),  # would empty the section's only paragraph
    ],
)
def test_invalid_edits_raise(
    section: int, paragraph: int, text: str, replacement: str | None
) -> None:
    with pytest.raises(ArtifactValidationError):
        apply_sentence_edit(
            body(), section=section, paragraph=paragraph, text=text, replacement=replacement
        )
