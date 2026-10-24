"""Automatic review of a draft: the rules an editor applies by eye, as code.

Pure functions, no DB and no LLM. The decision is one of:

- ``approve``: after deleting the flagged sentences the draft is long enough, has enough
  verified claims and passes the dash and wording gate.
- ``revise``: it can be fixed by a redraft (too many flags, too short, too few claims).
- ``reject``: it already had the maximum number of redrafts and still fails.
"""

import re
from dataclasses import dataclass
from typing import Literal

from signalforge.core.artifacts.article import ArticleBody, ArticleFlag, ArticleTemplate
from signalforge.core.artifacts.research import ClaimStatus
from signalforge.core.errors import ArtifactValidationError
from signalforge.stages.draft_extraction import publish_gate, word_count
from signalforge.stages.draft_review import DEK, apply_sentence_edit

_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
_GOOD = frozenset({ClaimStatus.VERIFIED, ClaimStatus.SUPPORTED})


@dataclass(frozen=True)
class ReviewPolicy:
    min_words: int = 250
    min_claims: int = 3
    max_flagged_share: float = 0.4
    max_redrafts: int = 2


@dataclass(frozen=True)
class AutoDecision:
    action: Literal["approve", "revise", "reject"]
    reasons: tuple[str, ...]
    body: ArticleBody
    deleted: tuple[ArticleFlag, ...] = ()
    new_dek: str | None = None


_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(\d])")
_MAX_DEK_CHARS = 280


def _lead_sentence(body: ArticleBody) -> str | None:
    """First sentence of the first paragraph that is not flagged and is short enough for a dek."""
    flagged = {f.text for f in body.flags}
    for sentence in _SPLIT.split(body.sections[0].paragraphs[0]):
        text = sentence.strip()
        if text and text not in flagged and len(text) <= _MAX_DEK_CHARS:
            return text
    return None


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
    new_dek: str | None = None
    for flag in flags:
        try:
            if flag.section == DEK:
                # A dek cannot be deleted: use the article's first unflagged sentence instead.
                lead = _lead_sentence(body)
                if lead is None:
                    return _fail(
                        body, ["the dek is flagged and no lead sentence fits"], redrafts, policy
                    )
                current = apply_sentence_edit(
                    current, section=DEK, paragraph=0, text=flag.text, replacement=lead
                )
                new_dek = lead
                if len(_SPLIT.split(current.sections[0].paragraphs[0])) > 1:
                    current = apply_sentence_edit(
                        current, section=0, paragraph=0, text=lead, replacement=None
                    )
            else:
                current = apply_sentence_edit(
                    current,
                    section=flag.section,
                    paragraph=flag.paragraph,
                    text=flag.text,
                    replacement=None,
                )
        except ArtifactValidationError as exc:
            return _fail(body, [f"cannot fix a flagged sentence: {exc.message}"], redrafts, policy)
        deleted.append(flag)
    reasons: list[str] = []
    words = word_count(current)
    if words < policy.min_words:
        reasons.append(f"{words} words after deletions, minimum {policy.min_words}")
    good = sum(c.status in _GOOD for c in current.claims)
    if good < policy.min_claims:
        reasons.append(f"{good} verified or supported claims, minimum {policy.min_claims}")
    reasons.extend(f for f in publish_gate(current, template) if not f.startswith("length"))
    if reasons:
        return _fail(body, reasons, redrafts, policy)
    return AutoDecision("approve", (), current, tuple(deleted), new_dek)
