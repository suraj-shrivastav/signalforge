import re
from pathlib import Path

from signalforge.core.reason_tags import REASON_TAGS

API_TS = Path(__file__).parents[2] / "apps/web/src/lib/api.ts"


def test_web_reason_tags_match_python() -> None:
    match = re.search(r"REASON_TAGS\s*=\s*\[(.*?)\]\s*as const", API_TS.read_text(), re.S)
    assert match, "REASON_TAGS array not found in apps/web/src/lib/api.ts"
    web = tuple(re.findall(r'"([^"]+)"', match.group(1)))
    assert web == REASON_TAGS, (
        f"ReasonTag drift: api.ts has {web}, reason_tags.py has {REASON_TAGS}. "
        "Update both to the same members in the same order."
    )
