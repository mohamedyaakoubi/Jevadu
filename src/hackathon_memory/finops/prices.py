"""The price book: what Google charges for each model, and from which day.

Read on 10 October 2026 from Google's page "Gemini Developer API pricing" (last updated 9 October
2026), which gives the same list prices as the global endpoint of the Agent Platform (Vertex AI):

* Gemini 3.8 Flash: 0.75 dollars for a million input tokens and 3.75 for a million output tokens
  until 31 December 2026. From 1 January 2027 both double: 1.50 and 7.50.
* Gemini 3.1 Pro (preview): 2.00 and 12.00 for a prompt of up to 200,000 tokens. A longer prompt
  costs 4.00 and 18.00, for the whole request and not only for the part above the line.
* Output includes the thinking tokens.
* Input that Google serves from its cache costs a tenth: 0.075 for Flash (0.15 from 2027), 0.20
  for Pro (0.40 for a long prompt).
* A batch job costs half.
* Gemini Embedding 2 costs 0.20 for a million input tokens. The page does not list
  gemini-embedding-001, which this project uses, so its price is NOT KNOWN here and its cost is
  never guessed.

A price that is not in this book gives no cost: the call is counted, and its cost is "not known".
When Google changes a price, add a line with the new day. Never edit an old line: the old calls
were billed at the old price.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

READ_ON = date(2026, 10, 10)
SOURCE = "Google, Gemini Developer API pricing (ai.google.dev/gemini-api/docs/pricing)"
PER = 1_000_000  # prices are for a million tokens
BATCH_FACTOR = 0.5  # a batch job costs half of the standard price


@dataclass(frozen=True)
class Price:
    """What one model costs from `valid_from` on, in dollars for a million tokens."""

    model: str
    valid_from: date
    input_usd: float
    output_usd: float  # thinking tokens are billed as output
    cached_input_usd: float | None = None
    # A prompt above this many tokens is billed at the "long" prices, for the whole request.
    long_above_tokens: int | None = None
    long_input_usd: float | None = None
    long_output_usd: float | None = None
    long_cached_input_usd: float | None = None
    read_on: date = READ_ON


# Oldest first for each model. The line that is used is the last one that has begun.
PRICE_BOOK: tuple[Price, ...] = (
    Price("gemini-3.8-flash", date(2026, 1, 1), 0.75, 3.75, cached_input_usd=0.075),
    Price("gemini-3.8-flash", date(2027, 1, 1), 1.50, 7.50, cached_input_usd=0.15),
    Price(
        "gemini-3.1-pro-preview",
        date(2026, 1, 1),
        2.00,
        12.00,
        cached_input_usd=0.20,
        long_above_tokens=200_000,
        long_input_usd=4.00,
        long_output_usd=18.00,
        long_cached_input_usd=0.40,
    ),
    Price("gemini-embedding-2", date(2026, 1, 1), 0.20, 0.0),
)


def price_on(model: str, day: date, book: tuple[Price, ...] = PRICE_BOOK) -> Price | None:
    """The price of the model on that day, or None when the book does not know the model."""
    known = [p for p in book if p.model == model and p.valid_from <= day]
    return max(known, key=lambda p: p.valid_from) if known else None


def cost_usd(
    model: str,
    day: date,
    *,
    input_tokens: int,
    output_tokens: int = 0,
    thinking_tokens: int = 0,
    cached_tokens: int = 0,
    batch: bool = False,
    book: tuple[Price, ...] = PRICE_BOOK,
) -> float | None:
    """The cost of one call in dollars, or None when the price of the model is not known.

    `input_tokens` is the whole prompt, the cached part included. The cached part is billed at
    the cache price and the rest at the input price. Thinking tokens are billed as output.
    """
    price = price_on(model, day, book)
    if price is None:
        return None
    long = price.long_above_tokens is not None and input_tokens > price.long_above_tokens
    price_in = (
        price.long_input_usd if long and price.long_input_usd is not None else price.input_usd
    )
    price_out = (
        price.long_output_usd if long and price.long_output_usd is not None else price.output_usd
    )
    price_cached = (
        price.long_cached_input_usd
        if long and price.long_cached_input_usd is not None
        else price.cached_input_usd
    )
    cached = min(max(cached_tokens, 0), input_tokens)
    if price_cached is None:
        price_cached = price_in  # no cache price is known, so nothing is assumed to be cheaper
    total = (
        (input_tokens - cached) * price_in
        + cached * price_cached
        + (output_tokens + thinking_tokens) * price_out
    ) / PER
    if batch:
        total *= BATCH_FACTOR
    return round(total, 8)


def next_change(model: str, day: date, book: tuple[Price, ...] = PRICE_BOOK) -> Price | None:
    """The next line of the book for this model that begins after `day`, if there is one."""
    later = [p for p in book if p.model == model and p.valid_from > day]
    return min(later, key=lambda p: p.valid_from) if later else None
