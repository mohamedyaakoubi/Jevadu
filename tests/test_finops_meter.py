"""The meter: every call is counted, none goes around the count, and no text is kept.

The real google-genai library makes the calls. Only the network is replaced (googlefake.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from googlefake import PAGE_CANARY, FakeGoogle, answer
from hackathon_memory.finops.budget import Budget, BudgetExceeded
from hackathon_memory.finops.calls import Call, MemoryStore
from hackathon_memory.finops.meter import Meter, MeteredClient, Tags, metered_client
from hackathon_memory.llm import embeddings
from hackathon_memory.llm.gemini import CardFormatError, fill_card
from hackathon_memory.settings import Settings

FLASH = "gemini-3.8-flash"
PRO = "gemini-3.1-pro-preview"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
PAGE = f"Zed Widget lets a shop keep a public list of small facts. {PAGE_CANARY}"


class Clock:
    """Each look at the clock is 250 ms after the one before."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.25
        return self.now


def metered(fake: FakeGoogle, budget: Budget | None = None, **tags: str):
    store = MemoryStore()
    meter = Meter(store, "test", budget=budget, location="global", now=lambda: NOW)
    labels = Tags(purpose=tags.pop("purpose", "rewrite"), **tags)
    return MeteredClient(fake.client(), meter, labels, clock=Clock()), store


def test_a_call_leaves_one_line_with_what_google_reported() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake, run_id="run-1", item_ref="project-7")
    fill_card(client, PAGE, model=PRO, thinking_level="HIGH")

    [line] = store.calls()
    assert (line.environment, line.purpose, line.model) == ("test", "rewrite", PRO)
    assert (line.input_tokens, line.output_tokens, line.thinking_tokens) == (1000, 200, 300)
    assert line.thinking_level == "HIGH"
    assert line.location == "global"
    assert (line.run_id, line.item_ref) == ("run-1", "project-7")
    assert line.ok is True
    assert line.latency_ms == 250
    assert line.cost_usd == pytest.approx(0.008)  # 1000 in at 2.00, 500 out at 12.00
    assert line.called_at == NOW


def test_every_attempt_is_a_line_because_every_attempt_is_billed() -> None:
    fake = FakeGoogle(answer())
    fake.answer_queue = ["this is not json"]
    client, store = metered(fake)
    result = fill_card(client, PAGE, model=FLASH, thinking_level="LOW")
    assert result.attempts == 2
    assert len(store.calls()) == 2
    assert store.spent("test") == pytest.approx(2 * 0.002625)


def test_a_form_that_never_comes_out_right_is_still_paid_for_and_counted() -> None:
    fake = FakeGoogle("still not json")
    client, store = metered(fake)
    with pytest.raises(CardFormatError):
        fill_card(client, PAGE, model=FLASH, thinking_level="LOW", attempts=3)
    assert len(store.calls()) == 3


def test_an_embedding_call_is_counted_and_its_cost_is_not_guessed() -> None:
    client, store = metered(FakeGoogle(), purpose="embed_document")
    embeddings.embed_documents(client, ["a first text", "a second text"])
    [line] = store.calls()
    assert (line.purpose, line.model) == ("embed_document", "gemini-embedding-001")
    assert line.input_tokens == 14  # the fake reports 7 tokens for each text
    assert line.output_tokens == 0
    assert line.cost_usd is None  # the price of this model was not read from Google


def test_an_embedding_of_the_search_model_is_counted_with_its_price() -> None:
    client, store = metered(FakeGoogle(), purpose="embed_document")
    embeddings.embed_documents(client, ["a text", "another"], model=embeddings.SEARCH_MODEL)
    lines = store.calls()
    assert len(lines) == 2  # one request for each text
    assert {(line.model, line.input_tokens) for line in lines} == {("gemini-embedding-2", 9)}
    assert all(line.cost_usd == pytest.approx(9 * 0.20 / 1_000_000) for line in lines)
    assert PAGE_CANARY not in repr(lines)


def test_a_call_that_fails_gets_a_line_with_the_class_of_its_error_and_no_text() -> None:
    fake = FakeGoogle(answer())
    fake.fail_with = (403, "Permission denied for SECRET-CANARY-PROJECT")
    client, store = metered(fake)
    with pytest.raises(Exception, match="403"):
        fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    [line] = store.calls()
    assert line.ok is False
    assert line.error_kind == "ClientError"
    assert (line.input_tokens, line.cost_usd) == (0, 0.0)
    assert "SECRET-CANARY" not in repr(line)


def test_the_ledger_never_holds_the_text_that_was_sent_or_the_answer() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake)
    fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    kept = repr(store.calls())
    assert PAGE_CANARY not in kept
    assert "public list of facts" not in kept  # a text of the answer


# --------------------------------------------------------------------- the budget guard


def test_a_call_that_could_go_over_the_budget_is_never_sent() -> None:
    fake = FakeGoogle(answer())
    # The worst case of one call with Pro: up to 16,384 output tokens at 12 dollars a million.
    client, store = metered(fake, budget=Budget("test", 0.10))
    with pytest.raises(BudgetExceeded, match="was not made"):
        fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    assert fake.requests == []  # nothing left the computer
    assert store.calls() == []


def test_a_call_passes_when_there_is_room() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake, budget=Budget("test", 5.0))
    fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    assert len(fake.requests) == 1
    assert len(store.calls()) == 1


def test_the_guard_counts_what_was_already_spent() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake, budget=Budget("test", 1.0))
    # 0.85 dollars are already spent. One more call with Pro may cost about 0.20.
    store.add(Call("test", "rewrite", PRO, 0, output_tokens=70_834, called_at=NOW))
    with pytest.raises(BudgetExceeded):
        fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    assert fake.requests == []
    # A cheaper model still fits: its worst case is about 0.06.
    fill_card(client, PAGE, model=FLASH, thinking_level="LOW")
    assert len(fake.requests) == 1


def test_a_meter_refuses_the_budget_of_another_environment() -> None:
    with pytest.raises(ValueError, match="another environment"):
        Meter(MemoryStore(), "test", budget=Budget("prod", 1.0))


# ------------------------------------------------- a gate for who asks (the public copy)


def test_a_gate_sees_each_call_before_it_is_made_and_may_refuse_it() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake)
    seen: list[Tags] = []

    def gate(tags: Tags) -> None:
        seen.append(tags)
        if len(seen) > 1:
            raise BudgetExceeded("this visitor's allowance is used")

    behind = client.gated(gate).tagged(purpose="compare", item_ref="an-idea:order")
    fill_card(behind, PAGE, model=FLASH, thinking_level="LOW")
    with pytest.raises(BudgetExceeded, match="allowance is used"):
        fill_card(behind, PAGE, model=FLASH, thinking_level="LOW")
    assert seen == [Tags("compare", None, "an-idea:order")] * 2
    assert len(fake.requests) == 1 and len(store.calls()) == 1  # the refused call never left
    fill_card(client, PAGE, model=FLASH, thinking_level="LOW")  # the client without the gate
    assert len(fake.requests) == 2 and client.meter.gate is None


def test_a_gate_is_asked_only_for_a_call_that_the_budget_lets_through() -> None:
    """What a gate counts (a visitor's allowance) is never used up by a call that is not made."""
    fake = FakeGoogle(answer())
    client, _ = metered(fake, budget=Budget("test", 0.10))
    seen: list[Tags] = []
    with pytest.raises(BudgetExceeded, match="was not made"):
        fill_card(client.gated(seen.append), PAGE, model=PRO, thinking_level="HIGH")
    assert seen == [] and fake.requests == []


# ------------------------------------------------------- nothing goes around the count


def test_a_method_that_costs_money_and_is_not_known_is_refused() -> None:
    client, _ = metered(FakeGoogle())
    with pytest.raises(AttributeError, match="not counted by the meter"):
        client.models.generate_content_stream(model=PRO, contents="x")
    with pytest.raises(AttributeError, match="not counted by the meter"):
        _ = client.models.generate_images


def test_a_method_that_costs_nothing_passes_through() -> None:
    client, _ = metered(FakeGoogle())
    assert callable(client.models.count_tokens)


def test_the_same_meter_can_count_for_another_purpose() -> None:
    fake = FakeGoogle(answer())
    client, store = metered(fake, run_id="run-1")
    search = client.tagged(purpose="search", item_ref="idea-3")
    fill_card(search, PAGE, model=FLASH, thinking_level="LOW")
    fill_card(client, PAGE, model=PRO, thinking_level="HIGH")
    first, second = store.calls()
    assert (first.purpose, first.run_id, first.item_ref) == ("search", "run-1", "idea-3")
    assert (second.purpose, second.run_id, second.item_ref) == ("rewrite", "run-1", None)
    assert search.meter is client.meter


# --------------------------------------------------------------------- built from the settings


def test_the_metered_client_of_the_settings_uses_their_environment_and_budget() -> None:
    fake = FakeGoogle(answer())
    store = MemoryStore()
    settings = Settings(
        _env_file=None,
        google_cloud_location="global",
        llm_environment="prod",
        llm_budget_prod_usd=9.0,
        llm_budget_prod_per_day_usd=1.0,
    )
    client = metered_client(settings, "search", client=fake.client(), store=store, run_id="s-1")
    assert client.meter.environment == "prod"
    assert client.meter.budget == Budget("prod", 9.0, 1.0, 80)
    assert client.tags == Tags("search", "s-1", None)
    fill_card(client, PAGE, model=FLASH, thinking_level="LOW")
    [line] = store.calls("prod")
    assert (line.purpose, line.location) == ("search", "global")
