"""Gemini fills the card form (design 4.1, 6.2, 11.3; design rule 7).

There are two Gemini layers, chosen by the maintainer on 9 October 2026:

* the REWRITE layer reads a project page and fills the card. It uses Gemini 3.1 Pro, for the
  quality of the rewrite;
* the SEARCH layer, which compares the closest projects with the idea of the user, uses
  Gemini 3.8 Flash. The search form is built in Phase D. Until then the same card form is used
  to check that this model, its location and its thinking level work.

The models and their thinking levels are settings (GEMINI_REWRITE_*, GEMINI_SEARCH_*).

Facts from Google's own pages, read on 9 October 2026:

* `gemini-3.8-flash` is generally available, offered in the locations `global`, `us` and `eu`.
  `gemini-3.1-pro-preview` is a PUBLIC PREVIEW model, offered only in `global`. A preview model
  can change or be retired, and it is under Google's Pre-GA terms.
* Both take the thinking levels LOW, MEDIUM and HIGH. MINIMAL is refused. The default is MEDIUM
  for 3.8 Flash and HIGH for 3.1 Pro. The old thinking budget is deprecated for Gemini 3 and is an
  error when sent with a level, so it is never sent.
* `temperature`, `top_k` and `top_p` are ignored by the backend, and Google says to remove them,
  so they are not sent.
* Thinking tokens are billed as output tokens.
* The prices are in the price book, finops/prices.py, with the day each one begins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from google import genai
from google.genai import types
from pydantic import ValidationError

from hackathon_memory.finops import prices
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION, SYSTEM_INSTRUCTIONS, CardFields

THINKING_LEVELS = ("LOW", "MEDIUM", "HIGH")
MAX_OUTPUT_TOKENS = 16384  # thinking tokens count against this limit too, and HIGH thinks a lot

# Where each model is offered (Google's model pages, 9 October 2026). A model that is not in
# this table is not checked: the first call shows if the location is wrong.
LOCATIONS: dict[str, tuple[str, ...]] = {
    "gemini-3.8-flash": ("global", "us", "eu"),
    "gemini-3.1-pro-preview": ("global",),
}


# A model that stops for one of these reasons will stop again: asking again is a waste of money.
_NO_RETRY = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY", "RECITATION"}
DEFAULT_ATTEMPTS = 3  # the first try and two more


class CardFormatError(Exception):
    """The answer is not a valid form. The message never holds text of the page or of the answer.

    `usage` is the tokens of all the attempts that were made: a failed attempt is billed too.
    """

    def __init__(self, message: str, usage: Usage | None = None, attempts: int = 0) -> None:
        super().__init__(message)
        self.usage = usage
        self.attempts = attempts


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    total_tokens: int

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.output_tokens + other.output_tokens,
            self.thought_tokens + other.thought_tokens,
            self.total_tokens + other.total_tokens,
        )

    def cost_usd(self, model: str, on: date | None = None) -> float | None:
        """The cost of this call on that day, or None when the price of the model is not known.

        The day is today when none is given. Thinking tokens are billed as output.
        """
        return prices.cost_usd(
            model,
            on or prices.today(),
            input_tokens=self.prompt_tokens,
            output_tokens=self.output_tokens,
            thinking_tokens=self.thought_tokens,
        )


@dataclass(frozen=True)
class CardResult:
    fields: CardFields
    usage: Usage
    model: str
    thinking_level: str
    instructions_version: str
    attempts: int = 1  # how many calls it took; the usage above counts all of them

    @property
    def cost_usd(self) -> float | None:
        return self.usage.cost_usd(self.model)


def check_location(model: str, location: str) -> None:
    offered = LOCATIONS.get(model)
    if offered is not None and location not in offered:
        raise CardFormatError(
            f"{model} is offered in the locations {', '.join(offered)} (Google's model page, "
            f"9 October 2026). GOOGLE_CLOUD_LOCATION is '{location}'. Use 'global'."
        )


def _usage_of(response: object) -> Usage:
    meta = getattr(response, "usage_metadata", None)
    return Usage(
        prompt_tokens=(meta.prompt_token_count or 0) if meta else 0,
        output_tokens=(meta.candidates_token_count or 0) if meta else 0,
        thought_tokens=(meta.thoughts_token_count or 0) if meta else 0,
        total_tokens=(meta.total_token_count or 0) if meta else 0,
    )


def _finish_reason(response: object) -> str | None:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    reason = candidates[0].finish_reason
    return getattr(reason, "name", None) or (str(reason) if reason is not None else None)


def _parse(text: str, finish: str | None) -> CardFields:
    """The form, or a CardFormatError that says HOW the answer failed, not what it said."""
    try:
        json.loads(text)
    except ValueError as error:
        place = getattr(error, "pos", None)
        raise CardFormatError(
            f"The answer is not JSON ({getattr(error, 'msg', 'invalid')}, at character {place} "
            f"of {len(text)}; finish reason {finish})"
        ) from None
    try:
        return CardFields.model_validate_json(text)
    except ValidationError as error:
        # The details of a pydantic error repeat the input. Only places and kinds are kept.
        problems = sorted(
            {f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in error.errors()}
        )
        raise CardFormatError(
            f"The answer is not a valid form: {'; '.join(problems[:6])} (finish reason {finish})"
        ) from None


def fill_card(
    client: genai.Client,
    page_text: str,
    *,
    model: str,
    thinking_level: str,
    attempts: int = DEFAULT_ATTEMPTS,
) -> CardResult:
    """Fill the card. The answer is checked against the form.

    A model sometimes returns text that is not valid JSON (seen on the first live run, backlog
    entry 06), so a bad answer is asked for again, up to `attempts` calls in all. Every attempt is
    billed, so the usage of the result counts all of them. A stop for a safety reason is not
    repeated. If every attempt fails, the error says so and carries the tokens that were spent.
    """
    if thinking_level not in THINKING_LEVELS:
        raise CardFormatError(f"The thinking level must be one of {', '.join(THINKING_LEVELS)}.")
    if not page_text.strip():
        raise CardFormatError("The page text is empty.")
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        response_mime_type="application/json",
        response_schema=CardFields,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[thinking_level]),
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    spent = Usage(0, 0, 0, 0)
    failures: list[str] = []
    for attempt in range(1, max(1, attempts) + 1):
        response = client.models.generate_content(model=model, contents=page_text, config=config)
        spent = spent + _usage_of(response)
        finish = _finish_reason(response)
        try:
            if not response.text:
                raise CardFormatError(f"The model returned no text (finish reason: {finish}).")
            fields = _parse(response.text, finish)
        except CardFormatError as error:
            failures.append(f"attempt {attempt}: {error}")
            if finish in _NO_RETRY:
                break
            continue
        return CardResult(
            fields=fields,
            usage=spent,
            model=model,
            thinking_level=thinking_level,
            instructions_version=INSTRUCTIONS_VERSION,
            attempts=attempt,
        )
    tries = len(failures)
    raise CardFormatError(
        f"No valid form after {tries} attempt(s). " + " | ".join(failures),
        usage=spent,
        attempts=tries,
    )
