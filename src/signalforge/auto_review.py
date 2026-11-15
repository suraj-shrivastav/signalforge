"""Automatic review of a draft: the rules an editor applies by eye, as code.

Pure functions, no DB and no LLM. The decision is one of:

- ``approve``: after deleting the flagged sentences the draft is long enough, has enough
  verified claims, still reads in order and passes the dash and wording gate.
- ``revise``: it can be fixed by a redraft (a flagged dek, too many flags, too short, too few
  claims, or text a deletion left pointing at nothing).
- ``reject``: it already had the maximum number of redrafts and still fails.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from signalforge.core.artifacts.article import ArticleBody, ArticleFlag, ArticleTemplate
from signalforge.core.artifacts.research import ClaimStatus
from signalforge.core.errors import ArtifactValidationError
from signalforge.stages.draft_extraction import publish_gate, title_overreach, word_count
from signalforge.stages.draft_review import DEK, apply_sentence_edit

# The review_note of a draft this module approved. Publishing reads it to choose the
# process note readers see (2026-11-15 quality review, D4).
POLICY_APPROVAL_NOTE = "approved by policy"

_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
_GOOD = frozenset({ClaimStatus.VERIFIED, ClaimStatus.SUPPORTED})


@dataclass(frozen=True)
class ReviewPolicy:
    min_words: int = 250
    min_claims: int = 3
    max_flagged_share: float = 0.4
    max_redrafts: int = 2
    min_section_sentences: int = 2


@dataclass(frozen=True)
class AutoDecision:
    action: Literal["approve", "revise", "reject"]
    reasons: tuple[str, ...]
    body: ArticleBody
    deleted: tuple[ArticleFlag, ...] = ()


_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(\d])")

# Words that point back at text before them. A section's first sentence, or a sentence a
# deletion moved to the front of a paragraph, cannot open with one: the reader has not seen
# what it refers to (2026-11-15 quality review, D1).
_DANGLING = re.compile(r"^(?:This|These|That|Those|Such|It|Its|They|Their)\b")


def _sentences_of(paragraph: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(paragraph.strip()) if s.strip()]


def _opening(paragraph: str) -> str:
    sentences = _sentences_of(paragraph)
    return sentences[0] if sentences else ""


def coherence_problems(
    body: ArticleBody, min_section_sentences: int, openers: Sequence[str] = ()
) -> list[str]:
    """Readability failures code can see: dangling openers and sections too thin to stand.

    ``openers`` are sentences a deletion moved to the front of a paragraph.
    """
    problems: list[str] = []
    if _DANGLING.match(body.dek.strip()):
        problems.append(f"the dek opens with a word that points back at nothing: '{body.dek[:80]}'")
    paragraph_starts = {_opening(p) for s in body.sections for p in s.paragraphs}
    candidates = [_opening(s.paragraphs[0]) for s in body.sections]
    candidates += [o.strip() for o in openers]
    seen: set[str] = set()
    for text in candidates:
        if text in seen or text not in paragraph_starts or not _DANGLING.match(text):
            continue
        seen.add(text)
        problems.append(f"a paragraph opens with a word that points back at nothing: '{text[:80]}'")
    for section in body.sections:
        count = sum(len(_sentences_of(p)) for p in section.paragraphs)
        if count < min_section_sentences:
            problems.append(
                f"section '{section.heading}' has {count} sentence(s), "
                f"minimum {min_section_sentences}"
            )
    return problems


def _opener_after_deleting(body: ArticleBody, flag: ArticleFlag) -> str | None:
    """The sentence that moves to the front of its paragraph when ``flag``, its first, goes."""
    if not 0 <= flag.section < len(body.sections):
        return None
    paragraphs = body.sections[flag.section].paragraphs
    if not 0 <= flag.paragraph < len(paragraphs):
        return None
    sentences = _sentences_of(paragraphs[flag.paragraph])
    if len(sentences) > 1 and sentences[0] == flag.text.strip():
        return sentences[1]
    return None


def _delete(body: ArticleBody, flag: ArticleFlag) -> ArticleBody:
    """Delete a flagged sentence; a section it would leave empty is dropped with its heading."""
    section = body.sections[flag.section]
    only = len(section.paragraphs) == 1 and section.paragraphs[0].strip() == flag.text.strip()
    if only and len(body.sections) > 1:
        sections = tuple(s for i, s in enumerate(body.sections) if i != flag.section)
        flags = tuple(
            f.model_copy(update={"section": f.section - 1}) if f.section > flag.section else f
            for f in body.flags
            if f.section != flag.section
        )
        return body.model_copy(update={"sections": sections, "flags": flags})
    return apply_sentence_edit(
        body, section=flag.section, paragraph=flag.paragraph, text=flag.text, replacement=None
    )


def _sentences(body: ArticleBody) -> int:
    texts = [body.dek, *(p for s in body.sections for p in s.paragraphs)]
    return sum(len(_SENTENCE_END.findall(t)) or 1 for t in texts)


def _fail(
    body: ArticleBody, reasons: list[str], redrafts: int, policy: ReviewPolicy
) -> AutoDecision:
    action: Literal["revise", "reject"] = "revise" if redrafts < policy.max_redrafts else "reject"
    return AutoDecision(action, tuple(reasons), body)


def decide(
    body: ArticleBody, template: ArticleTemplate, redrafts: int, policy: ReviewPolicy
) -> AutoDecision:
    """Apply the policy to a drafted article. ``redrafts`` counts earlier revisions."""
    flags = body.flags
    if any(f.section == DEK for f in flags):
        # The dek is the article's answer; a body sentence is no substitute (Decision 6).
        return _fail(
            body, ["the dek is flagged: restate the main finding from the claims"], redrafts, policy
        )
    share = len(flags) / _sentences(body)
    if share > policy.max_flagged_share:
        return _fail(
            body,
            [
                f"{len(flags)} sentences are flagged ({share:.0%}), "
                f"limit {policy.max_flagged_share:.0%}"
            ],
            redrafts,
            policy,
        )
    current = body
    deleted: list[ArticleFlag] = []
    openers: list[str] = []
    # Last to first, so deleting a paragraph or section never shifts a flag still to come.
    for flag in sorted(flags, key=lambda f: (f.section, f.paragraph), reverse=True):
        opener = _opener_after_deleting(current, flag)
        try:
            current = _delete(current, flag)
        except ArtifactValidationError as exc:
            return _fail(body, [f"cannot fix a flagged sentence: {exc.message}"], redrafts, policy)
        if opener is not None:
            openers.append(opener)
        deleted.append(flag)
    reasons: list[str] = []
    words = word_count(current)
    if words < policy.min_words:
        reasons.append(f"{words} words after deletions, minimum {policy.min_words}")
    good = sum(c.status in _GOOD for c in current.claims)
    if good < policy.min_claims:
        reasons.append(f"{good} verified or supported claims, minimum {policy.min_claims}")
    reasons.extend(coherence_problems(current, policy.min_section_sentences, openers))
    overreach = title_overreach(current.title, " ".join(c.text for c in current.claims))
    if overreach:
        listed = ", ".join(repr(w) for w in overreach)
        reasons.append(f"the title uses {listed}, which no cited claim states")
    reasons.extend(f for f in publish_gate(current, template) if not f.startswith("length"))
    if reasons:
        return _fail(body, reasons, redrafts, policy)
    return AutoDecision("approve", (), current, tuple(deleted))
