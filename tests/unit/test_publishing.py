import pytest

from signalforge.publishing import meta_description, slugify, unique_slug


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Granite Speech 5.0: Transcribe, Translate!", "granite-speech-5-0-transcribe-translate"),
        ("  Café  déjà vu  ", "cafe-deja-vu"),
        ("日本語", "article"),
        ("---", "article"),
    ],
)
def test_slugify(title: str, expected: str) -> None:
    assert slugify(title) == expected


def test_slugify_cuts_at_a_word_boundary() -> None:
    slug = slugify("word " * 40)
    assert len(slug) <= 80
    assert not slug.endswith("-")
    assert all(part == "word" for part in slug.split("-"))


def test_unique_slug_numbers_collisions() -> None:
    taken = {"a", "a-2"}
    assert unique_slug("b", taken.__contains__) == "b"
    assert unique_slug("a", taken.__contains__) == "a-3"


def test_meta_description_fits_a_snippet_without_cutting_words() -> None:
    short = "A short dek."
    assert meta_description(short) == short
    long = " ".join(["information"] * 30)
    out = meta_description(long)
    assert len(out) <= 155
    assert out.endswith("...")
    assert "informatio..." not in out
