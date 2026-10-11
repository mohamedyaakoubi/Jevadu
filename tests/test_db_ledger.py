"""The store of ledger facts and proof results, on a real PostgreSQL. Everything is invented."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, project_page
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import NO_ID_GIVEN, PROOF_FOUND, WINDOW_NOT_KNOWN
from hackathon_memory.db.ledger import IdToCheck, LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import TOPIC

pytestmark = pytest.mark.integration

ASKED = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
MADE = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
SINCE = datetime(2026, 2, 4, 16, 0, tzinfo=UTC)
UNTIL = datetime(2026, 3, 22, 23, 59, tzinfo=UTC)
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"

TOPIC_FACTS = LedgerFacts(
    entity_id="0.0.3456789",
    network="testnet",
    asked_at=ASKED,
    found=True,
    kind=TOPIC,
    ledger_id="0.0.3456789",
    created_at=MADE,
    deleted=False,
    first_activity_at=MADE,
    last_activity_at=MADE,
    activity_count=49,
    empty=False,
    details={},
)
NOT_THERE = LedgerFacts("0.0.3456789", "mainnet", ASKED, found=False)


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


@pytest.fixture
def with_projects(database: str) -> str:
    """Two projects: one whose page gives two ids, and one whose page gives none."""
    projects = ProjectStore(database)
    first = project_page(
        description="<p>The log is the topic 0.0.3456789. The coin is 0.0.2345678.</p>",
        made="<p>Both live on the test network.</p>",
    )
    projects.save(read_project_page(first, PROJECT_PAGE), "a" * 64)
    second = project_page(name="Quartz Notes", slug="quartz-notes", short_id="q3w4e")
    projects.save(read_project_page(second, SECOND_PAGE), "b" * 64)
    return database


def rows(database: str, query: str, *values: object) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(query, values).fetchall()


# --------------------------------------------------------------------- the facts


def test_the_facts_of_an_id_come_back_as_they_were_kept(database: str) -> None:
    store = LedgerStore(database)
    assert store.facts("0.0.3456789", "testnet") is None
    token = replace(
        TOPIC_FACTS,
        entity_id="0.0.2345678",
        kind="token",
        ledger_id="0.0.2345678",
        activity_count=None,
        details={"type": "FUNGIBLE_COMMON", "total_supply": "1000000", "name": "Pebble"},
    )
    store.save_facts(TOPIC_FACTS)
    store.save_facts(token)
    assert store.facts("0.0.3456789", "testnet") == TOPIC_FACTS
    assert store.facts("0.0.2345678", "testnet") == token
    assert store.facts("0.0.3456789", "mainnet") is None  # another network, another thing


def test_not_found_is_an_answer_that_is_kept_too(database: str) -> None:
    store = LedgerStore(database)
    store.save_facts(NOT_THERE)
    assert store.facts("0.0.3456789", "mainnet") == NOT_THERE


def test_a_newer_answer_replaces_the_older_one(database: str) -> None:
    store = LedgerStore(database)
    store.save_facts(TOPIC_FACTS)
    store.save_use("0.0.3456789", "testnet", SINCE, UNTIL, True, ASKED)
    later = replace(TOPIC_FACTS, asked_at=datetime(2026, 10, 18, tzinfo=UTC), activity_count=60)
    store.save_facts(later)
    assert store.facts("0.0.3456789", "testnet") == later
    assert rows(database, "SELECT count(*) FROM ledger_facts") == [(1,)]
    # What was asked about the older state is gone with it.
    assert store.use("0.0.3456789", "testnet", SINCE, UNTIL) is None


def test_the_use_inside_a_window_is_kept_for_that_window(database: str) -> None:
    store = LedgerStore(database)
    store.save_facts(TOPIC_FACTS)
    assert store.use("0.0.3456789", "testnet", SINCE, UNTIL) is None  # never asked
    store.save_use("0.0.3456789", "testnet", SINCE, UNTIL, False, ASKED)
    assert store.use("0.0.3456789", "testnet", SINCE, UNTIL) is False
    store.save_use("0.0.3456789", "testnet", SINCE, UNTIL, True, ASKED)  # asked again
    assert store.use("0.0.3456789", "testnet", SINCE, UNTIL) is True
    assert store.use("0.0.3456789", "testnet", SINCE, datetime(2026, 4, 1, tzinfo=UTC)) is None


@pytest.mark.parametrize(
    "bad",
    [
        replace(TOPIC_FACTS, kind=None),  # found, and no kind
        replace(NOT_THERE, kind=TOPIC),  # not found, and a kind
        replace(NOT_THERE, created_at=MADE),  # not found, and a day it was made
        replace(TOPIC_FACTS, network="ethereum"),
        replace(TOPIC_FACTS, entity_id="0.0.98x"),
        replace(TOPIC_FACTS, activity_count=-1),
        replace(TOPIC_FACTS, first_activity_at=UNTIL, last_activity_at=SINCE),
    ],
)
def test_the_table_refuses_facts_that_make_no_sense(database: str, bad: LedgerFacts) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        LedgerStore(database).save_facts(bad)
    assert rows(database, "SELECT count(*) FROM ledger_facts") == [(0,)]


# --------------------------------------------------------------------- the check


def test_every_id_of_every_project_is_given_with_its_event(with_projects: str) -> None:
    with psycopg.connect(with_projects) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
    ids = LedgerStore(with_projects).ids_to_check()
    assert [(i.entity_id, i.network, i.said_kind) for i in ids] == [
        ("0.0.3456789", None, TOPIC),
        ("0.0.2345678", None, None),
    ]
    assert all(isinstance(i, IdToCheck) and i.project_id == ids[0].project_id for i in ids)
    assert ids[0].event_starts_at == datetime(2026, 3, 6, 16, 0, tzinfo=UTC)
    assert ids[0].event_ends_on == date(2026, 3, 8)


def test_a_project_is_not_checked_until_the_check_has_looked_at_it(with_projects: str) -> None:
    store = LedgerStore(with_projects)
    assert store.proof_counts() == {"not_checked": 2}
    assert store.mark_projects_with_no_id() == 1
    assert store.proof_counts() == {"not_checked": 1, NO_ID_GIVEN: 1}


def test_the_results_of_a_project_are_kept_and_replaced(with_projects: str) -> None:
    store = LedgerStore(with_projects)
    topic, coin = store.ids_to_check()
    store.save_checks(
        topic.project_id,
        {
            topic.hedera_id: {"testnet": PROOF_FOUND, "mainnet": "another_kind"},
            coin.hedera_id: {"testnet": "not_found", "mainnet": "not_found"},
        },
        PROOF_FOUND,
    )
    assert rows(
        with_projects,
        "SELECT h.entity_id, c.network, c.status FROM id_checks c "
        "JOIN hedera_ids h ON h.id = c.hedera_id ORDER BY 1, 2",
    ) == [
        ("0.0.2345678", "mainnet", "not_found"),
        ("0.0.2345678", "testnet", "not_found"),
        ("0.0.3456789", "mainnet", "another_kind"),
        ("0.0.3456789", "testnet", PROOF_FOUND),
    ]
    assert store.proof_counts() == {PROOF_FOUND: 1, "not_checked": 1}

    store.save_checks(
        topic.project_id, {topic.hedera_id: {"testnet": WINDOW_NOT_KNOWN}}, WINDOW_NOT_KNOWN
    )
    assert rows(with_projects, "SELECT network, status FROM id_checks") == [
        ("testnet", WINDOW_NOT_KNOWN)
    ]
    assert store.proof_counts() == {WINDOW_NOT_KNOWN: 1, "not_checked": 1}


def test_a_page_that_is_read_again_sets_its_project_back_to_not_checked(with_projects: str) -> None:
    store = LedgerStore(with_projects)
    topic, _ = store.ids_to_check()
    store.save_checks(topic.project_id, {topic.hedera_id: {"testnet": PROOF_FOUND}}, PROOF_FOUND)

    changed = project_page(description="<p>No id is named any more.</p>")
    ProjectStore(with_projects).save(read_project_page(changed, PROJECT_PAGE), "c" * 64)

    assert store.proof_counts() == {"not_checked": 2}
    assert rows(with_projects, "SELECT count(*) FROM id_checks") == [(0,)]  # gone with the ids


def test_the_tables_refuse_a_status_that_does_not_exist(with_projects: str) -> None:
    store = LedgerStore(with_projects)
    topic, _ = store.ids_to_check()
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save_checks(topic.project_id, {topic.hedera_id: {"testnet": "very good"}}, "x")
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save_checks(topic.project_id, {}, "very good")
    assert store.proof_counts() == {"not_checked": 2}  # and nothing was half written
