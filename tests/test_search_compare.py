"""The comparison of the first results with the idea (design 8.3): the options of its call."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from hackathon_memory.search.compare import Item, compare

ANSWER = json.dumps({"projects": [{"number": 1, "same": "Same.", "differs": "Differs.",
                                   "fields_used": ["short_line"]}]})  # fmt: skip


class Stub:
    """A client that keeps the config of each call and answers one fixed comparison."""

    def __init__(self) -> None:
        self.configs: list[Any] = []
        self.models = self

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.configs.append(config)
        return SimpleNamespace(text=ANSWER)


ITEMS = [Item(1, 42, {"name": "Pebble Pay", "short_line": "Pay a vendor with a coin."})]


def test_a_comparison_a_person_waits_for_is_tried_once_and_not_for_long() -> None:
    client = Stub()
    found = compare(client, "a coin", ITEMS, model="m", thinking_level="LOW", timeout_seconds=30)
    assert found[42].same == "Same."
    options = client.configs[0].http_options
    assert options.timeout == 30_000  # the library counts in milliseconds
    assert options.retry_options.attempts == 1


def test_without_a_time_limit_the_client_keeps_its_own_options() -> None:
    client = Stub()
    compare(client, "a coin", ITEMS, model="m", thinking_level="LOW")
    assert client.configs[0].http_options is None
