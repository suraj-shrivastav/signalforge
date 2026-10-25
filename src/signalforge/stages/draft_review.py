"""Editor edits to a draft's flagged sentences. Pure functions: no DB, no LLM.

An edit replaces or deletes one sentence inside one paragraph and clears the flag on it. The
editor owns the new text, so it is not re-checked for grounding; the repository logs it.
"""

from signalforge.core.artifacts.article import ArticleBody, ArticleSection
from signalforge.core.errors import ArtifactValidationError
from signalforge.stages.draft_extraction import fix_dashes

DEK = -1


def _squash(text: str) -> str:
    return " ".join(text.split())


def apply_sentence_edit(
    body: ArticleBody, *, section: int, paragraph: int, text: str, replacement: str | None
) -> ArticleBody:
    """Replace ``text`` with ``replacement`` (or delete it when ``None``) at the location.

    Raises:
        ArtifactValidationError: the location or sentence does not exist, or the edit would
            leave the dek, a paragraph's section or the body empty.
    """
    new = None if replacement is None else _squash(fix_dashes(replacement))
    if new == "":
        raise ArtifactValidationError("Replacement is empty; delete the sentence instead")
    remaining = tuple(
        f
        for f in body.flags
        if not (f.section == section and f.paragraph == paragraph and f.text == text)
    )

    if section == DEK:
        if new is None:
            raise ArtifactValidationError("The dek cannot be deleted; replace it")
        if text not in body.dek:
            raise ArtifactValidationError("Sentence not found in the dek")
        dek = _squash(body.dek.replace(text, new, 1))
        return body.model_copy(update={"dek": dek, "flags": remaining})

    if not 0 <= section < len(body.sections):
        raise ArtifactValidationError("No such section", context={"section": section})
    target = body.sections[section]
    if not 0 <= paragraph < len(target.paragraphs):
        raise ArtifactValidationError("No such paragraph", context={"paragraph": paragraph})
    old_paragraph = target.paragraphs[paragraph]
    if text not in old_paragraph:
        raise ArtifactValidationError("Sentence not found in the paragraph")
    edited = _squash(old_paragraph.replace(text, new or "", 1))

    paragraphs = list(target.paragraphs)
    citations = list(target.citations)
    if edited:
        paragraphs[paragraph] = edited
    else:
        if len(paragraphs) == 1:
            raise ArtifactValidationError("Cannot delete the last paragraph of a section")
        del paragraphs[paragraph]
        if citations:
            del citations[paragraph]
        # Flags below the removed paragraph move up one.
        remaining = tuple(
            f.model_copy(update={"paragraph": f.paragraph - 1})
            if f.section == section and f.paragraph > paragraph
            else f
            for f in remaining
        )
    sections = list(body.sections)
    sections[section] = ArticleSection(
        heading=target.heading,
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        table=target.table,
    )
    return body.model_copy(update={"sections": tuple(sections), "flags": remaining})
