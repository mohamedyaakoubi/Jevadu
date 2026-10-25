"""The step `refresh` (design 7.3, 25 October 2026), on a real PostgreSQL, a stand-in GitHub and
a stand-in mirror node: a first run asks for what is missing, a later run asks again for what is
old, with the ETag of the last answer, and writes what changed.

Every page, answer and archive here is invented. No request leaves the test."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import psycopg
import pytest

from checkfakes import (
    DOWNLOAD,
    NOW,
    REPO,
    commits_answer,
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
