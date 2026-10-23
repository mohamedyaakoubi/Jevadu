"""What the comparison should read, the card or the full text (evals/compare_inputs.py): the full
text of a page, the numbers of each input, and the page that a person reads. No model is asked.
Every page and answer is invented."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evals.compare_inputs import full_items, side_by_side, summary
from hackathon_memory.search.compare import ProjectComparison
from searchfakes import ids_of, three_projects


@pytest.mark.integration
def test_the_full_text_is_the_name_the_short_line_and_every_section(empty_database: str) -> None:
    database = three_projects(empty_database)
    ids = ids_of(database)
    items = full_items(database, [ids["Pebble Pay"], ids["Fern Vote"]])
    assert [item.number for item in items] == [1, 2]
    pebble = items[0].texts
    assert pebble["name"] == "Pebble Pay" and pebble["short_line"] == "Pebble Pay, invented."
    assert "A street vendor takes a coin." in pebble["page_text"]
    assert "A small web page asks the buyer to sign." in pebble["page_text"]  # the second section


def row(name: str, seconds: float, *, failed: bool = False, cost: float = 0.01) -> dict:
    return {"idea": 1, "input": name, "seconds": seconds, "failed": failed, "projects": 10,
            "answered": 0 if failed else 10, "input_tokens": 3000, "cost_usd": cost}  # fmt: skip


def test_each_input_gets_its_own_numbers() -> None:
    found = summary([row("cards", 6.0), row("full_text", 9.0), row("cards", 8.0),
                     row("full_text", 30.0, failed=True, cost=0.02)])  # fmt: skip
    assert found["cards"]["seconds_middle"] == 7.0 and found["cards"]["projects_answered"] == 20
    assert found["full_text"]["failed"] == 1 and found["full_text"]["cost_usd"] == 0.03


def test_the_page_to_read_shows_both_answers_and_escapes_every_text() -> None:
    idea = SimpleNamespace(number=3, words="pay a <b>vendor</b>")
    one = ProjectComparison(number=1, same="Both pay.", differs="One uses a card.",
                            fields_used=["what_it_does"])  # fmt: skip
    answers = {"cards": {7: one}, "full_text": {}}
    page = side_by_side([{"idea": idea, "ids": [7], "names": {7: "Pebble <Pay>"},
                          "answers": answers}], "2026-10-18")  # fmt: skip
    assert "pay a &lt;b&gt;vendor&lt;/b&gt;" in page and "Pebble &lt;Pay&gt;" in page
    assert "<b>Same</b> Both pay." in page and "<td>no answer</td>" in page
