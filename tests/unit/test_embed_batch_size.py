import json

import httpx

from signalforge.llm.providers import OpenAICompatibleProvider


def _provider(batch_size: int, seen: list[int]) -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        seen.append(len(texts))
        data = [{"embedding": [float(len(t))]} for t in texts]
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": len(texts)}})

    return OpenAICompatibleProvider(
        "https://example.test/v1",
        None,
        httpx.Client(transport=httpx.MockTransport(handler)),
        embed_batch_size=batch_size,
    )


def test_default_sends_every_text_in_one_request() -> None:
    seen: list[int] = []
    reply = _provider(0, seen).embed("m", ["a", "bb", "ccc"], timeout_s=5)
    assert seen == [3]
    assert [v[0] for v in reply.vectors] == [1.0, 2.0, 3.0]


def test_batch_size_one_sends_one_request_per_text_and_keeps_order() -> None:
    seen: list[int] = []
    reply = _provider(1, seen).embed("m", ["a", "bb", "ccc"], timeout_s=5)
    assert seen == [1, 1, 1]
    assert [v[0] for v in reply.vectors] == [1.0, 2.0, 3.0]
    assert reply.input_tokens == 3


def test_batch_size_two_splits_into_chunks() -> None:
    seen: list[int] = []
    _provider(2, seen).embed("m", ["a"] * 5, timeout_s=5)
    assert seen == [2, 2, 1]
