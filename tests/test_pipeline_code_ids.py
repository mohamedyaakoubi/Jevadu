"""The IDs of a project's code that prove its use of Hedera (pipeline/code_ids.py), on a real
PostgreSQL and a stand-in mirror node. Every page, repository, ID and date is invented."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, StandInMirror, project_page
from hackathon_memory.collect.github_code import READ, CodeRead
from hackathon_memory.db.code_ids import CodeIdStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_code import CodeScan, IdInCode, Seen
from hackathon_memory.pipeline.check_ids import MAX_AGE, check_ids
from hackathon_memory.pipeline.code_ids import give_code_ids

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
DURING = "1772884800.000000001"  # 7 March 2026: the event runs from 6 to 8 March 2026
LONG_BEFORE = "1736899200.000000001"  # 15 January 2025
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
PEBBLE_CODE = "https://github.com/sample-org/pebble-pay"
QUARTZ_CODE = "https://github.com/sample-org/quartz-notes"


def reading(*ids: str) -> CodeRead:
    """The reading of a repository whose settings name these IDs, with no network."""
    scan = CodeScan(files=3, ids={(one, None): IdInCode(one, None, Seen(1, ["config/ids.ts"]))
                                  for one in ids})  # fmt: skip
    return CodeRead(READ, scan, "2026-03-09T00:00:00Z")


@pytest.fixture
def database(empty_database: str) -> str:
    """Two projects of one event: the first names a topic on its page, the second nothing."""
    migrate(empty_database)
    projects = ProjectStore(empty_database)
    first = project_page(description="<p>The log is the topic 0.0.3456781.</p>")
    projects.save(read_project_page(first, PROJECT_PAGE), "a" * 64)
    second = project_page(name="Quartz Notes", slug="quartz-notes", short_id="q3w4e")
    projects.save(read_project_page(second, SECOND_PAGE), "b" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
        ids = dict(conn.execute("SELECT site_key, id FROM projects").fetchall())
    repositories = RepositoryStore(empty_database)
    repositories.link({ids["pebble-pay-x1y2z"]: PEBBLE_CODE,
                       ids["quartz-notes-q3w4e"]: QUARTZ_CODE})  # fmt: skip
    # The first project's code: its own account, made during the event; the topic that its page
    # names; a public token made long before; an account that the other repository names too.
    repositories.save_code(PEBBLE_CODE, reading("0.0.7000001", "0.0.3456781", "0.0.6000002",
                                                "0.0.7000003"))  # fmt: skip
    # The second project's code: the shared account, an empty topic made during the event, and
    # its own account made during the event.
    repositories.save_code(QUARTZ_CODE, reading("0.0.7000003", "0.0.7000004", "0.0.7000006"))
    return empty_database


def nodes() -> dict[str, StandInMirror]:
    made = {"created_timestamp": DURING}
    test = StandInMirror(
        "testnet",
        topic={"0.0.3456781": {"topic_id": "0.0.3456781", **made},
               "0.0.7000004": {"topic_id": "0.0.7000004", **made}},
        token={"0.0.6000002": {"token_id": "0.0.6000002", "total_supply": "1000",
                               "created_timestamp": LONG_BEFORE, "modified_timestamp": DURING}},
        account={pid: {"account": pid, **made} for pid in ("0.0.7000001", "0.0.7000003",
                                                          "0.0.7000006")},
    )  # fmt: skip
    test.lists[("messages", "0.0.3456781")] = [
        {"sequence_number": 1, "consensus_timestamp": DURING}
    ]
    return {"testnet": test, "mainnet": StandInMirror("mainnet")}


def run_both(database: str, mirrors: dict) -> Run:
    with recorded_run(database, "check") as run:
        give_code_ids(CodeIdStore(database), LedgerStore(database), mirrors, run,
                      max_age=MAX_AGE, now=lambda: NOW)  # fmt: skip
        check_ids(LedgerStore(database), mirrors, run, now=lambda: NOW)
    return run


def code_rows(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(
            "SELECT p.site_key, h.entity_id, h.network, h.found_at, h.words_around "
            "FROM hedera_ids h JOIN projects p ON p.id = h.project_id WHERE h.found_in = 'code' "
            "ORDER BY 1, 2"
        ).fetchall()


def statuses(database: str) -> dict[str, str | None]:
    with psycopg.connect(database) as conn:
        return dict(conn.execute("SELECT site_key, proof_status FROM projects").fetchall())


def test_only_an_own_id_of_the_code_made_during_the_event_counts(database: str) -> None:
    mirrors = nodes()
    run = run_both(database, mirrors)
    # Given: the own accounts made during the event. Not given: the topic that the page names
    # (the page's rule judges it), the public token made long before, the account that two
    # repositories name, and the empty topic.
    assert code_rows(database) == [
        ("pebble-pay-x1y2z", "0.0.7000001", "testnet", "config/ids.ts", ""),
        ("quartz-notes-q3w4e", "0.0.7000006", "testnet", "config/ids.ts", ""),
    ]
    # The second project names nothing on its page: its code now proves its use of Hedera.
    assert statuses(database) == {"pebble-pay-x1y2z": "proof_found",
                                  "quartz-notes-q3w4e": "proof_found"}  # fmt: skip
    assert run.counts["code_ids_given"] == 2 and run.counts["projects_with_code_ids"] == 2
    asked = {question[1] for question in mirrors["testnet"].asked}
    assert "0.0.7000003" not in asked  # a shared ID is not even asked about
    again = run_both(database, mirrors)
    assert again.counts["answers_from_the_node"] == 0  # the answers are young enough
    assert code_rows(database)[0][1] == "0.0.7000001"


def test_an_id_of_the_code_that_another_project_names_later_is_taken_back(database: str) -> None:
    mirrors = nodes()
    run_both(database, mirrors)
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) SELECT id, '0.0.7000006', 'testnet', 'account', "
            "'page', 'our account', false FROM projects WHERE site_key = 'pebble-pay-x1y2z'"
        )
    run_both(database, mirrors)
    assert [row[1] for row in code_rows(database)] == ["0.0.7000001"]
    assert statuses(database)["quartz-notes-q3w4e"] == "no_id_given"


def test_the_check_asks_only_about_the_candidates_in_the_most_files(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hackathon_memory.db import code_ids

    with psycopg.connect(database) as conn:  # the own account of the second project in 3 files
        conn.execute("UPDATE ids_in_code SET files = 3 WHERE entity_id = '0.0.7000006'")
    monkeypatch.setattr(code_ids, "MOST_CANDIDATES", 1)
    candidates = CodeIdStore(database).candidates()
    second = [one.entity_id for one in candidates if one.entity_id.startswith("0.0.70000")
              and one.project_id == candidates[-1].project_id]  # fmt: skip
    assert second == ["0.0.7000006"] and len(candidates) == 2  # one for each project


def test_a_candidate_whose_number_shows_it_was_made_outside_the_event_is_not_asked(
    database: str,
) -> None:
    mirrors = nodes()
    run_both(database, mirrors)  # the ledger's facts now date some numbers
    with psycopg.connect(database) as conn:  # a number below the token made long before
        conn.execute("INSERT INTO ids_in_code (repository_id, entity_id, network, files, examples) "
                     "SELECT id, '0.0.5000001', 'testnet', 2, ARRAY['src/old.ts'] "
                     "FROM repositories WHERE url = %s", (QUARTZ_CODE,))  # fmt: skip
    before = len(mirrors["testnet"].asked)
    again = run_both(database, mirrors)
    assert again.counts["code_ids_ruled_out_by_their_number"] >= 1
    assert all(question[1] != "0.0.5000001" for question in mirrors["testnet"].asked[before:])
