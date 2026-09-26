"""Parse RSS 2.0 and Atom into a flat list of entries. Entries without a link are dropped."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from signalforge.core.errors import ArtifactValidationError

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class FeedEntry:
    title: str
    link: str
    published: datetime | None
    summary: str


def _text(node: ET.Element, *tags: str) -> str:
    for tag in tags:
        found = node.find(tag)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return ""


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = (
            datetime.fromisoformat(value) if value[:4].isdigit() else parsedate_to_datetime(value)
        )
    except (ValueError, TypeError, IndexError, OverflowError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _atom_link(entry: ET.Element) -> str:
    for link in entry.findall(f"{_ATOM}link"):
        href = link.get("href", "").strip()
        if link.get("rel", "alternate") == "alternate" and href:
            return href
    return ""


def parse_feed(xml: bytes) -> list[FeedEntry]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ArtifactValidationError("Feed is not valid XML") from exc
    entries: list[FeedEntry] = []
    for item in root.iter("item"):
        entries.append(
            FeedEntry(
                _text(item, "title"),
                _text(item, "link"),
                _date(_text(item, "pubDate")),
                _text(item, "description"),
            )
        )
    for atom in root.iter(f"{_ATOM}entry"):
        entries.append(
            FeedEntry(
                _text(atom, f"{_ATOM}title"),
                _atom_link(atom),
                _date(_text(atom, f"{_ATOM}published", f"{_ATOM}updated")),
                _text(atom, f"{_ATOM}summary", f"{_ATOM}content"),
            )
        )
    return [e for e in entries if e.link and e.title]
