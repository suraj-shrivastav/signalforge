"""CLI: ``uv run python -m apps.worker.quality_report --days 30`` (read only).

Scores published articles with the auto-review's readability checks, to set
AUTO_REVIEW_LENGTH_FLOOR_RATIO from data and to measure Milestone 2. Prints Markdown.
"""

import argparse
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.worker._args import days as days_arg
from signalforge.auto_review import coherence_problems
from signalforge.core.artifacts.article import ArticleBody, ArticleTemplate
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.repositories.published import PublishedArticleRepository
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.stages.draft_extraction import LENGTH_BANDS, title_overreach, word_count

RATIOS = (1.0, 0.8, 0.6)


@dataclass(frozen=True)
class ArticleQuality:
    slug: str
    template: ArticleTemplate
    words: int
    coherence: tuple[str, ...]
    overreach: tuple[str, ...]


def assess(
    slug: str, body: ArticleBody, template: ArticleTemplate, min_section_sentences: int
) -> ArticleQuality:
    claims = " ".join(c.text for c in body.claims)
    return ArticleQuality(
        slug=slug,
        template=template,
        words=word_count(body),
        coherence=tuple(coherence_problems(body, min_section_sentences)),
        overreach=tuple(title_overreach(body.title, claims)),
    )


def below_floor(row: ArticleQuality, ratio: float) -> bool:
    return row.words < math.ceil(LENGTH_BANDS[row.template][0] * ratio)


def report(rows: Sequence[ArticleQuality], since: datetime) -> str:
    total = len(rows)

    def share(count: int) -> str:
        return f"{count} of {total}"

    lines = [f"# Article quality report since {since:%Y-%m-%d}", "", f"Published: {total}", ""]
    for ratio in RATIOS:
        below = sum(below_floor(r, ratio) for r in rows)
        lines.append(f"- Below {ratio:.0%} of the template minimum: {share(below)}")
    lines.append(
        f"- Readability problems (dangling openers, thin sections): "
        f"{share(sum(bool(r.coherence) for r in rows))}"
    )
    lines.append(
        f"- Title uses a strong word no claim states: {share(sum(bool(r.overreach) for r in rows))}"
    )
    lines += ["", "| Article | Template | Words | Problems |", "|---|---|---|---|"]
    for r in rows:
        found = [*r.coherence, *(f"title word '{w}'" for w in r.overreach)]
        problems = "; ".join(found).replace("|", "/") or "none"
        lines.append(f"| {r.slug} | {r.template.value} | {r.words} | {problems} |")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=days_arg, default=30, help="published in the last N days")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    since = datetime.now(UTC) - timedelta(days=args.days)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        with create_session_factory(engine)() as session:
            rows = [
                assess(
                    row.slug,
                    ArticleBody.model_validate(row.body),
                    ArticleTemplate(row.template),
                    settings.auto_review_min_section_sentences,
                )
                for row in PublishedArticleRepository(session).list_public(200)
                if row.published_at >= since
            ]
    finally:
        engine.dispose()
    print(report(rows, since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
