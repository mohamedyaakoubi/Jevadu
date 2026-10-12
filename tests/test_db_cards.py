"""The store of the cards of the LLM (migration 0010). Every project here is invented."""

from __future__ import annotations

import psycopg
import pytest

from googlefake import valid_form
from hackathon_memory.db.cards import CardStore, card_text
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.llm.card_form import CardFields
from hackathon_memory.llm.gemini import CardResult, Usage
from hackathon_memory.parse.winner_entries import entries_from_records
from hackathon_memory.read.quotes import check_card
from searchfakes import PAGES, three_projects

pytestmark = pytest.mark.integration

PRO = "gemini-3.1-pro-preview"
VERSION = "card-form-test"


@pytest.fixture
def database(empty_database: str) -> str:
    three_projects(empty_database)
    record = {
        "kind": "winner_entry", "name": "Moss Map", "event": "Invented Winners 2024",
        "description_as_published": "Maps moss.", "source_url": "https://example.test/winners",
    }  # fmt: skip
    [entry] = entries_from_records([record], site="example.test", source="a test")
    ProjectStore(empty_database).save(entry.page, entry.sha256)
    return empty_database


def result(**changes: object) -> CardResult:
    return CardResult(
        fields=CardFields.model_validate(valid_form(**changes)),
        usage=Usage(1000, 200, 300, 1500),
        model=PRO,
        thinking_level="HIGH",
        instructions_version=VERSION,
    )


def test_the_text_of_a_card_is_the_name_the_short_line_and_the_sections() -> None:
    text = card_text("Pebble Pay", " A coin for vendors. ",
                     [("Project Description", "It pays."), ("", "No title here.")])  # fmt: skip
    assert (
        text
        == "Pebble Pay\n\nA coin for vendors.\n\nProject Description\nIt pays.\n\nNo title here."
    )


def test_only_full_cards_are_read_and_the_pages_can_be_chosen(database: str) -> None:
    store = CardStore(database)
    inputs = store.inputs()
    assert len(inputs) == 3  # the winner entry gets no card of the LLM
    assert all("Moss Map" not in card.text for card in inputs)
    first = inputs[0]
    assert first.text.split("\n\n")[0] in {name for name, _ in PAGES.values()}
    assert store.inputs([first.page]) == [first]
    assert store.inputs([]) == []


def test_a_card_is_kept_once_for_each_model_and_version(database: str) -> None:
    store = CardStore(database)
    card = store.inputs()[0]
    first = result()
    store.save(card, first, check_card(first.fields, card.text))
    assert store.known(PRO, VERSION) == {card.project_id: card.sha256}
    second = result(
        problem={"label": "stated", "text": "Invented.", "quotes": ["Not on the page."]}
    )
    checked = check_card(second.fields, card.text)
    store.save(card, second, checked)  # in place of the first
    counts = store.counts(PRO, VERSION)
    assert counts["cards"] == 1
    assert counts["fields_dropped"] == len(checked.dropped()) >= 1
    assert (counts["quotes_given"], counts["quotes_found"]) == (
        checked.quotes_given, checked.quotes_found
    )  # fmt: skip
    with psycopg.connect(database) as conn:
        fields, answer, cost = conn.execute(
            "SELECT fields, answer, cost_usd FROM cards WHERE project_id = %s", (card.project_id,)
        ).fetchone()
    assert fields["problem"]["state"] == "dropped"
    assert answer["problem"]["quotes"] == ["Not on the page."]  # the answer before the check
    assert float(cost) == pytest.approx(second.cost_usd)
    assert store.known("another-model", VERSION) == {}
