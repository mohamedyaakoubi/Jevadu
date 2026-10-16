"""The search model puts the closest projects in order (search/rerank.py), on invented projects."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from hackathon_memory.llm.embeddings import SEARCH_MODEL
from hackathon_memory.search import engine, rerank
from searchfakes import embed_all, google, ids_of, three_projects


class Stub:
    """A model that answers one fixed text, or raises, and keeps what it was asked."""

    def __init__(self, answer: str = "", error: Exception | None = None) -> None:
        self.answer, self.error = answer, error
        self.asked: list[tuple[str, Any]] = []
        self.models = self

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.asked.append((contents, config))
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.answer)


def test_only_numbers_of_the_list_are_kept_once_in_the_models_order() -> None:
    stub = Stub(json.dumps({"closest": [3, 9, 1, 3, 0]}))
    lines = ["1. A: a", "2. B: b", "3. C: c"]
    assert rerank.ask_closest(stub, "m", "LOW", "an idea", lines) == [3, 1]
    assert stub.asked[0][1].http_options is None  # without a time limit, the client's options


def test_a_time_limit_makes_one_try() -> None:
    stub = Stub(json.dumps({"closest": [1]}))
    rerank.ask_closest(stub, "m", "LOW", "an idea", ["1. A: a"], timeout_seconds=8)
    options = stub.asked[0][1].http_options
    assert options.timeout == 8000 and options.retry_options.attempts == 1


@pytest.fixture
def database(empty_database: str) -> str:
    return three_projects(empty_database)


def test_the_closest_by_meaning_are_put_in_the_models_order(database: str) -> None:
    client, _, _ = google()
    embed_all(database, client)
    by_meaning = engine.by_meaning(engine.EmbeddingStore(database), client, "help a vendor",
                                   model=SEARCH_MODEL, limit=30)  # fmt: skip
    stub = Stub(json.dumps({"closest": [3]}))
    hits, ordered = rerank.closest_by_ai(database, client, stub, "help a vendor",
                                         embedding_model=SEARCH_MODEL, model="m",
                                         level="LOW")  # fmt: skip
    assert ordered is True
    assert [hit.project_id for hit in hits] == [by_meaning[2], by_meaning[0], by_meaning[1]]
    assert "Pebble Pay" in stub.asked[0][0]  # each project is one line of the question


def test_a_late_model_keeps_the_order_by_meaning(database: str) -> None:
    client, _, _ = google()
    embed_all(database, client)
    ids = ids_of(database)
    stub = Stub(error=httpx.ReadTimeout("late"))
    hits, ordered = rerank.closest_by_ai(database, client, stub, "help a vendor",
                                         embedding_model=SEARCH_MODEL, model="m", level="LOW",
                                         timeout_seconds=8)  # fmt: skip
    assert ordered is False and hits[0].project_id == ids["Pebble Pay"]


def test_with_no_embedding_only_the_words_are_searched(database: str) -> None:
    client, fake, _ = google()
    ids = ids_of(database)
    stub = Stub(json.dumps({"closest": [1]}))
    hits, ordered = rerank.closest_by_ai(database, client, stub, "a parcel tracker",
                                         embedding_model=SEARCH_MODEL, model="m",
                                         level="LOW")  # fmt: skip
    assert ordered is False and [hit.project_id for hit in hits] == [ids["Cedar Post"]]
    assert stub.asked == [] and fake.requests == []  # nothing was asked of anybody
