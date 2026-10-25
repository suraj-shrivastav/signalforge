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


def test_upload_via_api_posts_both_svgs_and_no_storage_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(url: str, **kwargs: Any) -> tuple[int, bytes]:
        calls.append({"url": url, **kwargs})
        return 200, b"{}"

    monkeypatch.setattr(img, "_request", fake_request)
    img.upload_via_api(
        "my-slug",
        ("<svg/>", {"alt": "Cover"}),
        ("<svg></svg>", {"alt": "Fig", "caption": "Cap"}),
        "https://api.example/",
        "agent-key",
    )
    (call,) = calls
    assert call["url"] == "https://api.example/editor/articles/my-slug/images/upload"
    assert call["headers"]["X-Editor-Key"] == "agent-key"
    body = json.loads(call["data"])
    assert body["figure"] == {"svg": "<svg></svg>", "alt": "Fig", "caption": "Cap"}
    assert "supabase" not in str(call).lower()


def test_upload_via_api_reports_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(img, "_request", lambda *_a, **_k: (503, b"not configured"))
    with pytest.raises(img.SpecError, match="HTTP 503"):
        img.upload_via_api(
            "s", ("<svg/>", {"alt": "a"}), ("<svg/>", {"alt": "b"}), "https://api.example", "k"
        )


def test_script_avoids_python_310_only_calls() -> None:
    """Hermes runs the script with the system python3, which is 3.9 on macOS."""
    source = (ROOT / "scripts" / "articleimg.py").read_text()
    assert "strict=" not in source  # zip(strict=True) needs 3.10


def architecture(boxes: list[str]) -> dict[str, Any]:
    spec = example("example-architecture-figure.json")
    spec["values"] = {"boxes": boxes}
    return spec


def test_architecture_validates_box_count_length_and_fields() -> None:
    assert img.validate(architecture(["a", "b", "c"]), None) == []
    assert any("3 to 5" in e for e in img.validate(architecture(["a", "b"]), None))
    assert any("3 to 5" in e for e in img.validate(architecture(list("abcdef")), None))
    assert any("1 to 14" in e for e in img.validate(architecture(["a", "b", "x" * 15]), None))
    assert any(
        "no figure" in e for e in img.validate({**architecture(list("abc")), "figure": "5"}, None)
    )
    spec = architecture(["Stage 9", "b", "c"])
    assert any("number '9'" in e for e in img.validate(spec, ARTICLE))


@pytest.mark.parametrize("count", [3, 4, 5])
def test_architecture_draws_every_box_and_one_arrow_between_each_pair(count: int) -> None:
    names = ["Query", "Retriever", "Reranker", "Language model", "Answer"][:count]
    svg = img.render(architecture(names), "some-slug")
    assert all(f">{name}</text>" in svg for name in names)
    assert svg.count("<polygon") == count - 1
    assert svg == img.render(architecture(names), "some-slug")  # same slug, same image


@pytest.mark.parametrize("slug", ["a", "b", "c", "d", "e", "f"])
def test_architecture_boxes_stay_inside_the_canvas_and_do_not_overlap(slug: str) -> None:
    for count in (3, 4, 5):
        svg = img.render(architecture(list("abcde")[:count]), slug)
        rects = [
            tuple(int(v) for v in m)
            for m in re.findall(
                r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" rx="44"', svg
            )
        ]
        assert len(rects) == count
        for x, y, w, h in rects:
            assert x >= 80
            assert x + w <= 1120
            assert y + h <= 820
        for i, (x1, y1, w1, h1) in enumerate(rects):
            for x2, y2, w2, h2 in rects[i + 1 :]:
                assert x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1


def test_architecture_cover_and_figure_pair_with_the_ripples_cover() -> None:
    cover = example("example-architecture-cover.json")
    figure = example("example-architecture-figure.json")
    assert img.check_pair(cover, figure) == []
