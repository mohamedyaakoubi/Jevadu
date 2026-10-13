"""The quote check (design 6.3, design rule 3): every quote of the LLM must stand in the page.

The model is asked to copy, word for word, the sentences of the page that support each field.
This program checks each one. After the quote marks, dashes, spaces and letter case are made
uniform, the quote must be found in the text that the model was given, which the parser copied
word for word from the saved page (design rule 4).

| What the LLM gave | Result |
|---|---|
| "stated" or "inferred", with a quote that is found | the field is kept, with those quotes |
| a quote that is not found, or that has fewer than three words | that quote is removed |
| no quote left | the field is dropped, and the reason is kept |
| "not_found" | the field stays empty |

A quote of one or two words does not count: "Hedera" stands on almost every page and supports
nothing. The check catches invention. It does not catch a wrong reading of a real sentence: for
that, people grade a sample (design 13.2).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from hackathon_memory.llm.card_form import CardFields, CategoryField, Label, StepsField

MIN_WORDS = 3
KEPT, DROPPED, NOT_FOUND = "kept", "dropped", "not_found"
FIELDS = (
    "what_it_does",
    "how_it_works",
    "for_whom",
    "hedera_services",
    "category",
    "problem",
    "solution",
)
_SAME = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
     " ": " "}
)  # fmt: skip
_SPACES = re.compile(r"\s+")
_ENDS = " .,;:!?'\"()[]"


def uniform(text: str) -> str:
    """The text as the check compares it: one kind of quote mark and of dash, single spaces,
    small letters."""
    text = unicodedata.normalize("NFKC", text).translate(_SAME)
    return _SPACES.sub(" ", text).strip().casefold()


@dataclass(frozen=True)
class CheckedField:
    name: str
    label: str
    value: str | list[str] | None  # the text, the steps or the category; empty when not kept
    quotes: tuple[str, ...]  # the quotes that were found, as the model wrote them
    removed: int  # the quotes that were not found, or were too short
    state: str  # kept, dropped or not_found
    why: str = ""  # for a dropped field, in plain words


@dataclass(frozen=True)
class CheckedCard:
    fields: tuple[CheckedField, ...]

    @property
    def quotes_given(self) -> int:
        return sum(len(field.quotes) + field.removed for field in self.fields)

    @property
    def quotes_found(self) -> int:
        return sum(len(field.quotes) for field in self.fields)

    def dropped(self) -> list[CheckedField]:
        return [field for field in self.fields if field.state == DROPPED]

    def as_json(self) -> dict:
        """The checked fields, as they are stored with the card."""
        return {
            field.name: {
                "label": field.label,
                "value": field.value,
                "quotes": list(field.quotes),
                "removed": field.removed,
                "state": field.state,
                "why": field.why,
            }
            for field in self.fields
        }


def _value(field: object) -> str | list[str] | None:
    if isinstance(field, StepsField):
        return list(field.steps)
    if isinstance(field, CategoryField):
        return field.category.value
    return field.text  # type: ignore[attr-defined]


def _empty(value: str | list[str] | None) -> str | list[str] | None:
    return [] if isinstance(value, list) else (None if value is None else "")


def found_in(quote: str, page: str) -> bool:
    """True when the quote, made uniform and without the marks at its two ends, has at least
    three words and stands in the page made uniform."""
    words = uniform(quote).strip(_ENDS)
    return len(words.split()) >= MIN_WORDS and words in page


def _uniform_with_places(text: str) -> tuple[str, list[int]]:
    """The text made uniform letter by letter, and for each letter the place in the text of the
    letter it came from."""
    letters: list[str] = []
    places: list[int] = []
    for place, letter in enumerate(text):
        for one in unicodedata.normalize("NFKC", letter).translate(_SAME).casefold():
            if one.isspace():
                if not letters or letters[-1] == " ":
                    continue
                one = " "
            letters.append(one)
            places.append(place)
    while letters and letters[-1] == " ":
        letters.pop()
        places.pop()
    return "".join(letters), places


def place_of(quote: str, text: str) -> tuple[int, int] | None:
    """Where the quote stands in the text: the start and the end of the letters it covers, or
    None. The two are compared as the check compares them, so a sheet can show a quote in the
    page. A letter that becomes another one only next to its neighbours (a rare accent written
    as two signs) can hide a quote here that the check found."""
    words = uniform(quote).strip(_ENDS)
    if not words:
        return None
    letters, places = _uniform_with_places(text)
    start = letters.find(words)
    if start < 0:
        return None
    return places[start], places[start + len(words) - 1] + 1


def check_card(card: CardFields, page_text: str) -> CheckedCard:
    """Every field of the card, with its quotes checked against the text the model was given."""
    page = uniform(page_text)
    checked: list[CheckedField] = []
    for name in FIELDS:
        given = getattr(card, name)
        value = _value(given)
        if given.label is Label.NOT_FOUND:
            checked.append(CheckedField(name, given.label.value, _empty(value), (), 0, NOT_FOUND))
            continue
        found = tuple(quote for quote in given.quotes if found_in(quote, page))
        removed = len(given.quotes) - len(found)
        if found:
            checked.append(CheckedField(name, given.label.value, value, found, removed, KEPT))
            continue
        why = "no quote was given" if not given.quotes else "no quote was found in the page"
        checked.append(
            CheckedField(name, given.label.value, _empty(value), (), removed, DROPPED, why)
        )
    return CheckedCard(tuple(checked))
