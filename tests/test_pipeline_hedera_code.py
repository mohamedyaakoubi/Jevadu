"""The step that reads where Hedera stands in the code of each repository, on a real PostgreSQL.

Every page, answer and archive here is invented. No request leaves the test.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import psycopg
import pytest

from fakes import archive, project_page
from hackathon_memory.collect.github import archive_address, raw_dir
from hackathon_memory.collect.github_code import save_reading
from hackathon_memory.collect.github_facts import SUFFIX as FACTS_SUFFIX
from hackathon_memory.collect.github_facts import facts_address, kept_of
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_code import LimitedStream, scan_archive
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.pipeline.hedera_code import STEP, read_hedera_code
from hackathon_memory.settings import Settings

pytestmark = pytest.mark.integration

PEBBLE = "https://github.com/sample-org/pebble-pay"
CEDAR = "https://github.com/sample-org/cedar-lens"
COLLECTOR = "TestTool/0.1.0"
FILES = {
    "package.json": b'{"dependencies": {"@hashgraph/sdk": "^2"}}',
    "src/topic.ts": b'import { TopicCreateTransaction } from "@hashgraph/sdk";\n',
    "src/plain.ts": b"export const one = 1;\n",
}


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


def save_archive(raw: RawStore, repository: str, files: dict[str, bytes] | None) -> None:
    """Save a reading as the collector saves it: of an archive, or of a 404 when `files` is
    None."""
    url = archive_address(repository)
    if files is None:
        body = b'{"message": "Not Found"}'
        fetch = FetchResult(url, url, 404, body, "application/json", "2026-10-21T20:00:00Z")
        save_reading(raw, fetch, None, COLLECTOR)
        return
    scan = scan_archive(LimitedStream(io.BytesIO(archive(files)).read))
    name = repository.removeprefix("https://github.com/")
    download = f"https://codeload.github.com/{name}/legacy.tar.gz/refs/heads/main"
    fetch = FetchResult(url, download, 200, b"", "application/x-gzip", "2026-10-21T20:00:00Z")
    save_reading(raw, fetch, scan, COLLECTOR)


def save_gone_facts(raw: RawStore, repository: str) -> None:
    """Save GitHub's answer about a repository, as the step of the code saves it: gone."""
    url = facts_address(repository)
    body = json.dumps({"message": "Not Found"}).encode()
    fetch = FetchResult(url, url, 404, body, "application/json", "2026-10-12T02:00:00Z")
    kept, facts, taken_out = kept_of(fetch)
    raw.save(fetch, kept, received=fetch.body, collector=COLLECTOR, team_cut=taken_out,
             answer=facts, suffix=FACTS_SUFFIX)  # fmt: skip


def run_step(database: str, raw: RawStore, **options: object) -> Run:
    with recorded_run(database, STEP) as run:
        read_hedera_code(RepositoryStore(database), raw, run, **options)  # type: ignore[arg-type]
    return run


def test_what_each_saved_reading_found_is_written(database: str, tmp_path: Path) -> None:
    raw = RawStore(tmp_path)
    save_archive(raw, PEBBLE, FILES)
    save_archive(raw, CEDAR, None)
    run = run_step(database, raw)
    with psycopg.connect(database) as conn:
        states = conn.execute(
            "SELECT url, archive_status, archive_files FROM repositories ORDER BY url"
        ).fetchall()
        found = conn.execute(
            "SELECT r.url, h.kind, h.name, h.files FROM hedera_in_code h "
            "JOIN repositories r ON r.id = h.repository_id ORDER BY h.kind"
        ).fetchall()
    assert states == [(CEDAR, "gone", None), (PEBBLE, "read", 3)]
    assert found == [
        (PEBBLE, "feature", "Consensus Service (topics)", 1),
        (PEBBLE, "import", "a Hedera library", 1),
        (PEBBLE, "mention", "the word Hedera, Hashgraph or Hiero", 2),
        (PEBBLE, "package", "@hashgraph/sdk", 1),
    ]
    assert dict(run.counts) == {
        "projects_with_code_on_github": 2,
        "repositories": 2,
        "archive_read": 1,
        "archive_gone": 1,
        "files_read": 3,
        "repositories_with_package": 1,
        "repositories_with_feature": 1,
        "repositories_with_import": 1,
        "repositories_with_mention": 1,
    }


def test_the_missing_archives_are_read_first_and_a_gone_repository_is_not_asked(
    database: str, tmp_path: Path
) -> None:
    raw = RawStore(tmp_path)
    save_gone_facts(raw, CEDAR)  # the step of the code already heard that it is gone
    asked: list[list[str]] = []

    def fetch(wanted: list[str]) -> AnswersRun:
        asked.append(wanted)
        save_archive(raw, PEBBLE, {"src/plain.ts": b"export const one = 1;\n"})
        return AnswersRun(repositories=len(wanted), asked=1, failed=0)

    run = run_step(database, raw, fetch=fetch)
    assert asked == [[PEBBLE]]
    assert run.counts["archives_asked"] == 1
    assert run.counts["archives_not_asked_code_gone"] == 1
    assert run.counts["archives_not_read_yet"] == 1  # Cedar: nothing is known of its code
    assert run.counts["repositories_with_nothing_found"] == 1


def test_the_command_reads_the_saved_readings_and_says_what_it_did(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, database_url=database, data_dir=str(tmp_path))
    save_archive(RawStore(raw_dir(settings)), PEBBLE, FILES)
    assert main(["hedera_code", "--no-requests"], settings) == 0
    said = capsys.readouterr().out
    assert "Projects with their code on GitHub: 2, in 2 repositories." in said
    assert (
        "Repositories: 1 read whole, 0 read in part, 0 gone or private, 0 blocked by GitHub. "
        "Not read yet: 1. Files of their own code read: 3." in said
    )
    assert "      1  a Hedera package in a package file" in said
    assert "      0  a sign of Hedera" in said
    assert "      0  a mention and nothing else" in said
    assert "older version of the reader" not in said


def test_the_options_of_github_go_with_the_step(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["hedera_code", "--limit", "3"], Settings(_env_file=None)) == 2
    assert "--limit goes with parse, embed, cards or history" in capsys.readouterr().out
