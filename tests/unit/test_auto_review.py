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

POLICY = ReviewPolicy(min_words=20, min_claims=2, max_flagged_share=0.4, max_redrafts=1)
GOOD = "This sentence states a plain fact about the system."


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


def test_flagged_dek_is_replaced_by_the_first_unflagged_body_sentence() -> None:
    b = body(dek="A bad dek.", flags=(flag(-1, -1, "A bad dek."),))
    result = decide(b, ArticleTemplate.EXPLAINER, 0, POLICY)
    assert result.action == "approve"
    assert result.body.dek == GOOD
    assert result.new_dek == GOOD
    assert result.body.sections[0].paragraphs[0].count(GOOD) == 2  # moved out of the lead
    assert result.body.flags == ()


def test_flagged_dek_without_a_usable_lead_is_revised() -> None:
    lead = "A lead."
    b = body(
        paragraphs=(lead, f"{GOOD} {GOOD}"),
        dek="A bad dek.",
        flags=(flag(-1, -1, "A bad dek."), flag(0, 0, lead)),
    )
    loose = ReviewPolicy(min_words=20, min_claims=2, max_flagged_share=0.9, max_redrafts=1)
    result = decide(b, ArticleTemplate.EXPLAINER, 0, loose)
    assert result.action == "revise"
    assert "no lead sentence" in result.reasons[0]


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
