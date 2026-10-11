"""The price book: the right price on the right day, and no price that was not read."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from hackathon_memory.finops.prices import PRICE_BOOK, Price, cost_usd, next_change, price_on

FLASH = "gemini-3.8-flash"
PRO = "gemini-3.1-pro-preview"
IN_2026 = date(2026, 10, 10)
IN_2027 = date(2027, 1, 1)
ROOT = Path(__file__).resolve().parents[1]


def test_the_prices_of_the_two_models_are_the_ones_that_were_read() -> None:
    flash = price_on(FLASH, IN_2026)
    pro = price_on(PRO, IN_2026)
    assert flash is not None and pro is not None
    assert (flash.input_usd, flash.output_usd, flash.cached_input_usd) == (0.75, 3.75, 0.075)
    assert (pro.input_usd, pro.output_usd, pro.cached_input_usd) == (2.00, 12.00, 0.20)
    assert (pro.long_above_tokens, pro.long_input_usd, pro.long_output_usd) == (200_000, 4.0, 18.0)


def test_flash_costs_double_from_the_first_of_january_2027() -> None:
    tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert cost_usd(FLASH, date(2026, 12, 31), **tokens) == pytest.approx(0.75 + 3.75)
    assert cost_usd(FLASH, IN_2027, **tokens) == pytest.approx(1.50 + 7.50)
    assert cost_usd(PRO, date(2026, 12, 31), input_tokens=1000) == cost_usd(
        PRO, IN_2027, input_tokens=1000
    )  # no change of date is known for Pro


def test_thinking_tokens_are_billed_as_output() -> None:
    with_thinking = cost_usd(PRO, IN_2026, input_tokens=0, output_tokens=100, thinking_tokens=900)
    as_output = cost_usd(PRO, IN_2026, input_tokens=0, output_tokens=1000)
    assert with_thinking == as_output == pytest.approx(0.012)


def test_a_long_prompt_is_billed_at_the_long_price_for_the_whole_request() -> None:
    at_the_line = cost_usd(PRO, IN_2026, input_tokens=200_000, output_tokens=1000)
    above = cost_usd(PRO, IN_2026, input_tokens=200_001, output_tokens=1000)
    assert at_the_line == pytest.approx((200_000 * 2.00 + 1000 * 12.00) / 1_000_000)
    assert above == pytest.approx((200_001 * 4.00 + 1000 * 18.00) / 1_000_000)
    # Flash has one price whatever the length.
    assert cost_usd(FLASH, IN_2026, input_tokens=900_000) == pytest.approx(0.675)


def test_cached_input_costs_a_tenth_and_never_more_than_the_prompt() -> None:
    plain = cost_usd(FLASH, IN_2026, input_tokens=10_000)
    half_cached = cost_usd(FLASH, IN_2026, input_tokens=10_000, cached_tokens=5_000)
    assert plain == pytest.approx(0.0075)
    assert half_cached == pytest.approx((5_000 * 0.75 + 5_000 * 0.075) / 1_000_000)
    all_cached = cost_usd(FLASH, IN_2026, input_tokens=10_000, cached_tokens=10_000)
    assert cost_usd(FLASH, IN_2026, input_tokens=10_000, cached_tokens=99_999) == all_cached


def test_a_batch_job_costs_half() -> None:
    standard = cost_usd(PRO, IN_2026, input_tokens=5000, output_tokens=700)
    batch = cost_usd(PRO, IN_2026, input_tokens=5000, output_tokens=700, batch=True)
    assert batch == pytest.approx(standard / 2)


def test_a_model_that_is_not_in_the_book_has_no_cost() -> None:
    assert cost_usd("gemini-9-unknown", IN_2026, input_tokens=1000) is None
    assert price_on("gemini-9-unknown", IN_2026) is None


def test_the_embedding_model_in_use_has_no_price_because_none_was_read() -> None:
    # Google's price page of 9 October 2026 does not list gemini-embedding-001. Its cost is not
    # guessed. When a price is read from Google, add a line to the book and change this test.
    assert cost_usd("gemini-embedding-001", IN_2026, input_tokens=1000) is None
    assert cost_usd("gemini-embedding-2", IN_2026, input_tokens=1_000_000) == pytest.approx(0.20)


def test_a_day_before_the_first_line_has_no_price() -> None:
    assert price_on(FLASH, date(2025, 12, 31)) is None
    assert cost_usd(FLASH, date(2025, 12, 31), input_tokens=1000) is None


def test_the_next_change_of_a_price_is_known() -> None:
    change = next_change(FLASH, IN_2026)
    assert change is not None and change.valid_from == IN_2027
    assert next_change(FLASH, IN_2027) is None
    assert next_change(PRO, IN_2026) is None


def test_a_new_line_takes_over_on_its_day_and_old_days_keep_the_old_price() -> None:
    book = (
        Price("m", date(2026, 1, 1), 1.0, 2.0),
        Price("m", date(2026, 6, 1), 3.0, 4.0),
    )
    assert cost_usd("m", date(2026, 5, 31), input_tokens=1_000_000, book=book) == 1.0
    assert cost_usd("m", date(2026, 6, 1), input_tokens=1_000_000, book=book) == 3.0


def test_every_line_of_the_book_says_when_it_was_read() -> None:
    assert all(isinstance(p.read_on, date) for p in PRICE_BOOK)
    models = [p.model for p in PRICE_BOOK]
    for model in set(models):
        days = [p.valid_from for p in PRICE_BOOK if p.model == model]
        assert days == sorted(days), f"the lines of {model} are not in the order of their days"


@pytest.mark.parametrize(("layer", "model"), [("rewrite", PRO), ("search", FLASH)])
def test_the_book_gives_the_cost_that_the_live_proof_recorded(layer: str, model: str) -> None:
    """The proof of 9 October 2026 measured real token counts and wrote a cost for each layer."""
    path = ROOT / "proofs" / "results" / "20261009T225549Z-google-models.json"
    measured = json.loads(path.read_text(encoding="utf-8"))["measurements"]["layers"][layer]
    assert measured["model"] == model
    cost = cost_usd(
        model,
        date(2026, 10, 9),
        input_tokens=measured["prompt_tokens"],
        output_tokens=measured["output_tokens"],
        thinking_tokens=measured["thought_tokens"],
    )
    assert cost == pytest.approx(measured["cost_usd"], abs=1e-6)
