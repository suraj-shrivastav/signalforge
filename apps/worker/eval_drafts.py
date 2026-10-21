"""Draft evaluation over a golden set of stored research packages.

    uv run python -m apps.worker.eval_drafts export          # DB -> tests/golden/*.json
    uv run python -m apps.worker.eval_drafts run             # draft each fixture, score it
    uv run python -m apps.worker.eval_drafts judge           # judge false accepts / rejects

``export`` reads the database. ``run`` and ``judge`` need only the fixtures and the LLM
provider: nothing is written to the database. Fixtures keep each document's text only
around the cited quotes, which is all the writer and judge ever see.
"""

import argparse
import json
import re
import time
import uuid
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.article import ArticleDraft, ArticleTemplate, FlagKind
from signalforge.core.artifacts.research import ResearchPackage
from signalforge.core.budget import Budget, BudgetScope
from signalforge.core.config import get_settings
from signalforge.core.errors import SignalForgeError
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.stages import draft
from signalforge.stages.draft_extraction import LENGTH_BANDS, word_count

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "tests" / "golden"
_WINDOW = 300
_NUMBER = re.compile(r"\d+")
_FABRICATION = " An independent audit confirmed this result in every region."


class _NullSession:
    """Stands in for a DB session: the gateway only calls ``add``."""

    def add(self, row: object) -> None:
        pass


def trim_package(package: ResearchPackage) -> ResearchPackage:
    """Keep each document's text only around the quotes that cite it."""
    documents = []
    for index, doc in enumerate(package.documents):
        spans = [c.evidence_span.strip() for c in package.claims if index in c.document_indices]
        ranges = sorted(
            (max(0, at - _WINDOW), at + len(span) + _WINDOW)
            for span in spans
            if (at := doc.text.find(span)) >= 0
        )
        merged: list[list[int]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        text = "\n...\n".join(doc.text[s:e] for s, e in merged) or doc.text[:_WINDOW]
        documents.append(doc.model_copy(update={"text": text}))
    return package.model_copy(update={"documents": tuple(documents)})


def load_fixtures(directory: Path = GOLDEN_DIR) -> list[dict[str, Any]]:
    fixtures = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text())
        raw["package"] = ResearchPackage.model_validate(raw["package"])
        raw["name"] = path.stem
        fixtures.append(raw)
    return fixtures


def score(result: ArticleDraft) -> dict[str, Any]:
    """Deterministic metrics for one draft, read from the draft and its review summary."""
    body = result.draft
    low, high = LENGTH_BANDS[result.template]
    words = word_count(body) if body else 0
    sentences = (
        sum(len(re.findall(r"[.!?](?:\s|$)", p)) or 1 for s in body.sections for p in s.paragraphs)
        if body
        else 0
    )
    flags = body.flags if body else ()
    uncited = sum(f.kind is FlagKind.UNCITED for f in flags)
    numbers = sum(f.kind is FlagKind.NUMBER for f in flags)
    rejected = sum(f.kind is FlagKind.UNSUPPORTED for f in flags)
    return {
        "status": result.status.value,
        "template": result.template.value,
        "words": words,
        "in_band": low <= words <= high,
        "sentences": sentences,
        "uncited": uncited,
        "number_mismatch": numbers,
        "judge_rejected": rejected,
        "cited_claims": len(body.claims) if body else 0,
        "grounded_rate": round(1 - (uncited + numbers + rejected) / sentences, 3)
        if sentences
        else 0.0,
    }


def _gateway(budget_usd: Decimal | None = None) -> LLMGateway:
    settings = get_settings()
    limits = settings.budget_limits(BudgetScope.ARTICLE)
    if budget_usd is not None:
        limits = limits.__class__(max_cost_usd=budget_usd)
    return build_gateway(settings, _NullSession(), Budget(BudgetScope.ARTICLE, limits))  # type: ignore[arg-type]


def run_eval(fixtures: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for fx in fixtures:
        gateway = _gateway()
        started = time.monotonic()
        try:
            result = draft._process_card(
                gateway,
                fx["package"],
                ArticleTemplate(fx["template"]),
                uuid.uuid4(),
                fx.get("brief", ""),
            )
            row = {"fixture": fx["name"], **score(result)}
        except SignalForgeError as exc:  # report and continue: one bad card must not hide the rest
            row = {
                "fixture": fx["name"],
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        row["seconds"] = round(time.monotonic() - started, 1)
        rows.append(row)
    return rows


def _mutate_number(text: str) -> str | None:
    match = _NUMBER.search(text)
    if match is None:
        return None
    return text[: match.start()] + str(int(match.group(0)) + 7) + text[match.end() :]


def judge_probe(fixtures: Sequence[dict[str, Any]], per_fixture: int = 6) -> dict[str, Any]:
    """Judge accuracy on labelled items built from stored claims.

    Positives are claim texts (should be supported). Negatives are the same claim with a
    number changed, or with an invented clause appended (should be rejected).
    """
    counts = {"pos": 0, "pos_rejected": 0, "neg": 0, "neg_accepted": 0, "neg_number": 0,
              "neg_number_accepted": 0}  # fmt: skip
    for fx in fixtures:
        package: ResearchPackage = fx["package"]
        gateway = _gateway()
        items: list[tuple[draft._Sentence, str]] = []
        for index, claim in enumerate(package.claims[:per_fixture]):
            items.append((draft._Sentence(claim.text, (index,)), "pos"))
            changed = _mutate_number(claim.text)
            if changed:
                items.append((draft._Sentence(changed, (index,)), "neg_number"))
            items.append((draft._Sentence(claim.text + _FABRICATION, (index,)), "neg"))
        verdicts = draft._judge(gateway, uuid.uuid4(), package, [s for s, _ in items])
        for position, (_, kind) in enumerate(items):
            supported = verdicts.get(position, False)
            if kind == "pos":
                counts["pos"] += 1
                counts["pos_rejected"] += not supported
            else:
                counts["neg"] += 1
                counts["neg_accepted"] += supported
                if kind == "neg_number":
                    counts["neg_number"] += 1
                    counts["neg_number_accepted"] += supported

    def rate(num: int, den: int) -> float:
        return round(num / den, 3) if den else 0.0

    return {
        **counts,
        "false_reject_rate": rate(counts["pos_rejected"], counts["pos"]),
        "false_accept_rate": rate(counts["neg_accepted"], counts["neg"]),
        "false_accept_rate_changed_number": rate(
            counts["neg_number_accepted"], counts["neg_number"]
        ),
    }


def export_fixtures(session: Session, directory: Path = GOLDEN_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    query = (
        select(ResearchPackageRow, TopicCardRow, Signal)
        .join(TopicCardRow, TopicCardRow.id == ResearchPackageRow.card_id)
        .join(Signal, Signal.id == TopicCardRow.signal_id)
        .where(ResearchPackageRow.status == "researched")
        .order_by(ResearchPackageRow.created_at)
    )
    for row, card, signal in session.execute(query).all():
        package = trim_package(draft._package(row))
        payload = {
            "card": str(card.id)[:8],
            "title": signal.title,
            "template": draft._template_for(card, signal).value,
            "brief": card.suggested_angle,
            "package": json.loads(package.model_dump_json()),
        }
        path = directory / f"{str(card.id)[:8]}.json"
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_drafts")
    parser.add_argument("command", choices=["export", "run", "judge"])
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)
    if args.command == "export":
        engine = create_db_engine(get_settings(), ConnectionMode.SESSION)
        try:
            with create_session_factory(engine)() as session:
                for path in export_fixtures(session):
                    print(f"wrote {path.relative_to(GOLDEN_DIR.parents[1])}")
        finally:
            engine.dispose()
        return 0
    fixtures = load_fixtures()
    report: Any = run_eval(fixtures) if args.command == "run" else judge_probe(fixtures)
    print(json.dumps(report, indent=1))
    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
