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


def test_a_comparison_is_asked_only_for_the_projects_not_kept(empty_database: str) -> None:
    import json as _json

    from hackathon_memory.search import compare as comparing
    from searchfakes import ids_of, three_projects

    database = three_projects(empty_database)
    ids = sorted(ids_of(database).values())

    class Answers:
        def __init__(self) -> None:
            self.asked: list[str] = []
            self.models = self

        def generate_content(self, *, model: str, contents: str, config: object) -> object:
            from types import SimpleNamespace

            self.asked.append(contents)
            numbers = [item["number"] for item in _json.loads(contents)["projects"]]
            return SimpleNamespace(text=_json.dumps({"projects": [
                {"number": n, "same": f"Same {n}.", "differs": f"Differs {n}.",
                 "fields_used": ["name"]} for n in numbers]}))  # fmt: skip

    model = Answers()
    items = comparing.items_for(database, ids[:2], model="m", version="v")
    found, asked = comparing.kept_or_compared(database, model, "an idea", items, model="f",
                                              thinking_level="LOW")  # fmt: skip
    assert asked == 2 and len(model.asked) == 1 and found[ids[0]].same == "Same 1."
    items = comparing.items_for(database, ids, model="m", version="v")
    found, asked = comparing.kept_or_compared(database, model, "an idea", items, model="f",
                                              thinking_level="LOW")  # fmt: skip
    assert asked == 1 and len(model.asked) == 2  # only the third project was asked about
    assert _json.loads(model.asked[-1])["projects"][0]["number"] == 3
    assert found[ids[1]].same == "Same 2." and found[ids[2]].same == "Same 3."
