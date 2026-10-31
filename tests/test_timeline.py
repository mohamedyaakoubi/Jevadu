"""The timeline of projects that came back (design 8.7, 31 October 2026), on a real PostgreSQL and
a stand-in GitHub: which projects have one, whatever they won and however they are linked, the
step that asks GitHub once for what they lack, and the timeline read from the saved answers.

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
from hackathon_memory.collect.github_commits import EMPTY
from hackathon_memory.collect.github_history import Change, compare_address, until_address
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.timeline import STEP, ask_timelines, timeline_lines
from hackathon_memory.search.timeline import (
    COMPARED,
    NO_COMMIT,
    NO_REPOSITORY,
    NOT_ASKED,
    NOT_GIVEN,
    OTHER_REPOSITORY,
    SAME_COMMIT,
    Entry,
    Group,
    returning_groups,
    timeline_of,
)

pytestmark = pytest.mark.integration

COLLECTOR = "TestTool/0.1.0"
MARCH, JUNE = date(2026, 3, 8), date(2026, 6, 14)  # the last days of the two invented events
SHOWCASE = "https://ethglobal.com/showcase/"
OTHER = "https://github.com/sample-org/other-pay"  # an invented second repository
TOPIC = "0.0.3456781"


@pytest.fixture
def came_back(empty_database: str) -> tuple[str, dict[str, int]]:
    """Pebble Pay won a prize at an event that ended on 8 March, and came back with the same
    repository to another that ended on 14 June, where it won nothing; Reed Radio, with no code,
    was at the first."""
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


def same_topic(database: str, *projects: int) -> None:
    """Each project names the same topic, which the ledger confirmed."""
    with psycopg.connect(database) as conn:
        for pid in projects:
            (hid,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'topic', 'page', "
                "'invented', false) RETURNING id", (pid, TOPIC)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'testnet', 'proof_found')", (hid,))  # fmt: skip


def answers_of_github(second: bytes | None = None) -> dict[str, Reply]:
    """GitHub knows the newest commit at the end of each event, and their comparison."""
    return {
        until_address(REPO, MARCH): Reply(200, commits_answer()),
        until_address(REPO, JUNE): Reply(200, second or commits_answer(LATER_COMMIT)),
        compare_address(REPO, COMMIT, LATER_COMMIT): Reply(200, compare_answer()),
    }


def no_depth(project_id: int) -> None:  # noqa: ARG001
    return None


def test_a_team_that_came_back_with_one_repository_is_one_group(came_back) -> None:  # noqa: ANN001
    database, ids = came_back
    pebble, two = ids["Pebble Pay"], ids["Pebble Pay Two"]
    expected = [Group((pebble, two), (MARCH, JUNE), (REPO, REPO))]  # the oldest event first
    assert returning_groups(database) == expected and expected[0].repository == REPO
    assert returning_groups(database, [two]) == expected
    assert returning_groups(database, [ids["Reed Radio"]]) == []


def test_a_group_needs_two_known_last_days(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = NULL WHERE slug = 'later-event'")
    assert returning_groups(database) == []
    assert timeline_of(database, Answers(tmp_path / "raw"), ids["Pebble Pay"], no_depth) is None


def test_projects_linked_by_a_hedera_id_have_a_timeline_too(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    """The same topic at two events links two projects with two repositories (design 8.4): each
    entry gets its own code at the end of its event, the step says how the two are linked, and
    the code is not compared. With no repository on one side, the step says so."""
    database, ids = came_back
    pebble, two = ids["Pebble Pay"], ids["Pebble Pay Two"]
    RepositoryStore(database).link({pebble: REPO, two: OTHER})
    same_topic(database, pebble, two)
    (group,) = returning_groups(database)
    assert group == Group((pebble, two), (MARCH, JUNE), (REPO, OTHER)) and group.repository is None
    pages = {until_address(REPO, MARCH): Reply(200, commits_answer()),
             until_address(OTHER, JUNE): Reply(200, commits_answer(LATER_COMMIT))}  # fmt: skip
    client, site = github(tmp_path, pages)
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert (run.counts["timeline_commits_asked"], run.counts["timeline_changes_asked"]) == (2, 0)
    assert len(site.seen) == 2  # each repository at the end of its own event, and no comparison
    line = timeline_of(database, store, two, no_depth)
    assert line.repository is None
    assert [(entry.repository, entry.commit.sha) for entry in line.entries] == [
        (REPO, COMMIT), (OTHER, LATER_COMMIT)]  # fmt: skip
    (step,) = line.steps
    assert (step.link, step.state) == (f"testnet:{TOPIC}", OTHER_REPOSITORY)
    RepositoryStore(database).link({pebble: REPO})  # the second names no code
    (step,) = timeline_of(database, store, pebble, no_depth).steps
    assert (step.link, step.state) == (f"testnet:{TOPIC}", NO_REPOSITORY)


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
    assert (first.project_id, second.project_id) == (pebble, two) and line.repository == REPO
    assert (first.event, first.ends, second.event, second.ends) == (EVENT, MARCH, "Later Event",
                                                                    JUNE)  # fmt: skip
    assert second.starts == date(2026, 6, 12)
    assert first.prizes and first.prizes[0].startswith("Hedera: AI, Agents & Hedera Services")
    assert (second.prizes, second.short_line) == ((), "Pebble Pay, now with receipts.")
    assert (first.commit.sha, second.commit.sha) == (COMMIT, LATER_COMMIT)
    (step,) = line.steps
    assert (step.link, step.state, step.change) == ("repository", COMPARED,
                                                    Change("ahead", 4, 3, 60, 3))  # fmt: skip
    assert step.page == f"{REPO}/compare/{COMMIT}...{LATER_COMMIT}"
    asked = len(site.seen)
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert len(site.seen) == asked  # every answer is saved: nothing is asked again
    assert timeline_lines(run) == [
        "Groups of projects that came back, with a timeline: 1.",
        "GitHub, commits at the end of an event: 0 asked, 2 saved before, 0 failed, 0 left for "
        "a later run.",
        "GitHub, comparisons of two commits: 0 asked, 1 saved before, 0 failed, 0 left for a "
        "later run.",
    ]


def test_the_same_commit_at_two_events_is_no_change(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    client, site = github(tmp_path, answers_of_github(second=commits_answer()))
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert run.counts["timeline_changes_asked"] == 0 and len(site.seen) == 2  # nothing to compare
    (step,) = timeline_of(database, store, ids["Pebble Pay"], no_depth).steps
    assert step.state == SAME_COMMIT


def test_no_commit_yet_and_a_comparison_not_given_are_said(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    """A day before the first commit gives no commit: the repository was empty on that day. A
    comparison that GitHub no longer gives (a history written again) is not asked for again."""
    database, ids = came_back
    pebble = ids["Pebble Pay"]
    for folder in ("empty", "gone"):
        (tmp_path / folder).mkdir()
    client, _ = github(tmp_path / "empty", answers_of_github(second=b"[]"))
    store = Answers(tmp_path / "raw-empty")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    line = timeline_of(database, store, pebble, no_depth)
    assert line.entries[1].commit.status == EMPTY and line.entries[1].commit.sha is None
    assert line.steps[0].state == NO_COMMIT
    pages = answers_of_github()
    pages[compare_address(REPO, COMMIT, LATER_COMMIT)] = Reply(404, b'{"message": "Not Found"}')
    client, site = github(tmp_path / "gone", pages)
    store = Answers(tmp_path / "raw-gone")
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert timeline_of(database, store, pebble, no_depth).steps[0].state == NOT_GIVEN
    asked = len(site.seen)
    with recorded_run(database, STEP) as run:
        ask_timelines(client, store, database, run, collector=COLLECTOR)
    assert len(site.seen) == asked


def test_with_no_client_the_timeline_says_what_is_not_read_yet(came_back, tmp_path: Path) -> None:  # noqa: ANN001
    database, ids = came_back
    store = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        ask_timelines(None, store, database, run, collector=COLLECTOR)
    assert run.counts["timeline_groups"] == 1 and run.counts["timeline_commits_asked"] == 0
    line = timeline_of(database, store, ids["Pebble Pay"], no_depth)
    assert [entry.commit for entry in line.entries] == [None, None]
    assert line.steps[0].state == NOT_ASKED and line.steps[0].page is None
    assert timeline_of(database, store, ids["Reed Radio"], no_depth) is None


def test_a_line_names_three_kinds_and_counts_the_rest() -> None:
    did = (("messages", 12), ("transfers", 7), ("mints", 3), ("burns", 2))
    entry = Entry(1, "Pebble Pay", EVENT, None, MARCH, (), "", did, 5, None, None)
    assert entry.did_text == "12 messages, 7 transfers, 3 mints, and 7 more"
    assert replace(entry, did=(("messages", 1_200),), more=0).did_text == "1,200 messages"
    assert replace(entry, did=(), more=0).did_text == "no transaction of its own Hedera IDs"
