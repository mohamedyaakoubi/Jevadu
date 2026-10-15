"""The filters of the search (design 8.2): which projects each one keeps, and what it offers."""

from __future__ import annotations

import json

import psycopg
import pytest

from hackathon_memory.search.filters import NOT_CHECKED, Facts, Filters, allowed, choices, facts
from searchfakes import ids_of, three_projects

ROWS = [
    Facts(1, "7", "Event A", "2026", "Payments and remittance", "proof_found", "active"),
    Facts(2, "7", "Event A", "2026", "", "no_id_given", "stopped"),
    Facts(3, "8", "Event B", "2025", "Health", "proof_found", "stopped"),
    Facts(4, "9", "Event C", "", "", "no_id_given", "unknown"),
]


def test_no_filter_keeps_every_project() -> None:
    assert allowed(ROWS, Filters()) is None


@pytest.mark.parametrize(
    ("chosen", "kept"),
    [
        (Filters(event="7"), [1, 2]),
        (Filters(year="2025"), [3]),
        (Filters(category="Health"), [3]),
        (Filters(proof="proof_found"), [1, 3]),
        (Filters(life="stopped"), [2, 3]),
        (Filters(proof="proof_found", life="stopped"), [3]),  # every filter must match
        (Filters(event="7", category="Health"), []),
    ],
)
def test_each_filter_keeps_the_projects_that_have_its_value(chosen: Filters, kept: list) -> None:
    assert allowed(ROWS, chosen) == kept


def test_the_choices_are_the_values_that_the_projects_have() -> None:
    offer = choices(ROWS)
    assert [(c.words, c.count) for c in offer.event] == [("Event A", 2), ("Event B", 1),
                                                          ("Event C", 1)]  # fmt: skip
    assert [(c.value, c.count) for c in offer.year] == [("2026", 2), ("2025", 1)]
    assert [c.value for c in offer.category] == ["Health", "Payments and remittance"]
    assert [(c.value, c.count) for c in offer.proof] == [("proof_found", 2), ("no_id_given", 2)]
    assert offer.proof[0].words == "proof found"
    assert [c.value for c in offer.life] == ["active", "stopped", "unknown"]  # the rule's order
    assert (offer.projects, offer.with_category) == (4, 2)
    assert offer.knows("year", "2025") and not offer.knows("year", "2019")


def test_the_facts_come_from_the_tables(empty_database: str) -> None:
    database = three_projects(empty_database)
    ids = ids_of(database)
    category = {"label": "inferred", "value": "Payments and remittance", "quotes": ["x"],
                "removed": 0, "state": "kept", "why": ""}  # fmt: skip
    dropped = {**category, "value": "Health", "state": "dropped"}
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE id = %s",
                     (ids["Pebble Pay"],))  # fmt: skip
        for name, field in (("Pebble Pay", category), ("Cedar Post", dropped)):
            conn.execute(
                "INSERT INTO cards (project_id, model, instructions_version, thinking_level, "
                "input_sha256, fields, answer, quotes_given, quotes_found, fields_dropped, "
                "attempts) VALUES (%s, 'm', 'v', 'HIGH', %s, %s, '{}', 1, 1, 0, 1)",
                (ids[name], "a" * 64, json.dumps({"category": field})),
            )
    rows = {row.project_id: row for row in facts(database, model="m", version="v")}
    assert rows[ids["Pebble Pay"]].category == "Payments and remittance"
    assert rows[ids["Cedar Post"]].category == ""  # a category the quote check dropped is none
    assert rows[ids["Pebble Pay"]].proof == "proof_found"
    assert rows[ids["Fern Vote"]].proof == NOT_CHECKED
    assert {row.event_name for row in rows.values()} == {"ETHGlobal Sample Event"}
    assert {row.life for row in rows.values()} == {"unknown"}  # no end and no dates of code
    assert {row.year for row in rows.values()} == {"2026"}  # from the start of the event
