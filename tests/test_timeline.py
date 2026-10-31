"""The timeline of a team that came back with one repository (design 8.7, 31 October 2026), on a
real PostgreSQL and a stand-in GitHub: which teams have one, the step that asks GitHub once for
what they lack, and the timeline read from the saved answers.

Every page and answer here is invented. No request leaves the test."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import psycopg
import pytest

from checkfakes import COMMIT, LATER_COMMIT, REPO, commits_answer, compare_answer, github
from fakes import EVENT, Reply, project_page, won
from hackathon_memory.collect.answers import Answers
from hackathon_memory.collect.github_history import Change, compare_address, until_address
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.timeline import STEP, ask_timelines, timeline_lines
from hackathon_memory.search import seen
from hackathon_memory.search.timeline import (
    SAME,
    Entry,
    Group,
    groups_with_one_repository,
    timeline_of,
)

pytestmark = pytest.mark.integration

COLLECTOR = "TestTool/0.1.0"
MARCH, JUNE = date(2026, 3, 8), date(2026, 6, 14)  # the last days of the two invented events
SHOWCASE = "https://ethglobal.com/showcase/"


@pytest.fixture
def came_back(empty_database: str) -> tuple[str, dict[str, int]]:
    """Pebble Pay won a prize at an event that ended on 8 March, and came back with the same
    repository to another that ended on 14 June; Reed Radio, with no code, was at the first."""
    migrate(empty_database)
    store = ProjectStore(empty_database)
    store.save(read_project_page(project_page(prizes=[won()]), f"{SHOWCASE}pebble-pay-x1y2z"),
               "a" * 64)  # fmt: skip
    back = project_page(name="Pebble Pay Two", slug="pebble-pay-two", short_id="p2q3r",
                        event_slug="later-event", event_name="Later Event",
                        starts_at="2026-06-12T16:00:00.000Z",
                        short_line="Pebble Pay, now with receipts.")  # fmt: skip
    store.save(read_project_page(back, f"{SHOWCASE}pebble-pay-two-p2q3r"), "b" * 64)
    reed = project_page(name="Reed Radio", slug="reed-radio", short_id="r5t6y", code=None)
    store.save(read_project_page(reed, f"{SHOWCASE}reed-radio-r5t6y"), "c" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET ends_on = %s WHERE slug = 'sample-event'", (MARCH,))
        conn.execute("UPDATE events SET ends_on = %s WHERE slug = 'later-event'", (JUNE,))
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
    RepositoryStore(empty_database).link({ids["Pebble Pay"]: REPO, ids["Pebble Pay Two"]: REPO})
    return empty_database, ids


def answers_of_github(second: str = LATER_COMMIT) -> dict[str, Reply]:
    """GitHub knows the newest commit at the end of each event, and their comparison."""
    return {
        until_address(REPO, MARCH): Reply(200, commits_answer()),
        until_address(REPO, JUNE): Reply(200, commits_answer(second)),
        compare_address(REPO, COMMIT, LATER_COMMIT): Reply(200, compare_answer()),
    }


def no_depth(project_id: int) -> None:  # noqa: ARG001
    return None


def test_a_team_that_came_back_with_one_repository_is_one_group(came_back) -> None:  # noqa: ANN001
    database, ids = came_back
    pebble, two = ids["Pebble Pay"], ids["Pebble Pay Two"]
    expected = [Group(REPO, (pebble, two), (MARCH, JUNE))]  # the oldest event first
    assert groups_with_one_repository(database) == expected
    assert groups_with_one_repository(database, [two]) == expected
    assert groups_with_one_repository(database, [ids["Reed Radio"]]) == []


def test_a_group_needs_two_known_last_days(came_back) -> None:  # noqa: ANN001
    database, _ = came_back
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = NULL WHERE slug = 'later-event'")
    assert groups_with_one_repository(database) == []


def test_a_team_linked_by_a_hedera_id_alone_has_no_code_to_compare(came_back) -> None:  # noqa: ANN001
    """The same topic at two events links the two projects (design 8.4), but with two
    repositories, or one project with none, there is no one history of code to read."""
    database, ids = came_back
    pebble, two = ids["Pebble Pay"], ids["Pebble Pay Two"]
    other = "https://github.com/sample-org/other-pay"
    RepositoryStore(database).link({pebble: REPO, two: other})
    with psycopg.connect(database) as conn:
        for pid in (pebble, two):
            (hid,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, '0.0.3456781', 'testnet', 'topic', "
                "'page', 'invented', false) RETURNING id", (pid,)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'testnet', 'proof_found')", (hid,))  # fmt: skip
    assert sorted(seen.came_back(database)[0]) == sorted([pebble, two])  # still linked
    assert groups_with_one_repository(database) == []
    RepositoryStore(database).link({pebble: REPO})  # the second names no code
    assert groups_with_one_repository(database) == []


def test_the_step_asks_once_and_the_timeline_reads_the_answers(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    pebble, two = ids["Pebble Pay"], ids["Pebble Pay Two"]
    client, site = github(tmp_path, answers_of_github())
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    counts = run.counts
    assert (counts["timeline_groups"], counts["timeline_commits_asked"],
            counts["timeline_changes_asked"]) == (1, 2, 1)  # fmt: skip
    line = timeline_of(database, store, two, no_depth)
    first, second = line.entries
    assert (first.project_id, second.project_id) == (pebble, two)
    assert (first.event, first.ends, second.event, second.ends) == (EVENT, MARCH, "Later Event",
                                                                    JUNE)  # fmt: skip
    assert second.starts == date(2026, 6, 12)
    assert first.prizes and first.prizes[0].startswith("Hedera: AI, Agents & Hedera Services")
    assert (second.prizes, second.short_line) == ((), "Pebble Pay, now with receipts.")
    assert (first.commit.sha, second.commit.sha) == (COMMIT, LATER_COMMIT)
    assert line.changes == (Change("ahead", 4, 3, 60, 3),)
    assert line.compare_page(0) == f"{REPO}/compare/{COMMIT}...{LATER_COMMIT}"
    asked = len(site.seen)
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert len(site.seen) == asked  # every answer is saved: nothing is asked again
    assert timeline_lines(run) == [
        "Teams that came back with one repository: 1.",
        "GitHub, commits at the end of an event: 0 asked, 2 saved before, 0 failed, 0 left for "
        "a later run.",
        "GitHub, comparisons of two commits: 0 asked, 1 saved before, 0 failed, 0 left for a "
        "later run.",
    ]


def test_the_same_commit_at_two_events_is_no_change(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    client, site = github(tmp_path, answers_of_github(second=COMMIT))
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert run.counts["timeline_changes_asked"] == 0 and len(site.seen) == 2  # nothing to compare
    assert timeline_of(database, store, ids["Pebble Pay"], no_depth).changes == (SAME,)


def test_with_no_client_the_timeline_says_what_is_not_read_yet(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(None, store, database, run, collector=COLLECTOR)
    assert run.counts["timeline_groups"] == 1 and run.counts["timeline_commits_asked"] == 0
    line = timeline_of(database, store, ids["Pebble Pay"], no_depth)
    assert [entry.commit for entry in line.entries] == [None, None]
    assert line.changes == (None,) and line.compare_page(0) is None
    assert timeline_of(database, store, ids["Reed Radio"], no_depth) is None


def test_a_line_names_three_kinds_and_counts_the_rest() -> None:
    did = (("messages", 12), ("transfers", 7), ("mints", 3), ("burns", 2))
    entry = Entry(1, "Pebble Pay", EVENT, None, MARCH, (), "", did, 5, None)
    assert entry.did_text == "12 messages, 7 transfers, 3 mints, and 7 more"
    assert replace(entry, did=(("messages", 1_200),), more=0).did_text == "1,200 messages"
    assert replace(entry, did=(), more=0).did_text == "no transaction of its own Hedera IDs"
