"""The quote check of design 6.3. Every page and every card here is invented."""

from __future__ import annotations

from googlefake import valid_form
from hackathon_memory.llm.card_form import CardFields
from hackathon_memory.read.quotes import (
    DROPPED,
    KEPT,
    NOT_FOUND,
    check_card,
    place_of,
    uniform,
)

PAGE = (
    "Zed Widget lets a shop keep a public list of small facts.\n\n"
    "It writes each fact to a topic on Hedera,   so that anyone can read the list.\n"
    "Built in two days by a team that ‘loves’ small shops — really."
)


def card(**changes: object) -> CardFields:
    return CardFields.model_validate(valid_form(**changes))


def field(checked, name: str):  # noqa: ANN001, ANN202
    return next(f for f in checked.fields if f.name == name)


def test_a_field_whose_quote_stands_in_the_page_is_kept() -> None:
    checked = check_card(card(), PAGE)
    what = field(checked, "what_it_does")
    assert (what.state, what.value, what.quotes, what.removed) == (
        KEPT,
        "It keeps a public list of facts.",
        ("Zed Widget lets a shop keep a public list of small facts.",),
        0,
    )


def test_spaces_case_quote_marks_and_dashes_are_made_uniform() -> None:
    quotes = [
        "it writes each fact to a topic on hedera, so that anyone can read the list",
        "a team that 'loves' small shops - really.",
    ]
    checked = check_card(card(for_whom={"label": "stated", "text": "Shops.", "quotes": quotes}),
                         PAGE)  # fmt: skip
    assert field(checked, "for_whom").quotes == tuple(quotes)


def test_a_quote_that_is_not_in_the_page_is_removed() -> None:
    quotes = ["Zed Widget lets a shop keep a public list of small facts.",
              "Zed Widget is used by ten thousand shops."]  # fmt: skip
    checked = check_card(card(hedera_services={"label": "stated", "text": "HCS.",
                                               "quotes": quotes}), PAGE)  # fmt: skip
    services = field(checked, "hedera_services")
    assert (services.state, len(services.quotes), services.removed) == (KEPT, 1, 1)


def test_a_field_with_no_quote_left_is_dropped_with_its_reason() -> None:
    invented = {"label": "stated", "text": "A bank.", "quotes": ["It is a bank for robots."]}
    empty = {"label": "inferred", "text": "Shops.", "quotes": []}
    checked = check_card(card(problem=invented, for_whom=empty), PAGE)
    problem, for_whom = field(checked, "problem"), field(checked, "for_whom")
    assert (problem.state, problem.value, problem.why) == (
        DROPPED, "", "no quote was found in the page"
    )  # fmt: skip
    assert (for_whom.state, for_whom.why) == (DROPPED, "no quote was given")
    assert [f.name for f in checked.dropped()] == ["for_whom", "problem"]


def test_a_quote_of_one_or_two_words_does_not_count() -> None:
    short = {"label": "stated", "text": "Hedera.", "quotes": ["Hedera", "small facts"]}
    assert field(check_card(card(hedera_services=short), PAGE), "hedera_services").state == DROPPED


def test_a_field_not_found_stays_empty_and_steps_and_category_keep_their_kind() -> None:
    checked = check_card(card(), PAGE)
    assert field(checked, "solution").state == NOT_FOUND
    assert field(checked, "how_it_works").value[0] == "A shop adds a fact."
    assert field(checked, "category").value == "Payments and remittance"
    no_steps = card(
        how_it_works={"label": "stated", "steps": ["One."], "quotes": ["Not here at all."]}
    )
    assert field(check_card(no_steps, PAGE), "how_it_works").value == []


def test_the_counts_and_the_stored_form() -> None:
    checked = check_card(card(), PAGE)
    assert (checked.quotes_given, checked.quotes_found) == (5, 5)
    stored = checked.as_json()
    assert set(stored) == {"what_it_does", "how_it_works", "for_whom", "hedera_services",
                           "category", "problem", "solution"}  # fmt: skip
    assert stored["problem"] == {"label": "not_found", "value": "", "quotes": [], "removed": 0,
                                 "state": "not_found", "why": ""}  # fmt: skip


def test_uniform() -> None:
    assert uniform("  A “B”—C  d\n") == 'a "b"-c d'


def test_the_place_of_a_quote_covers_its_letters_in_the_text() -> None:
    text = "Farmers scan a sack.  Buyers in\nEurope check “this” record."
    start, end = place_of('buyers in Europe check "this" record.', text)
    assert text[start:end] == "Buyers in\nEurope check “this” record"


def test_a_quote_that_is_not_in_the_text_has_no_place() -> None:
    assert place_of("buyers in Asia", "Buyers in Europe check it.") is None
    assert place_of(" . ", "Buyers in Europe check it.") is None


def test_a_letter_that_becomes_two_keeps_one_place() -> None:
    text = "Die Straße ist lang."
    start, end = place_of("strasse ist", text)
    assert text[start:end] == "Straße ist"
