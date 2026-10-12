"""The step that reads the README of each project's code, on a real PostgreSQL.

Every page and every README here is invented. No request leaves the test.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import psycopg
import pytest

from fakes import project_page
from hackathon_memory.collect.github import raw_dir, readme_address
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.github_readmes import SUFFIX, kept_of
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.pipeline.readmes import STEP, read_readmes
from hackathon_memory.settings import Settings

pytestmark = pytest.mark.integration

PEBBLE = "https://github.com/sample-org/pebble-pay"
CEDAR = "https://github.com/sample-org/cedar-lens"
DUNE = "https://github.com/sample-org/dune-notes"
README = (
    "# Pebble Pay\n\nOur topic on testnet: 0.0.3456789.\n\n"
    "## Team\n\nQuill Invented runs the account 0.0.1234567.\n\n## License\n\nMIT\n"
)


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def page(name: str) -> str:
    return f"https://ethglobal.com/showcase/{name}-x1y2z"


def projects_in(database: str) -> dict[str, int]:
    """Four invented projects: two share the code of Pebble, one has its own, one has none."""
    store = ProjectStore(database)
    for name, code in (
        ("pebble-pay", PEBBLE),
        ("pebble-copy", "https://www.github.com/Sample-Org/Pebble-Pay"),
        ("cedar-lens", CEDAR),
        ("dune-notes", None),
    ):
        html = project_page(name=name.replace("-", " ").title(), slug=name, code=code)
        store.save(read_project_page(html, page(name)), "a" * 64)
    with psycopg.connect(database) as conn:
        return {key: number for key, number in conn.execute("SELECT site_key, id FROM projects")}


def save_answer(raw: RawStore, repository: str, status: int, text: str | None = None) -> None:
    url = readme_address(repository)
    if text is None:
        body = json.dumps({"message": "Not Found", "status": "404"}).encode()
    else:
        content = base64.b64encode(text.encode()).decode()
        body = json.dumps(
            {"name": "README.md", "path": "README.md", "encoding": "base64", "content": content}
        ).encode()
    fetch = FetchResult(url, url, status, body, "application/json", "2026-10-11T18:00:00Z")
    kept, facts, taken_out = kept_of(fetch)
    raw.save(
        fetch, kept, received=body, collector="TestTool/0.1.0", team_cut=taken_out,
        answer=facts, suffix=SUFFIX,
    )  # fmt: skip


def run_step(database: str, raw: RawStore, **options: object) -> Run:
    with recorded_run(database, STEP) as run:
        read_readmes(RepositoryStore(database), ProjectStore(database), raw, run, **options)  # type: ignore[arg-type]
    return run


def readme_ids(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(
            "SELECT p.site_key, h.entity_id, h.network, h.said_kind FROM hedera_ids h "
            "JOIN projects p ON p.id = h.project_id WHERE h.found_in = 'readme' ORDER BY 1, 2"
        ).fetchall()


# --------------------------------------------------------------------- reading what is saved


def test_the_ids_of_a_readme_go_to_every_project_of_its_repository(
    database: str, tmp_path: Path
) -> None:
    projects_in(database)
    raw = RawStore(tmp_path)
    save_answer(raw, PEBBLE, 200, README)
    save_answer(raw, CEDAR, 404)
    run = run_step(database, raw)
    # The id that stood in the part about the team was cut out with it, and counted.
    assert readme_ids(database) == [
        ("pebble-copy-x1y2z", "0.0.3456789", "testnet", "topic"),
        ("pebble-pay-x1y2z", "0.0.3456789", "testnet", "topic"),
    ]
    assert dict(run.counts) == {
        "projects_with_code_on_github": 3,
        "repositories": 2,
        "readme_found": 1,
        "readme_none": 1,
        "taken_out_team_parts_cut": 1,
        "taken_out_team_lines_cut": 4,
        "taken_out_ids_in_the_cut": 1,
        "projects_whose_readme_ids_changed": 2,
        "projects_with_an_id_in_the_readme": 2,
        "ids_in_readmes": 2,
    }
    assert run.problems == []


def test_a_second_run_changes_nothing(database: str, tmp_path: Path) -> None:
    projects_in(database)
    raw = RawStore(tmp_path)
    save_answer(raw, PEBBLE, 200, README)
    run_step(database, raw)
    again = run_step(database, raw)
    assert again.counts["projects_whose_readme_ids_changed"] == 0
    assert again.counts["projects_with_an_id_in_the_readme"] == 2


def test_a_readme_not_asked_for_yet_changes_nothing_and_is_counted(
    database: str, tmp_path: Path
) -> None:
    projects_in(database)
    run = run_step(database, RawStore(tmp_path))
    assert run.counts["readmes_not_asked_yet"] == 2
    assert readme_ids(database) == []
    with psycopg.connect(database) as conn:
        statuses = conn.execute("SELECT url, readme_status FROM repositories ORDER BY 1").fetchall()
    assert statuses == [(CEDAR, None), (PEBBLE, None)]


def test_the_ids_of_a_readme_are_checked_like_those_of_a_page(
    database: str, tmp_path: Path
) -> None:
    ids = projects_in(database)
    raw = RawStore(tmp_path)
    save_answer(raw, PEBBLE, 200, README)
    run_step(database, raw)
    to_check = LedgerStore(database).ids_to_check()
    assert {(item.project_id, item.entity_id) for item in to_check} == {
        (ids["pebble-pay-x1y2z"], "0.0.3456789"),
        (ids["pebble-copy-x1y2z"], "0.0.3456789"),
    }


# --------------------------------------------------------------------- asking for what is missing


def test_the_missing_readmes_are_asked_for_before_the_saved_ones_are_read(
    database: str, tmp_path: Path
) -> None:
    projects_in(database)
    raw = RawStore(tmp_path)
    asked: list[list[str]] = []

    def fetch(wanted: list[str]) -> AnswersRun:
        asked.append(wanted)
        save_answer(raw, PEBBLE, 200, README)  # as GitHub would have answered
        return AnswersRun(repositories=len(wanted), asked=2, failed=1, left_for_later=0)

    run = run_step(database, raw, fetch=fetch)
    assert asked == [[CEDAR, PEBBLE]]
    assert (run.counts["readmes_asked"], run.counts["readmes_failed"]) == (2, 1)
    assert run.counts["readme_found"] == 1
    assert run.counts["readmes_not_asked_yet"] == 1


def test_a_stop_of_github_is_named_in_the_run(database: str, tmp_path: Path) -> None:
    projects_in(database)

    def fetch(wanted: list[str]) -> AnswersRun:
        return AnswersRun(repositories=len(wanted), stopped="api.github.com answered 401")

    run = run_step(database, RawStore(tmp_path), fetch=fetch)
    assert run.problems == [{"what": "GitHub", "rule": "api.github.com answered 401"}]


# --------------------------------------------------------------------- the command


def settings_for(database: str, tmp_path: Path, **values: object) -> Settings:
    return Settings(_env_file=None, database_url=database, data_dir=str(tmp_path), **values)  # type: ignore[arg-type]


def test_the_command_reads_the_saved_readmes_and_says_what_it_did(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects_in(database)
    settings = settings_for(database, tmp_path)
    save_answer(RawStore(raw_dir(settings)), PEBBLE, 200, README)
    assert main(["readmes", "--no-requests"], settings) == 0
    said = capsys.readouterr().out
    assert "Projects with their code on GitHub: 3, in 2 repositories." in said
    assert "READMEs: 1 found, 0 no README, 0 blocked by GitHub, 0 not text." in said
    assert "Not asked for yet: 1." in said
    assert "1 parts about the team (4 lines, with 1 Hedera ids in them)" in said
    assert "Projects with a Hedera id in their README: 2 (2 ids)." in said
    assert "quill" not in said.lower()


def test_with_the_switch_off_the_command_asks_nothing_and_says_so(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects_in(database)
    assert main(["readmes"], settings_for(database, tmp_path, collect_github=False)) == 0
    said = capsys.readouterr().out
    assert "COLLECT_GITHUB is off in .env, so nothing was asked of GitHub." in said


def test_a_client_that_cannot_start_is_named_and_the_saved_readmes_are_still_read(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects_in(database)
    settings = settings_for(database, tmp_path, collect_github=True, github_token="")
    save_answer(RawStore(raw_dir(settings)), PEBBLE, 200, README)
    assert main(["readmes"], settings) == 1
    said = capsys.readouterr().out
    assert "GITHUB_TOKEN is empty" in said
    assert "Projects with a Hedera id in their README: 2 (2 ids)." in said


@pytest.mark.parametrize(
    "argv",
    [
        ["parse", "--repos", "3"],
        ["check", "--no-requests"],
        ["readmes", "--repos", "0"],
        ["readmes", "--no-requests", "--repos", "2"],
        ["readmes", "--no-requests", "--wait"],
        ["readmes", "--limit", "5"],
        ["readmes", "--max-age-days", "1"],
    ],
)
def test_options_that_do_not_go_together_are_refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv, Settings(_env_file=None)) == 2
    assert "usage:" in capsys.readouterr().out
