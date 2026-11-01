"""The filters of the search (design 8.2): which projects each one keeps, and what it offers."""

from __future__ import annotations

import json
from dataclasses import replace

import psycopg
import pytest

from hackathon_memory.search.filters import (
    NO,
    NOT_CHECKED,
    YES,
    Facts,
    Filters,
    allowed,
    choices,
    counted_with,
    facts,
    joined,
    keep_chosen,
    values_of,
)
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
        (Filters(event="7|8"), [1, 2, 3]),  # several values of one filter: any of them
        (Filters(event="7|8", life="stopped"), [2, 3]),  # and every filter still
    ],
)
def test_each_filter_keeps_the_projects_that_have_its_value(chosen: Filters, kept: list) -> None:
    assert allowed(ROWS, chosen) == kept


def test_the_values_of_a_filter_have_one_text_whatever_their_order() -> None:
    """One choice has one address and one key of a kept order (1 November 2026)."""
    assert joined(["8|7", "7", " ", ""]) == "7|8"
    assert values_of("7|8") == ("7", "8") and values_of("") == ()
    assert Filters(event="7|8").values("event") == ("7", "8")


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


def test_a_chosen_value_stays_offered_when_the_closest_projects_lack_it() -> None:
    every = choices(ROWS)
    offer = choices(ROWS[:2])  # the closest to an idea: only Event A, with no project of 2025
    kept = keep_chosen(offer, every, Filters(event="8", year="2025"))
    assert [(c.value, c.count) for c in kept.event] == [("7", 2), ("8", 0)]
    assert [(c.value, c.count) for c in kept.year] == [("2026", 2), ("2025", 0)]
    assert kept.proof == offer.proof  # a filter not chosen is left as it was
    unknown = keep_chosen(offer, every, Filters(year="2019"))  # a value that no project has
    assert [c.value for c in unknown.year] == ["2026"]
    several = keep_chosen(offer, every, Filters(event="8|9|99"))  # each value apart; 99: none
    assert [(c.value, c.count) for c in several.event] == [("7", 2), ("8", 0), ("9", 0)]


def test_each_filter_counts_what_the_other_filters_keep() -> None:
    """The numbers follow the choice (1 November 2026): with Event A chosen, the years count only
    its projects, while the events still count them all, so that another event can be added."""
    offer = counted_with(ROWS, Filters(event="7"))
    assert [(c.value, c.count) for c in offer.year] == [("2026", 2)]
    assert [(c.value, c.count) for c in offer.event] == [("7", 2), ("8", 1), ("9", 1)]
    both = counted_with(ROWS, Filters(event="7", life="stopped"))
    assert [(c.value, c.count) for c in both.life] == [("active", 1), ("stopped", 1)]
    assert [(c.value, c.count) for c in both.event] == [("7", 1), ("8", 1)]
    assert counted_with(ROWS, Filters()) == choices(ROWS)


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
    rows = {row.project_id: row for row in facts(database, models=("m",), version="v")}
    assert rows[ids["Pebble Pay"]].category == "Payments and remittance"
    assert rows[ids["Cedar Post"]].category == ""  # a category the quote check dropped is none
    assert rows[ids["Pebble Pay"]].proof == "proof_found"
    assert rows[ids["Fern Vote"]].proof == NOT_CHECKED
    assert {row.event_name for row in rows.values()} == {"ETHGlobal Sample Event"}
    assert {row.life for row in rows.values()} == {"unknown"}  # no end and no dates of code
    assert {row.year for row in rows.values()} == {"2026"}  # from the start of the event


def test_the_organiser_is_ethglobal_or_the_one_of_its_winners_list(empty_database: str) -> None:
    """ETHGlobal for the events of its showcase; for another event, the organiser that its list of
    winners names, which the parser keeps as the sponsor of each entry's prize (30 October 2026)."""
    database = three_projects(empty_database)
    with psycopg.connect(database) as conn:
        (event,) = conn.execute(
            "INSERT INTO events (site, slug, name) "
            "VALUES ('hol.org', 'ai-2025', 'An AI hackathon') RETURNING id"
        ).fetchone()
        (entry,) = conn.execute(
            "INSERT INTO projects (site, page_url, site_key, entry_kind, event_id, name, "
            "short_line, prize_state, has_video, page_sha256, parser) VALUES ('hol.org', "
            "'https://hol.org/blog/winners#franky', 'franky', 'winner_entry', %s, 'Franky', "
            "'A line.', 'hedera_prize', false, %s, 'p') RETURNING id",
            (event, "b" * 64),
        ).fetchone()
        conn.execute(
            "INSERT INTO prizes (project_id, position, sponsor, track, award, pool, line) "
            "VALUES (%s, 1, 'Hashgraph Online', 'Agent Kit', 'First Place', false, "
            "'Hashgraph Online - Agent Kit - First Place')",
            (entry,),
        )
    rows = facts(database, models=("m",), version="v")
    by_id = {row.project_id: row for row in rows}
    assert by_id[entry].organiser == "Hashgraph Online"
    assert {row.organiser for row in rows if row.project_id != entry} == {"ETHGlobal"}
    offered = [(choice.value, choice.count) for choice in choices(rows).organiser]
    assert offered == [("ETHGlobal", 3), ("Hashgraph Online", 1)]
    assert allowed(rows, Filters(organiser="Hashgraph Online")) == [entry]


def test_the_mainnet_filter_keeps_the_teams_with_an_own_id_on_the_main_network() -> None:
    """The tag "Mainnet" of a card (design 7.5) as a filter, yes or no (31 October 2026)."""
    rows = [replace(ROWS[0], mainnet=YES), *ROWS[1:]]
    offered = [(choice.value, choice.words, choice.count) for choice in choices(rows).mainnet]
    assert offered == [(YES, "Yes", 1), (NO, "No", 3)]
    assert allowed(rows, Filters(mainnet=YES)) == [1]
    assert allowed(rows, Filters(mainnet=NO)) == [2, 3, 4]
    assert [choice.value for choice in choices(ROWS).mainnet] == [NO]  # none has it: no "Yes"


def test_the_prize_filter_keeps_the_winners_and_those_known_only_from_a_list() -> None:
    rows = [
        Facts(1, "7", "Event A", "2026", "", "proof_found", "active", prize="hedera_prize"),
        Facts(2, "7", "Event A", "2026", "", "no_id_given", "unknown", prize="hedera_prize",
              entry_kind="winner_entry"),
        Facts(3, "7", "Event A", "2026", "", "no_id_given", "stopped", prize="other_prize"),
        Facts(4, "7", "Event A", "2026", "", "no_id_given", "stopped"),
    ]  # fmt: skip
    assert allowed(rows, Filters(winner="hedera_prize")) == [1, 2]  # both won a Hedera prize
    assert allowed(rows, Filters(winner="winners_list")) == [2]
    assert allowed(rows, Filters(winner="winners_list", life="stopped")) == []
    assert allowed(rows, Filters(winner="other_prize")) == [3]  # another sponsor's prize only
    offered = choices(rows).winner
    assert [(one.value, one.words, one.count) for one in offered] == [
        ("hedera_prize", "Won a Hedera prize", 2),
        ("other_prize", "Won another sponsor's prize", 1),
        ("winners_list", "Winners' list only", 1),
    ]
