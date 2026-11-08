"""Replay research on accepted cards in dry-run mode and report depth and reliability.

    python scripts/eval_research.py --limit 30 --label before --out before.json

Reads accepted cards, calls ``_process_card`` for each and NEVER writes to the database: the
LLM gateway's session never flushes or commits and is rolled back after every card.
Needs DATABASE_URL and the same provider keys as the worker.
"""

import argparse
import json
import logging
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT, _ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_ARXIV_HOSTS = ("arxiv.org", "ar5iv.labs.arxiv.org")
_DIGIT = re.compile(r"\d")
_STAGE_LOGGER = "signalforge.stages.research"
_EXTRACTION_WARNING = "research extraction invalid"


def _share(part: float, whole: float) -> float:
    return part / whole if whole else 0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals over per-card rows; every ratio is 0 when its denominator is 0."""
    researched = [r for r in rows if r["status"] == "researched"]
    arxiv = [r for r in rows if r["host"] in _ARXIV_HOSTS]
    documents = sum(r["documents"] for r in rows)
    failures = sum(r["extraction_failures"] for r in rows)
    return {
        "cards": len(rows),
        "researched_share": _share(len(researched), len(rows)),
        "mean_claims": _mean([r["claims"] for r in rows]),
        "numeric_share_of_researched": _share(
            sum(1 for r in researched if r["numeric_claims"] > 0), len(researched)
        ),
        "full_text_share_arxiv": _share(
            sum(1 for r in arxiv if r["primary_full_text"]), len(arxiv)
        ),
        "mean_cost_usd": _mean([r["cost_usd"] for r in rows]),
        "mean_calls": _mean([r["calls"] for r in rows]),
        "extraction_success_rate": _share(documents - failures, documents),
        "failure_classes": dict(Counter(r["failure_class"] for r in rows if r["failure_class"])),
    }


class _WarningCounter(logging.Handler):
    """Counts the stage's per-document extraction failures."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if _EXTRACTION_WARNING in record.getMessage():
            self.count += 1


def _is_full_text(urls: Sequence[str]) -> bool:
    """A primary read as a whole paper (arXiv HTML or ar5iv), not just its abstract page."""
    return any("/html/" in u or "ar5iv" in u for u in urls)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eval_research", description="Dry-run research replay and report (no DB writes)."
    )
    parser.add_argument("--limit", type=int, default=30, help="max accepted cards (newest first)")
    parser.add_argument("--label", default="before", help="label stored in the JSON, e.g. before")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _print_table(rows: list[dict[str, Any]], totals: dict[str, Any]) -> None:
    print(
        f"{'card':8} {'host':24} {'docs':>4} {'full':>4} {'clm':>3} {'num':>3} "
        f"{'status':16} {'class':10} {'usd':>7} {'calls':>5} {'xfail':>5}"
    )
    for r in rows:
        print(
            f"{r['card_id'][:8]:8} {r['host'][:24]:24} {r['documents']:>4} "
            f"{'y' if r['primary_full_text'] else 'n':>4} {r['claims']:>3} "
            f"{r['numeric_claims']:>3} {r['status']:16} {(r['failure_class'] or '-'):10} "
            f"{r['cost_usd']:>7.4f} {r['calls']:>5} {r['extraction_failures']:>5}"
        )
    print()
    for key, value in totals.items():
        print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    from signalforge.core.config import get_settings
    from signalforge.core.errors import ConfigurationError

    try:
        settings = get_settings()
    except ConfigurationError:
        print("eval_research: cannot start, missing or invalid settings.", file=sys.stderr)
        print("Set DATABASE_URL and the provider keys the worker uses (see .env).", file=sys.stderr)
        return 2
    if settings.llm_provider == "fake":
        print(
            "eval_research: LLM_PROVIDER is 'fake'; set the real provider and keys.",
            file=sys.stderr,
        )
        return 2

    import uuid

    import httpx
    from apps.worker.research import build_search
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from signalforge.core.budget import Budget, BudgetScope
    from signalforge.core.errors import SignalForgeError
    from signalforge.core.logging import configure_logging
    from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
    from signalforge.db.models.signals import Signal
    from signalforge.db.session import ConnectionMode, create_db_engine
    from signalforge.llm.gateway import build_gateway
    from signalforge.plugins.search.direct_fetch import DirectFetcher
    from signalforge.stages.research import _process_card

    configure_logging(settings.log_level)
    counter = _WarningCounter()
    logging.getLogger(_STAGE_LOGGER).addHandler(counter)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    rows: list[dict[str, Any]] = []
    try:
        latest = (
            select(EditorDecisionRow.topic_card_id, EditorDecisionRow.decision)
            .distinct(EditorDecisionRow.topic_card_id)
            .order_by(
                EditorDecisionRow.topic_card_id,
                EditorDecisionRow.decided_at.desc(),
                EditorDecisionRow.created_at.desc(),
            )
            .subquery()
        )
        query = (
            select(TopicCardRow, Signal)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(latest, latest.c.topic_card_id == TopicCardRow.id)
            .where(latest.c.decision == "accepted")
            .order_by(TopicCardRow.created_at.desc(), TopicCardRow.id.asc())
            .limit(args.limit)
        )
        with Session(engine) as read_session:
            cards = [(c, s) for c, s in read_session.execute(query).all()]
            read_session.rollback()
            with httpx.Client() as client:
                fetcher = DirectFetcher(client)
                search = build_search(settings, client)
                for card, signal in cards:
                    budget = Budget(BudgetScope.TOPIC, settings.budget_limits(BudgetScope.TOPIC))
                    # Own session, autoflush off, rolled back below: llm_calls rows never land.
                    with Session(engine, autoflush=False) as scratch:
                        gateway = build_gateway(settings, scratch, budget)
                        before = counter.count
                        try:
                            package, why = _process_card(
                                gateway, fetcher, search, card, signal, uuid.uuid4()
                            )
                        except SignalForgeError as exc:  # report, go on with the next card
                            print(f"card {card.id}: {type(exc).__name__}: {exc}", file=sys.stderr)
                            scratch.rollback()
                            continue
                        scratch.rollback()
                    host = urllib.parse.urlsplit(signal.canonical_url).hostname or ""
                    primary_urls = [d.url for d in package.documents if d.is_primary]
                    rows.append(
                        {
                            "card_id": str(card.id),
                            "host": host,
                            "documents": len(package.documents),
                            "primary_full_text": _is_full_text(primary_urls),
                            "claims": len(package.claims),
                            "numeric_claims": sum(
                                1 for c in package.claims if _DIGIT.search(c.text)
                            ),
                            "status": package.status.value,
                            "failure_class": why.split(":", 1)[0] if why else None,
                            "cost_usd": float(budget.spent_usd),
                            "calls": budget.calls,
                            "extraction_failures": counter.count - before,
                        }
                    )
    finally:
        engine.dispose()
    totals = summarize(rows)
    _print_table(rows, totals)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"label": args.label, "totals": totals, "rows": rows}, indent=2) + "\n"
        )
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
