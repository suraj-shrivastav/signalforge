"""CLI: ``uv run python -m apps.worker.backfill_process_note [--apply]``.

Published articles the automated review approved still say "An editor reviewed and approved
this article". This rewrites their process note to PUBLISH_PROCESS_NOTE_AUTO. Dry run by
default: it prints the slugs it would change. ``modified_at`` is left alone, because the
article text does not change.
"""

import argparse
from collections.abc import Sequence

from sqlalchemy import select

from signalforge.auto_review import POLICY_APPROVAL_NOTE
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.published import PublishedArticleRow
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory


def needs_rewrite(review_note: str, process_note: str, auto_note: str) -> bool:
    return review_note == POLICY_APPROVAL_NOTE and process_note != auto_note


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    auto_note = settings.publish_process_note_auto
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        with create_session_factory(engine)() as session:
            pairs = session.execute(
                select(PublishedArticleRow, ArticleDraftRow.review_note).join(
                    ArticleDraftRow, ArticleDraftRow.card_id == PublishedArticleRow.card_id
                )
            ).all()
            changed = [
                row for row, note in pairs if needs_rewrite(note, row.process_note, auto_note)
            ]
            for row in changed:
                print(row.slug)
                if args.apply:
                    row.process_note = auto_note
            if args.apply:
                session.commit()
    finally:
        engine.dispose()
    print(f"{len(changed)} article(s) {'updated' if args.apply else 'would change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
