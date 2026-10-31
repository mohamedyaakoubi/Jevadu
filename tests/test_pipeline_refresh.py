"""The step `refresh` (design 7.3, 25 October 2026), on a real PostgreSQL, a stand-in GitHub and
a stand-in mirror node: a first run asks for what is missing, a later run asks again for what is
old, with the ETag of the last answer, and writes what changed.

Every page, answer and archive here is invented. No request leaves the test."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from checkfakes import (
    COMMIT,
    DOWNLOAD,
    LATER_COMMIT,
    NOW,
    REPO,
    commits_answer,
    compare_answer,
    facts_answer,
    github,
    nodes,
    readme_answer,
)
from fakes import ARCHIVE_COMMIT, Reply, archive, project_page
from hackathon_memory.collect.answers import Answers
from hackathon_memory.collect.github import archive_address, readme_address
from hackathon_memory.collect.github_commits import commits_address
from hackathon_memory.collect.github_facts import facts_address
from hackathon_memory.collect.github_history import compare_address, until_address
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.refresh import STEP, refresh, refresh_lines

pytestmark = pytest.mark.integration

COLLECTOR = "TestTool/0.1.0"
DAY = timedelta(hours=24)
LATER = NOW + timedelta(days=2)
FIRST = "# Pebble Pay\n\nOur topic on testnet: 0.0.3456781.\n"
SECOND = "# Pebble Pay\n\nOur topic on testnet: 0.0.3456781. Our token: 0.0.4870201.\n"


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    html = project_page(name="Pebble Pay", slug="pebble-pay", code=REPO)
    ProjectStore(empty_database).save(
        read_project_page(html, "https://ethglobal.com/showcase/pebble-pay-x1y2z"), "a" * 64
    )
    return empty_database


def readme_ids(database: str) -> list[str]:
    with psycopg.connect(database) as conn:
        rows = conn.execute("SELECT entity_id FROM hedera_ids WHERE found_in = 'readme' "
                            "ORDER BY entity_id").fetchall()  # fmt: skip
    return [row[0] for row in rows]


def test_a_first_run_asks_for_what_is_missing_and_a_later_run_for_what_changed(
    database: str, tmp_path: Path
) -> None:
    pages = {
        facts_address(REPO): [Reply(200, facts_answer(), {"ETag": '"facts"'}), Reply(304, b"")],
        readme_address(REPO): [Reply(200, readme_answer(FIRST), {"ETag": '"one"'}),
                               Reply(200, readme_answer(SECOND), {"ETag": '"two"'})],
        commits_address(REPO): Reply(200, commits_answer(ARCHIVE_COMMIT), {"ETag": '"c"'}),
        archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
        DOWNLOAD: Reply(200, archive({"src/a.ts": b"// nothing"})),
    }  # fmt: skip
    client, site = github(tmp_path, pages)
    answers = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        refresh(database, answers, client, nodes(), run, collector=COLLECTOR, older_than=DAY,
                now=lambda: NOW)  # fmt: skip
    assert readme_ids(database) == ["0.0.3456781"]
    first = len(site.seen)
    assert first == 5  # the facts, the README, the commit, and the archive in two requests

    client.now = lambda: LATER
    with recorded_run(database, STEP) as run:
        refresh(database, answers, client, nodes(), run, collector=COLLECTOR, older_than=DAY,
                now=lambda: LATER)  # fmt: skip
    asked = site.seen[first:]
    assert [request.headers.get("If-None-Match") for request in asked] == ['"facts"', '"one"',
                                                                          '"c"']  # fmt: skip
    assert readme_ids(database) == ["0.0.3456781", "0.0.4870201"]  # the README changed
    counts = run.counts
    assert (counts["facts_unchanged"], counts["readmes_changed"], counts["versions_unchanged"],
            counts["archives_fresh"]) == (1, 1, 1, 1)  # fmt: skip
    with psycopg.connect(database) as conn:
        (read_at,) = conn.execute("SELECT code_fetched_at FROM repositories").fetchone()
    assert read_at == LATER  # the 304 dates the facts of the repository
    lines = "\n".join(refresh_lines(run))
    assert "GitHub, READMEs: 1 asked (0 for the first time), 0 the same, 1 changed" in lines


def test_with_no_client_nothing_is_asked_of_github(database: str, tmp_path: Path) -> None:
    with recorded_run(database, STEP) as run:
        refresh(database, Answers(tmp_path / "raw"), None, nodes(), run, collector=COLLECTOR,
                now=lambda: NOW)  # fmt: skip
    assert run.counts["repositories_answered"] == 0 and readme_ids(database) == []


def test_one_project_is_read_again_alone(database: str, tmp_path: Path) -> None:
    """The button "Read again now" of a card asks for its own repository only (design 7.3)."""
    pages = {facts_address(REPO): Reply(200, facts_answer())}
    client, site = github(tmp_path, pages)
    with psycopg.connect(database) as conn:
        (pebble,) = conn.execute("SELECT id FROM projects").fetchone()
    with recorded_run(database, STEP) as run:
        refresh(database, Answers(tmp_path / "raw"), client, nodes(), run, collector=COLLECTOR,
                older_than=timedelta(0), projects={pebble + 1}, now=lambda: NOW)  # fmt: skip
    assert site.seen == []  # another project: nothing of Pebble Pay is asked
    with recorded_run(database, STEP) as run:
        refresh(database, Answers(tmp_path / "raw"), client, nodes(), run, collector=COLLECTOR,
                older_than=timedelta(0), projects={pebble}, now=lambda: NOW)  # fmt: skip
    assert str(site.seen[0].url) == facts_address(REPO)


def test_each_reading_keeps_what_changed_and_says_its_steps(database: str, tmp_path: Path) -> None:
    """A reading compares what the tool holds before and after it (design 7.3, 28 October 2026):
    the step keeps what changed, a reading by the button is kept also when nothing did, and each
    step is said as it starts."""
    from hackathon_memory.db.readings import BUTTON, REFRESH, ReadingStore
    from hackathon_memory.pipeline.refresh import STEPS

    pages = {
        facts_address(REPO): [Reply(200, facts_answer(), {"ETag": '"facts"'}), Reply(304, b"")],
        readme_address(REPO): [Reply(200, readme_answer(FIRST), {"ETag": '"one"'}),
                               Reply(200, readme_answer(SECOND), {"ETag": '"two"'})],
        commits_address(REPO): Reply(200, commits_answer(ARCHIVE_COMMIT), {"ETag": '"c"'}),
        archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
        DOWNLOAD: Reply(200, archive({"src/a.ts": b"// nothing"})),
    }  # fmt: skip
    client, _ = github(tmp_path, pages)
    answers = Answers(tmp_path / "raw")
    store = ReadingStore(database)
    with psycopg.connect(database) as conn:
        (pebble,) = conn.execute("SELECT id FROM projects").fetchone()

    def read(when: datetime, **options: object) -> None:
        client.now = lambda: when
        with recorded_run(database, STEP) as run:
            refresh(database, answers, client, nodes(), run, collector=COLLECTOR, older_than=DAY,
                    now=lambda: when, **options)  # fmt: skip

    steps: list[str] = []
    read(NOW, step=steps.append)
    assert steps == list(STEPS)  # GitHub, the code, the ledger, the new transactions
    first = store.latest(pebble)
    assert first is not None and first.source == REFRESH and first.read_at == NOW
    assert "A README was found." in first.changes and "New Hedera ID: 0.0.3456781." in first.changes
    read(LATER)
    second = store.latest(pebble)
    assert second is not None and second.read_at == LATER
    assert "The README changed." in second.changes
    assert "New Hedera ID: 0.0.4870201." in second.changes
    read(
        LATER + timedelta(minutes=1)
    )  # nothing is old enough to ask: nothing changed, nothing kept
    assert store.latest(pebble) == second
    read(LATER + timedelta(minutes=2), projects={pebble}, source=BUTTON)
    pressed = store.latest(pebble)
    assert pressed is not None and pressed.source == BUTTON and pressed.changes == ()


def test_a_team_that_comes_back_gets_its_timeline_in_the_reading(
    database: str, tmp_path: Path
) -> None:
    """A new list of projects brings Pebble Pay back to another event with the same repository:
    the next reading asks GitHub for what its timeline lacks, with nobody asking for it, and a
    later reading asks nothing more (design 8.7, 31 October 2026)."""
    back = project_page(name="Pebble Pay Two", slug="pebble-pay-two", short_id="p2q3r",
                        event_slug="later-event", event_name="Later Event",
                        starts_at="2026-06-12T16:00:00.000Z", code=REPO)  # fmt: skip
    ProjectStore(database).save(
        read_project_page(back, "https://ethglobal.com/showcase/pebble-pay-two-p2q3r"), "b" * 64
    )
    march, june = date(2026, 3, 8), date(2026, 6, 14)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = %s WHERE slug = 'sample-event'", (march,))
        conn.execute("UPDATE events SET ends_on = %s WHERE slug = 'later-event'", (june,))
    pages = {
        facts_address(REPO): Reply(200, facts_answer()),
        readme_address(REPO): Reply(200, readme_answer(FIRST)),
        commits_address(REPO): Reply(200, commits_answer(ARCHIVE_COMMIT)),
        archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
        DOWNLOAD: Reply(200, archive({"src/a.ts": b"// nothing"})),
        until_address(REPO, march): Reply(200, commits_answer()),
        until_address(REPO, june): Reply(200, commits_answer(LATER_COMMIT)),
        compare_address(REPO, COMMIT, LATER_COMMIT): Reply(200, compare_answer()),
    }
    client, site = github(tmp_path, pages)
    answers = Answers(tmp_path / "raw")
    with recorded_run(database, STEP) as run:
        refresh(database, answers, client, nodes(), run, collector=COLLECTOR, older_than=DAY,
                now=lambda: NOW)  # fmt: skip
    counts = run.counts
    assert (counts["timeline_groups"], counts["timeline_commits_asked"],
            counts["timeline_changes_asked"]) == (1, 2, 1)  # fmt: skip
    assert "GitHub, comparisons of two commits: 1 asked" in "\n".join(refresh_lines(run))
    asked = len(site.seen)
    with recorded_run(database, STEP) as run:
        refresh(database, answers, client, nodes(), run, collector=COLLECTOR, older_than=DAY,
                now=lambda: NOW)  # fmt: skip
    assert len(site.seen) == asked and run.counts["timeline_commits_saved_before"] == 2
    assert "comparisons of two commits" not in "\n".join(refresh_lines(run))
