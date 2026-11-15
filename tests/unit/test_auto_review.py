from signalforge.auto_review import ReviewPolicy, decide
from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleFlag,
    ArticleSection,
    ArticleTemplate,
    FlagKind,
)
from signalforge.core.artifacts.research import ClaimStatus

POLICY = ReviewPolicy(
    min_words=20,
    min_claims=2,
    max_flagged_share=0.4,
    max_redrafts=1,
    min_section_sentences=2,
    length_floor_ratio=0.0,
)
GOOD = "The sentence states a plain fact about the system."


def claim(status: ClaimStatus = ClaimStatus.VERIFIED) -> ArticleClaim:
    return ArticleClaim(text="c", evidence_span="s", document_indices=(0,), status=status)


def flag(section: int, paragraph: int, text: str) -> ArticleFlag:
    return ArticleFlag(
        section=section, paragraph=paragraph, text=text, kind=FlagKind.UNSUPPORTED, detail="d"
    )


def body(
    paragraphs: tuple[str, ...] = (f"{GOOD} {GOOD} {GOOD}", f"{GOOD} {GOOD}"),
    claims: int = 2,
    flags: tuple[ArticleFlag, ...] = (),
    dek: str = "A short dek.",
) -> ArticleBody:
    return ArticleBody(
        title="T",
        dek=dek,
        sections=(ArticleSection(heading="H", paragraphs=paragraphs),),
        claims=tuple(claim() for _ in range(claims)),
        cover=ArticleCover(alt="a"),
        flags=flags,
    )


def run(b: ArticleBody, redrafts: int = 0) -> tuple[str, tuple[str, ...]]:
    result = decide(b, ArticleTemplate.EXPLAINER, redrafts, POLICY)
    return result.action, result.reasons


def test_clean_draft_is_approved() -> None:
    assert run(body()) == ("approve", ())


def test_flagged_sentences_are_deleted_then_approved() -> None:
    bad = "A made up claim."
    b = body(paragraphs=(f"{GOOD} {bad} {GOOD} {GOOD}", f"{GOOD} {GOOD}"), flags=(flag(0, 0, bad),))
    result = decide(b, ArticleTemplate.EXPLAINER, 0, POLICY)
    assert result.action == "approve"
    assert bad not in result.body.sections[0].paragraphs[0]
    assert result.body.flags == ()
    assert [f.text for f in result.deleted] == [bad]


def test_too_many_flags_ask_for_a_revision() -> None:
    texts = [f"Bad {i}." for i in range(3)]
    b = body(paragraphs=(f"{GOOD} " + " ".join(texts),), flags=tuple(flag(0, 0, t) for t in texts))
    action, reasons = run(b)
    assert action == "revise"
    assert "flagged" in reasons[0]


def test_short_or_thin_drafts_are_sent_back() -> None:
    action, reasons = run(body(paragraphs=("Short.",), claims=1))
    assert action == "revise"
    assert any("words" in r for r in reasons)
    assert any("claims" in r for r in reasons)


def test_dash_in_text_fails_the_gate() -> None:
    action, reasons = run(body(paragraphs=(f"{GOOD} {GOOD} {GOOD}", f"{GOOD} — {GOOD}")))
    assert action == "revise"
    assert any("dash" in r for r in reasons)


def test_after_the_last_redraft_a_failing_draft_is_rejected() -> None:
    thin = body(paragraphs=("Short.",))
    assert run(thin, redrafts=0)[0] == "revise"
    assert run(thin, redrafts=1)[0] == "reject"


def test_a_section_left_empty_by_deletions_is_dropped() -> None:
    bad = "A made up claim."
    b = body(flags=(flag(1, 0, bad),)).model_copy(
        update={
            "sections": (
                ArticleSection(heading="H", paragraphs=(f"{GOOD} {GOOD} {GOOD}", f"{GOOD} {GOOD}")),
                ArticleSection(heading="Only a bad claim", paragraphs=(bad,)),
            )
        }
    )
    result = decide(b, ArticleTemplate.EXPLAINER, 0, POLICY)
    assert result.action == "approve"
    assert [s.heading for s in result.body.sections] == ["H"]
    assert result.body.flags == ()


def test_flags_in_several_paragraphs_are_all_deleted() -> None:
    first, second = "First bad claim.", "Second bad claim."
    b = body(
        paragraphs=(first, f"{GOOD} {GOOD} {GOOD}", second, f"{GOOD} {GOOD}"),
        flags=(flag(0, 0, first), flag(0, 2, second)),
    )
    result = decide(b, ArticleTemplate.EXPLAINER, 0, POLICY)
    assert result.action == "approve"
    text = " ".join(result.body.sections[0].paragraphs)
    assert first not in text
    assert second not in text


def test_a_flagged_dek_is_sent_back_not_replaced() -> None:
    b = body(dek="A bad dek.", flags=(flag(-1, -1, "A bad dek."),))
    action, reasons = run(b)
    assert action == "revise"
    assert "the dek is flagged" in reasons[0]


def test_a_section_opening_with_a_dangling_word_is_sent_back() -> None:
    b = body(paragraphs=(f"This dependence breaks in a tail. {GOOD} {GOOD}", f"{GOOD} {GOOD}"))
    action, reasons = run(b)
    assert action == "revise"
    assert any("points back at nothing" in r for r in reasons)


def test_deleting_an_opener_that_leaves_a_dangling_sentence_is_sent_back() -> None:
    bad = "The detector misses small boxes."
    b = body(
        paragraphs=(f"{GOOD} {GOOD}", f"{bad} This gap matters at night. {GOOD}"),
        flags=(flag(0, 1, bad),),
    )
    action, reasons = run(b)
    assert action == "revise"
    assert any("This gap matters at night." in r for r in reasons)


def test_a_one_sentence_section_is_sent_back() -> None:
    b = body().model_copy(
        update={
            "sections": (
                ArticleSection(heading="H", paragraphs=(f"{GOOD} {GOOD} {GOOD}",)),
                ArticleSection(heading="The problem", paragraphs=(GOOD,)),
            )
        }
    )
    action, reasons = run(b)
    assert action == "revise"
    assert any("'The problem' has 1 sentence" in r for r in reasons)


def test_a_title_with_a_strong_word_no_claim_uses_is_sent_back() -> None:
    b = body().model_copy(update={"title": "Only frontier models can investigate reliably"})
    action, reasons = run(b)
    assert action == "revise"
    assert any("'only', 'reliably'" in r for r in reasons)


def test_a_draft_below_its_template_minimum_is_sent_back() -> None:
    policy = ReviewPolicy(
        min_words=20, min_claims=2, max_flagged_share=0.4, max_redrafts=1, length_floor_ratio=1.0
    )
    result = decide(body(), ArticleTemplate.PAPER_BREAKDOWN, 0, policy)
    assert result.action == "revise"
    assert any("minimum 500 for paper_breakdown" in r for r in result.reasons)


def test_the_floor_ratio_scales_the_template_minimum() -> None:
    long = body(paragraphs=(" ".join([GOOD] * 50),))  # 450 words plus a 3-word dek
    lenient = ReviewPolicy(
        min_words=20, min_claims=2, max_flagged_share=0.4, max_redrafts=1, length_floor_ratio=0.8
    )
    strict = ReviewPolicy(
        min_words=20, min_claims=2, max_flagged_share=0.4, max_redrafts=1, length_floor_ratio=1.0
    )
    assert decide(long, ArticleTemplate.PAPER_BREAKDOWN, 0, lenient).action == "approve"
    assert decide(long, ArticleTemplate.PAPER_BREAKDOWN, 0, strict).action == "revise"
