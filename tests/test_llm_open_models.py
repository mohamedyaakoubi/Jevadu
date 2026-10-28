"""The client of the open models of Vertex AI (llm/open_models.py), on a stand-in endpoint."""

from __future__ import annotations

import json

import pytest

from hackathon_memory.finops.budget import Budget, BudgetExceeded
from hackathon_memory.finops.calls import MemoryStore
from hackathon_memory.llm.open_models import DEEPSEEK_FLASH, OpenModelError
from hackathon_memory.search import rerank
from openfake import FakeOpenModels as Endpoint
from openfake import answer
from openfake import open_client as client


def test_a_call_asks_the_model_with_its_publisher_and_its_thinking() -> None:
    endpoint, store = Endpoint((200, answer('{"closest": [2]}'))), MemoryStore()
    got = client(endpoint, store).chat(DEEPSEEK_FLASH, "the rules", "the question", thinking=True,
                                       max_tokens=500, timeout_seconds=5, as_json=True,
                                       effort="high")  # fmt: skip
    assert got.text == '{"closest": [2]}'
    request = endpoint.sent[0]
    assert request.url.path == (
        "/v1/projects/a-project/locations/global/endpoints/openapi/chat/completions"
    )
    assert request.headers["Authorization"] == "Bearer a-token"
    body = endpoint.body()
    assert body["model"] == "deepseek-ai/deepseek-v4.1-flash-maas"
    assert body["chat_template_kwargs"] == {"thinking": True}
    assert body["reasoning_effort"] == "high"
    assert body["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_the_thinking_counts_as_output_when_it_has_no_count_of_its_own() -> None:
    endpoint, store = Endpoint((200, answer("{}"))), MemoryStore()
    got = client(endpoint, store).chat(DEEPSEEK_FLASH, "s", "u", thinking=True, max_tokens=500,
                                       timeout_seconds=5, effort="high")  # fmt: skip
    assert (got.input_tokens, got.output_tokens, got.thinking_tokens) == (120, 900, 0)
    [call] = store.calls()
    assert (call.model, call.purpose, call.location) == (DEEPSEEK_FLASH, "rerank", "global")
    assert call.output_tokens == 900 and call.thinking_level == "HIGH" and call.ok
    # 120 tokens at $0.30 and 900 at $1.20 a million (finops/prices.py)
    assert call.cost_usd == pytest.approx(120 * 0.30 / 1e6 + 900 * 1.20 / 1e6)


def test_a_count_of_the_thinking_is_kept_apart() -> None:
    usage = {"prompt_tokens": 10, "completion_tokens": 300,
             "completion_tokens_details": {"reasoning_tokens": 250}}  # fmt: skip
    endpoint, store = Endpoint((200, answer("{}", usage))), MemoryStore()
    got = client(endpoint, store).chat(DEEPSEEK_FLASH, "s", "u", thinking=True, max_tokens=500,
                                       timeout_seconds=5)  # fmt: skip
    assert (got.output_tokens, got.thinking_tokens) == (50, 250)
    assert store.calls()[0].thinking_level == "ON"


def test_an_error_is_raised_and_counted_by_its_kind_only() -> None:
    endpoint, store = Endpoint((503, {"error": {"message": "the idea text"}})), MemoryStore()
    with pytest.raises(OpenModelError, match="503"):
        client(endpoint, store).chat(DEEPSEEK_FLASH, "s", "the idea text", thinking=False,
                                     max_tokens=500, timeout_seconds=5)  # fmt: skip
    [call] = store.calls()
    assert not call.ok and call.error_kind == "OpenModelError 503" and call.input_tokens == 0


def test_an_answer_with_no_choice_is_an_error_of_the_model() -> None:
    endpoint, store = Endpoint((200, {"id": "x", "object": "chat.completion"})), MemoryStore()
    with pytest.raises(OpenModelError, match=r"no choice: \['id', 'object'\]"):
        client(endpoint, store).chat(DEEPSEEK_FLASH, "s", "u", thinking=False, max_tokens=500,
                                     timeout_seconds=5)  # fmt: skip
    [call] = store.calls()
    assert not call.ok and call.error_kind == "OpenModelError"


def test_a_spent_budget_stops_the_call_before_it_is_sent() -> None:
    endpoint, store = Endpoint((200, answer("{}"))), MemoryStore()
    with pytest.raises(BudgetExceeded):
        client(endpoint, store, Budget("test", total_usd=0.0)).chat(
            DEEPSEEK_FLASH, "s", "u", thinking=True, max_tokens=500, timeout_seconds=5)  # fmt: skip
    assert endpoint.sent == [] and store.calls() == []


def test_a_tagged_client_keeps_its_meter() -> None:
    endpoint, store = Endpoint((200, answer("{}"))), MemoryStore()
    client(endpoint, store).tagged(item_ref="case 3").chat(
        DEEPSEEK_FLASH, "s", "u", thinking=False, max_tokens=500, timeout_seconds=5)  # fmt: skip
    [call] = store.calls()
    assert (call.purpose, call.item_ref) == ("rerank", "case 3")


def test_the_search_order_can_come_from_an_open_model() -> None:
    endpoint, store = Endpoint((200, answer('{"closest": [3, 9, 1, 3]}'))), MemoryStore()
    lines = ["1. A: a", "2. B: b", "3. C: c"]
    got = rerank.ask_closest(client(endpoint, store), DEEPSEEK_FLASH, rerank.OPEN_EFFORT,
                             "an idea", lines, timeout_seconds=30)  # fmt: skip
    assert got == [3, 1]
    body = endpoint.body()
    assert body["reasoning_effort"] == "high" and body["max_tokens"] == rerank.OPEN_MAX_TOKENS
    assert body["messages"][0]["content"].endswith(rerank.JSON_ANSWER)
    assert body["messages"][1]["content"].startswith("Idea: an idea")


def test_an_open_model_can_order_without_thinking() -> None:
    endpoint, store = Endpoint((200, answer('{"closest": [1]}'))), MemoryStore()
    rerank.ask_closest(client(endpoint, store), DEEPSEEK_FLASH, rerank.OPEN_OFF, "an idea",
                       ["1. A: a"], timeout_seconds=8)  # fmt: skip
    body = endpoint.body()
    assert body["chat_template_kwargs"] == {"thinking": False} and "reasoning_effort" not in body
    assert store.calls()[0].thinking_level is None


def test_a_comparison_can_come_from_an_open_model() -> None:
    from hackathon_memory.search import compare

    told = {"projects": [{"number": 1, "same": "Both pay a vendor.", "differs": "It uses coins.",
                          "fields_used": ["short_line", "not_a_text"]}]}  # fmt: skip
    endpoint, store = Endpoint(content=json.dumps(told)), MemoryStore()
    items = [compare.Item(1, 42, {"name": "Pebble Pay", "short_line": "Pay a vendor."})]
    found = compare.compare(client(endpoint, store), "an idea", items, model=DEEPSEEK_FLASH,
                            thinking_level=compare.OPEN_OFF, timeout_seconds=30)  # fmt: skip
    assert found[42].same == "Both pay a vendor." and found[42].fields_used == ["short_line"]
    body = endpoint.body()
    assert body["chat_template_kwargs"] == {"thinking": False} and "reasoning_effort" not in body
    assert body["messages"][0]["content"].endswith(compare.JSON_ANSWER)
