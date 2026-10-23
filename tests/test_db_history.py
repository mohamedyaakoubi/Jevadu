"""The store of the histories of the own Hedera IDs (db/history.py), on a real PostgreSQL.
Everything is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, project_page
from hackathon_memory.check.history import CONSENSUS, TOKENS, History
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import ANOTHER_KIND, PROOF_FOUND
from hackathon_memory.db.history import HistoryStore, IdToRead, story_of_project
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import TOKEN, TOPIC

pytestmark = pytest.mark.integration

ASKED = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
ONE, TWO = "1780000000.000000001", "1780000060.000000002"
MADE = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def judge_every_id(database: str, status: str) -> None:
    """Give every ID of every project one status on the test network."""
    ledger = LedgerStore(database)
    by_project: dict[int, dict[int, dict[str, str]]] = {}
    for item in ledger.ids_to_check():
        by_project.setdefault(item.project_id, {})[item.hedera_id] = {"testnet": status}
    for project_id, checks in by_project.items():
        ledger.save_checks(project_id, checks, status)


@pytest.fixture
def database(empty_database: str) -> str:
    """Two projects: the first names a topic and a coin, and the second names the same coin."""
    migrate(empty_database)
    projects = ProjectStore(empty_database)
    first = project_page(
        description="<p>The log is the topic 0.0.3456781. The coin is 0.0.2345671.</p>"
    )
    projects.save(read_project_page(first, PROJECT_PAGE), "a" * 64)
    second = project_page(
        name="Quartz Notes", slug="quartz-notes", short_id="q3w4e",
        description="<p>We pay with the coin 0.0.2345671.</p>",
    )  # fmt: skip
    projects.save(read_project_page(second, SECOND_PAGE), "b" * 64)
    ledger = LedgerStore(empty_database)
    for entity, kind in (("0.0.3456781", TOPIC), ("0.0.2345671", TOKEN)):
        ledger.save_facts(
            LedgerFacts(
                entity, "testnet", ASKED, found=True, kind=kind, ledger_id=entity, created_at=MADE
            )
        )
    judge_every_id(empty_database, PROOF_FOUND)
    return empty_database


def rows(database: str, query: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(query).fetchall()


def test_only_an_own_id_whose_kind_fits_is_given(database: str) -> None:
    # The coin is named by two projects: it is left out, as a shared service may be.
    assert HistoryStore(database).ids_to_read() == [
        IdToRead("0.0.3456781", "testnet", TOPIC, "0.0.3456781", MADE)
    ]
    judge_every_id(database, ANOTHER_KIND)  # the number is something else on the ledger
    assert HistoryStore(database).ids_to_read() == []


def test_a_history_is_kept_with_its_events_and_read_once(database: str) -> None:
    store = HistoryStore(database)
    store.save(
        "0.0.3456781", "testnet", TOPIC, History({ONE: CONSENSUS, TWO: TOKENS}, False), ASKED
    )
    assert rows(database, "SELECT entity_id, network, kind, events, cut FROM ledger_histories") == [
        ("0.0.3456781", "testnet", TOPIC, 2, False)
    ]
    assert rows(database, "SELECT stamp, at, service FROM ledger_events ORDER BY stamp") == [
        (ONE, datetime.fromtimestamp(1780000000, UTC), CONSENSUS),
        (TWO, datetime.fromtimestamp(1780000060, UTC), TOKENS),
    ]
    assert store.ids_to_read() == []


def test_a_newer_history_replaces_the_older_one(database: str) -> None:
    store = HistoryStore(database)
    store.save("0.0.3456781", "testnet", TOPIC, History({ONE: CONSENSUS}, False), ASKED)
    store.save("0.0.3456781", "testnet", TOPIC, History({TWO: CONSENSUS}, True), ASKED)
    assert rows(database, "SELECT events, cut FROM ledger_histories") == [(1, True)]
    assert rows(database, "SELECT stamp FROM ledger_events") == [(TWO,)]


def test_the_command_reads_the_histories_and_says_how_many(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from fakes import StandInMirror
    from hackathon_memory.pipeline.__main__ import main
    from hackathon_memory.settings import Settings

    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.3456781")] = [{"consensus_timestamp": ONE}]
    settings = Settings(_env_file=None, database_url=database)
    assert main(["history"], settings, {"testnet": mirror}) == 0  # type: ignore[arg-type]
    assert "Histories read: 1, with 1 events in all. Cut by the limit of events: 0." in (
        capsys.readouterr().out
    )
    assert main(["history", "--max-age-days", "1"], settings) == 2  # an option of check only


def test_the_story_of_a_project_reads_its_own_ids_and_the_days_of_its_event(
    database: str,
) -> None:
    """The ledger story of a card (design 7.5): the own IDs whose kind fits, what was read of
    them and when, and the time around its event."""
    with psycopg.connect(database) as conn:
        first, second = (pid for (pid,) in conn.execute("SELECT id FROM projects ORDER BY id"))
        conn.execute(  # the events of the history happen on 28 May 2026
            "UPDATE events SET starts_at = %s, ends_on = %s",
            (datetime(2026, 5, 27, 9, 0, tzinfo=UTC), date(2026, 5, 29)),
        )
        waiting = story_of_project(conn, first, words="Our HCS topic.", in_code=None)
        nothing = story_of_project(conn, second, words="We pay with HTS.", in_code=None)
    assert nothing is None  # its one ID, the coin, is named by two projects
    assert waiting is not None and waiting.not_read == 1 and not waiting.read
    HistoryStore(database).save(
        "0.0.3456781", "testnet", TOPIC, History({ONE: CONSENSUS, TWO: CONSENSUS}, True), ASKED
    )
    with psycopg.connect(database) as conn:
        story = story_of_project(conn, first, words="Our HCS topic.", in_code=frozenset())
    assert story is not None
    assert [(one.entity_id, one.kind, one.cut) for one in story.read] == [
        ("0.0.3456781", TOPIC, True)
    ]
    assert story.read_on == (ASKED.date(), ASKED.date())
    assert (story.starts_on, story.ends_on) == (date(2026, 4, 27), date(2026, 6, 28))
    assert [(line.service, line.words, line.count) for line in story.lines] == [
        (CONSENSUS, ("HCS",), 2)
    ]
    assert story.all_named_seen and story.before is not None and story.before.count == 0


def test_the_own_ids_to_time_are_those_read_on_their_network(database: str) -> None:
    from evals.history_times import own_ids

    assert own_ids(database) == {}  # nothing read yet
    HistoryStore(database).save(
        "0.0.3456781", "testnet", TOPIC, History({ONE: CONSENSUS}, False), ASKED
    )
    with psycopg.connect(database) as conn:
        (first,) = conn.execute("SELECT min(id) FROM projects").fetchone()
    assert own_ids(database) == {first: [("testnet", "0.0.3456781", TOPIC, MADE)]}
