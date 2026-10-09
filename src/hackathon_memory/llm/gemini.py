"""Gemini 3.8 Flash fills the card form (design 4.1, 6.2, 11.3; design rule 7).

Facts from Google's own pages, read on 9 October 2026:

* The model id is `gemini-3.8-flash`. It is generally available and offered in the locations
  `global`, `us` and `eu`.
* `temperature`, `top_k` and `top_p` are ignored by the backend. Google says to remove them, so
  they are not sent.
* Thinking levels are LOW, MEDIUM (the default) and HIGH. MINIMAL is refused. Thinking tokens are
  counted and billed as output. The job here is to read short English text and fill a form, so
  the level is LOW: the cost and the delay are smaller, and Test 1 (design 13.2) will show if
  the quality suffers.
* Price: 0.75 dollars per million tokens in and 3.75 out until 31 December 2026, then double.
"""

from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types
from pydantic import ValidationError

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION, SYSTEM_INSTRUCTIONS, CardFields

MODEL = "gemini-3.8-flash"
LOCATIONS = ("global", "us", "eu")
THINKING_LEVEL = types.ThinkingLevel.LOW
MAX_OUTPUT_TOKENS = 8192  # thinking tokens count against this limit too

# Dollars per million tokens, until 31 December 2026. After that the prices double.
PRICE_IN = 0.75
PRICE_OUT = 3.75


class CardFormatError(Exception):
    """The answer is not a valid form. The message never holds text of the page or of the answer."""


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    total_tokens: int

    @property
    def cost_usd(self) -> float:
        """The cost of this call. Thinking tokens are billed as output."""
        return (
            self.prompt_tokens * PRICE_IN + (self.output_tokens + self.thought_tokens) * PRICE_OUT
        ) / 1_000_000


@dataclass(frozen=True)
class CardResult:
    fields: CardFields
    usage: Usage
    model: str
    instructions_version: str


def check_location(location: str) -> None:
    if location not in LOCATIONS:
        raise CardFormatError(
            f"{MODEL} is offered in the locations {', '.join(LOCATIONS)} (Google's model page, "
            f"9 October 2026). GOOGLE_CLOUD_LOCATION is '{location}'. Use 'global'."
        )


def fill_card(client: genai.Client, page_text: str) -> CardResult:
    """One call. The answer is checked against the form; an invalid answer is an error."""
    if not page_text.strip():
        raise CardFormatError("The page text is empty.")
    response = client.models.generate_content(
        model=MODEL,
        contents=page_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=CardFields,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    text = response.text
    if not text:
        reason = None
        if response.candidates:
            reason = response.candidates[0].finish_reason
        raise CardFormatError(f"The model returned no text (finish reason: {reason}).")
    try:
        fields = CardFields.model_validate_json(text)
    except ValidationError as error:
        # The details of a pydantic error repeat the input. Only places and kinds are kept.
        problems = sorted(
            {f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in error.errors()}
        )
        raise CardFormatError(
            f"The answer is not a valid form: {'; '.join(problems[:6])}"
        ) from None
    meta = response.usage_metadata
    usage = Usage(
        prompt_tokens=(meta.prompt_token_count or 0) if meta else 0,
        output_tokens=(meta.candidates_token_count or 0) if meta else 0,
        thought_tokens=(meta.thoughts_token_count or 0) if meta else 0,
        total_tokens=(meta.total_token_count or 0) if meta else 0,
    )
    return CardResult(
        fields=fields, usage=usage, model=MODEL, instructions_version=INSTRUCTIONS_VERSION
    )
