"""The step that makes the cards of the LLM (design 4.1, 6.2, 6.3, 6.5).

    python -m hackathon_memory.pipeline cards --set evals/sets/tuning.json

For each full card of a set, the REWRITE layer (Gemini 3.1 Pro, design 11.3) fills the card form
from the text of the page. The quote check removes every quote that is not in that text and
drops a field with none left (design rule 3). The card is kept with its tokens and its cost. A
card whose text, model and instructions are the same as at its last making is passed over, and
costs nothing (design 6.5). Every call goes through the meter and its budget (design 11.4).

The step reads only the pages of a set. The run on every page waits for the maintainer's
decision on its cost (open question Q29), which comes after the cost of a page is measured on
the tuning set.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import httpx
from google.genai import errors as google_errors

from hackathon_memory.db.cards import CardStore
from hackathon_memory.db.runs import Run
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.llm.gemini import CardFormatError, fill_card
from hackathon_memory.pipeline.embed import GoogleIsAway
from hackathon_memory.read.quotes import KEPT, NOT_FOUND, check_card

STEP = "cards"
# Calls in a row that fail (after the client's own retries) and stop the step: Google is away.
MAX_ERRORS_IN_A_ROW = 3
FAILED_CALLS = (CardFormatError, google_errors.APIError, httpx.TransportError)


def make_cards(
    store: CardStore,
    client: Any,
    run: Run,
    *,
    pages: Collection[str],
    model: str,
    thinking_level: str,
    limit: int | None = None,
) -> None:
    """Make the card of each page of the set whose text changed, and count what was done."""
    known = store.known(model, INSTRUCTIONS_VERSION)
    inputs = store.inputs(pages)
    run.counts["pages_of_the_set"] = len(set(pages))
    run.counts["pages_without_a_full_card"] = len(set(pages) - {card.page for card in inputs})
    made = errors_in_a_row = 0
    for card in inputs:
        run.counts["projects"] += 1
        if known.get(card.project_id) == card.sha256:
            run.counts["the_same_as_before"] += 1
            continue
        if limit is not None and made >= limit:
            run.counts["left_for_later"] += 1
            continue
        try:
            result = fill_card(client, card.text, model=model, thinking_level=thinking_level)
        except FAILED_CALLS as error:
            # A CardFormatError says how the answer failed, never what it said; for any other
            # error only its kind is kept, since its text could repeat what was sent.
            why = str(error) if isinstance(error, CardFormatError) else type(error).__name__
            run.problem(card.page, why)
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                raise GoogleIsAway(f"the model failed {errors_in_a_row} times in a row") from None
            continue
        errors_in_a_row = 0
        checked = check_card(result.fields, card.text)
        store.save(card, result, checked)
        made += 1
        counts = run.counts
        counts["made"] += 1
        counts["quotes_given"] += checked.quotes_given
        counts["quotes_found"] += checked.quotes_found
        counts["fields_kept"] += sum(field.state == KEPT for field in checked.fields)
        counts["fields_not_found"] += sum(field.state == NOT_FOUND for field in checked.fields)
        counts["fields_dropped"] += len(checked.dropped())
        counts["input_tokens"] += result.usage.prompt_tokens
        counts["output_tokens"] += result.usage.output_tokens
        counts["thinking_tokens"] += result.usage.thought_tokens
        counts["cost_microdollars"] += round((result.cost_usd or 0.0) * 1_000_000)
        counts["asked_more_than_once"] += result.attempts > 1


def cards_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Pages of the set: {counts['pages_of_the_set']} "
        f"({counts['pages_without_a_full_card']} without a full card). "
        f"Cards made: {counts['made']}. The same as before: {counts['the_same_as_before']}."
    ]
    if counts["left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: {counts['left_for_later']}.")
    if counts["made"]:
        made = counts["made"]
        cost = counts["cost_microdollars"] / 1_000_000
        lines.append(
            f"Quotes: {counts['quotes_found']} of {counts['quotes_given']} found in the page. "
            f"Fields: {counts['fields_kept']} kept, {counts['fields_not_found']} not found on the "
            f"page, {counts['fields_dropped']} dropped by the quote check."
        )
        lines.append(
            f"Tokens: {counts['input_tokens']} in, {counts['output_tokens']} out, "
            f"{counts['thinking_tokens']} of thinking. Cost: ${cost:.4f}, "
            f"${cost / made:.4f} a card. Asked more than once: {counts['asked_more_than_once']}."
        )
    return lines
