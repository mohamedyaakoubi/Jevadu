"""The step that reads the facts of the code of each project, on a real PostgreSQL.

Every page and every answer here is invented. No request leaves the test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from fakes import project_page
from hackathon_memory.collect.github import raw_dir
from hackathon_memory.collect.github_facts import SUFFIX, facts_address, kept_of
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.pipeline.code import STEP, read_code
from hackathon_memory.settings import Settings

pytestmark = pytest.mark.integration

PEBBLE = "https://github.com/sample-org/pebble-pay"
CEDAR = "https://github.com/sample-org/cedar-lens"


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    store = ProjectStore(empty_database)
    for name, code in (("pebble-pay", PEBBLE), ("cedar-lens", CEDAR), ("dune-notes", None)):
        html = project_page(name=name.replace("-", " ").title(), slug=name, code=code)
        store.save(
            read_project_page(html, f"https://ethglobal.com/showcase/{name}-x1y2z"), "a" * 64
        )
    return empty_database


def save_answer(raw: RawStore, repository: str, status: int, **fields: object) -> None:
    url = facts_address(repository)
    body = json.dumps(
        {
            "owner": {"login": "sample-org", "avatar_url": "https://avatars.example.test/u/1"},
            "html_url": repository.replace("sample-org", "Sample-Org"),
            "created_at": "2026-03-06T17:00:00Z",
            "pushed_at": "2026-03-08T21:30:00Z",
            "archived": False,
            "fork": False,
            "language": "TypeScript",
            **fields,
        }
        if status == 200
        else {"message": "Not Found"}
    ).encode()
    fetch = FetchResult(url, url, status, body, "application/json", "2026-10-12T02:00:00Z")
    kept, facts, taken_out = kept_of(fetch)
    raw.save(
        fetch, kept, received=body, collector="TestTool/0.1.0", team_cut=taken_out,
        answer=facts, suffix=SUFFIX,
    )  # fmt: skip


def run_step(database: str, raw: RawStore, **options: object) -> Run:
    with recorded_run(database, STEP) as run:
        read_code(RepositoryStore(database), raw, run, **options)  # type: ignore[arg-type]
    return run


def test_the_facts_of_each_repository_are_written(database: str, tmp_path: Path) -> None:
    raw = RawStore(tmp_path)
    save_answer(raw, PEBBLE, 200, archived=True)
    save_answer(raw, CEDAR, 404)
    run = run_step(database, raw)
    with psycopg.connect(database) as conn:
        rows = conn.execute(
            "SELECT url, code_status, made_at, last_push_at, archived, fork, language, "
            "current_url FROM repositories ORDER BY url"
        ).fetchall()
    assert rows == [
        (CEDAR, "gone", None, None, None, None, None, None),
        (
            PEBBLE,
            "found",
            datetime(2026, 3, 6, 17, tzinfo=UTC),
            datetime(2026, 3, 8, 21, 30, tzinfo=UTC),
            True,
            False,
            "TypeScript",
            PEBBLE,  # the same repository in other letters is not a move
        ),
    ]
    assert dict(run.counts) == {
        "projects_with_code_on_github": 2,
        "repositories": 2,
        "repository_found": 1,
        "repository_gone": 1,
        "archived": 1,
    }


def test_a_moved_repository_is_counted(database: str, tmp_path: Path) -> None:
    raw = RawStore(tmp_path)
    save_answer(raw, PEBBLE, 200, html_url="https://github.com/new-org/pebble-pay")
    run = run_step(database, raw)
    assert run.counts["moved_or_renamed"] == 1
    assert run.counts["facts_not_asked_yet"] == 1


def test_the_missing_facts_are_asked_for_before_the_saved_ones_are_read(
    database: str, tmp_path: Path
) -> None:
    raw = RawStore(tmp_path)
    asked: list[list[str]] = []

    def fetch(wanted: list[str]) -> AnswersRun:
        asked.append(wanted)
        save_answer(raw, CEDAR, 200)
        return AnswersRun(repositories=len(wanted), asked=2, stopped="api.github.com answered 401")

    run = run_step(database, raw, fetch=fetch)
    assert asked == [[CEDAR, PEBBLE]]
    assert run.counts["facts_asked"] == 2
    assert run.counts["repository_found"] == 1
    assert run.problems == [{"what": "GitHub", "rule": "api.github.com answered 401"}]


def test_the_command_reads_the_saved_facts_and_says_what_it_did(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, database_url=database, data_dir=str(tmp_path))
    save_answer(RawStore(raw_dir(settings)), PEBBLE, 200, fork=True)
    assert main(["code", "--no-requests"], settings) == 0
    said = capsys.readouterr().out
    assert "Projects with their code on GitHub: 2, in 2 repositories." in said
    assert "Repositories: 1 found, 0 gone or private, 0 blocked by GitHub." in said
    assert "Not asked for yet: 1." in said
    assert "Archived: 0. Forks of another repository: 1." in said
