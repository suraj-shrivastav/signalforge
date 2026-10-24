import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2] / "skills" / "article-images"
spec = importlib.util.spec_from_file_location("articleimg", ROOT / "scripts" / "articleimg.py")
assert spec is not None
assert spec.loader is not None
img = importlib.util.module_from_spec(spec)
sys.modules["articleimg"] = img
spec.loader.exec_module(img)

ARTICLE: dict[str, Any] = {
    "title": "Granite Speech 5.0",
    "dek": "A 2B-parameter model and a 470M variant.",
    "claims": [
        {"text": "It reaches a word error rate of 5.06%.", "status": "verified"},
        {"text": "It was trained on 390,000 hours.", "status": "unverified"},
    ],
}


def example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((ROOT / "examples" / name).read_text())
    return data


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*.json")))
def test_every_example_is_valid_and_renders(path: Path) -> None:
    data = json.loads(path.read_text())
    assert img.validate(data, None) == []
    svg = img.render(data, "some-slug")
    assert svg.startswith("<svg")
    assert data["alt"] in svg
    assert "NaN" not in svg


def test_numbers_must_come_from_the_title_dek_or_verified_claims() -> None:
    fig = example("granite-figure.json")
    assert img.validate(fig, ARTICLE) == []
    assert img.validate({**fig, "figure": "9.99%"}, ARTICLE) == [
        "number '9.99' is not in the article's title, dek or verified claims"
    ]
    # 390,000 only appears in an unverified claim
    assert img.validate({**fig, "figure": "390K", "caption": "hours"}, ARTICLE) != []


def test_limits_unknown_fields_and_template_rules() -> None:
    fig = example("granite-figure.json")
    assert any("limit 8" in e for e in img.validate({**fig, "figure": "123456789"}, None))
    assert any("unknown fields" in e for e in img.validate({**fig, "color": "red"}, None))
    assert any("template" in e for e in img.validate({**fig, "template": "photo"}, None))
    layers = example("example-paper-figure.json")
    assert any("exactly 3" in e for e in img.validate({**layers, "values": {"items": ["a"]}}, None))
    assert any("no figure" in e for e in img.validate({**layers, "figure": "5"}, None))


def test_pair_needs_different_templates_and_roles() -> None:
    cover, fig = example("granite-cover.json"), example("granite-figure.json")
    assert img.check_pair(cover, fig) == []
    assert img.check_pair(cover, {**fig, "template": cover["template"]}) != []
    assert img.check_pair(fig, cover) != []


def test_same_spec_same_image_other_slug_different_image() -> None:
    fig = example("granite-figure.json")
    assert img.render(fig, "a") == img.render(fig, "a")
    renders = {img.render(fig, f"article-{i}") for i in range(6)}
    assert len(renders) == 6


def test_cover_and_figure_use_different_colours() -> None:
    for slug in ("a", "b", "c", "d", "e"):
        assert img.Seed(slug, "cover").palette != img.Seed(slug, "figure").palette


def test_text_is_escaped() -> None:
    fig = {**example("granite-figure.json"), "alt": "A <b> & B"}
    assert "<b>" not in img.render(fig, "x")


def test_compare_blocks_scale_with_values() -> None:
    cover = example("granite-cover.json")
    even = {
        **cover,
        "values": {
            "a": {**cover["values"]["a"], "value": 100},
            "b": {**cover["values"]["b"], "value": 100},
        },
    }
    assert img.render(even, "s") != img.render(cover, "s")


@pytest.mark.parametrize("small", [470, 1000, 1900, 2000])
def test_compare_blocks_stay_inside_the_canvas(small: int) -> None:
    cover = example("granite-cover.json")
    spec = {
        **cover,
        "values": {
            "a": {**cover["values"]["a"], "value": 2000},
            "b": {**cover["values"]["b"], "value": small},
        },
    }
    for slug in ("a", "b", "c", "d", "e", "f"):
        rects = [
            (int(x), int(w))
            for x, w in re.findall(
                r'<rect x="(-?\d+)" y="\d+" width="(\d+)" height="\d+" rx', img.render(spec, slug)
            )
        ]
        assert len(rects) == 2, slug
        assert all(x >= 80 and x + w <= 1120 for x, w in rects), (slug, rects)
