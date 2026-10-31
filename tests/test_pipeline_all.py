"""One command runs the whole path, from an empty database (design 14.3). All data is invented.

No request leaves the test: the pages and the README are saved files, the mirror node and Google
are stand-ins.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import psycopg
import pytest

from fakes import StandInMirror, project_page
from hackathon_memory.collect.github import raw_dir, readme_address
from hackathon_memory.collect.github_readmes import SUFFIX, kept_of
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.runs import last_runs
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.settings import Settings
from searchfakes import google

pytestmark = pytest.mark.integration

CODE = "https://github.com/sample-org/pebble-pay"


def save_page(store: RawStore, name: str, code: str | None) -> None:
    url = f"https://ethglobal.com/showcase/{name}-x1y2z"
    body = project_page(name=name.replace("-", " ").title(), slug=name, code=code)
    fetch = FetchResult(url, url, 200, body, "text/html", "2026-10-10T19:00:00Z")
    store.save(fetch, body, received=body, collector="TestTool/0.1.0")


def save_readme(store: RawStore, text: str) -> None:
    url = readme_address(CODE)
    content = base64.b64encode(text.encode()).decode()
    body = json.dumps({"name": "README.md", "encoding": "base64", "content": content}).encode()
    fetch = FetchResult(url, url, 200, body, "application/json", "2026-10-11T18:00:00Z")
    kept, facts, taken_out = kept_of(fetch)
    store.save(
        fetch, kept, received=body, collector="TestTool/0.1.0", team_cut=taken_out,
        answer=facts, suffix=SUFFIX,
    )  # fmt: skip


@pytest.fixture
def settings(empty_database: str, tmp_path: Path) -> Settings:
    migrate(empty_database)
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(tmp_path))
    pages = RawStore(tmp_path / "raw" / "ethglobal.com")
    save_page(pages, "pebble-pay", CODE)
    save_page(pages, "cedar-lens", None)
    save_readme(RawStore(raw_dir(settings)), "# Pebble\n\nOur topic on testnet: 0.0.3456781.\n")
    return settings


def test_one_command_runs_every_step_in_order(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    mirrors = {"testnet": StandInMirror("testnet"), "mainnet": StandInMirror("mainnet")}
    client, _, calls = google()
    assert main(["all"], settings, mirrors, client) == 0  # type: ignore[arg-type]
    said = capsys.readouterr().out
    headers = [line for line in said.splitlines() if line.startswith("== ")]
    assert headers == ["== parse ==", "== readmes ==", "== code ==", "== hedera_code ==",
                       "== timeline ==", "== check ==", "== embed =="]  # fmt: skip
    # the timelines of teams that came back are asked in the same run (design 8.7)
    assert "Teams that came back with one repository: 0." in said
    assert "Saved pages: 2. New: 2." in said
    assert "Projects with a Hedera id in their README: 1 (1 ids)." in said
    assert "Projects: 2. Embeddings made: 2" in said
    assert [row["step"] for row in reversed(last_runs(settings.database_conninfo()))] == [
        "parse",
        "readmes",
        "code",
        "hedera_code",
        "timeline",
        "check",
        "embed",
    ]
    with psycopg.connect(settings.database_conninfo()) as conn:
        asked = conn.execute("SELECT count(*) FROM id_checks").fetchone()[0]
        made = conn.execute("SELECT count(*) FROM project_embeddings").fetchone()[0]
    assert (asked, made) == (1, 2)
    assert len(calls.calls()) == 2  # one embedding for each project, all counted


def test_the_options_of_the_four_steps_go_with_it(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    mirrors = {"testnet": StandInMirror("testnet"), "mainnet": StandInMirror("mainnet")}
    client, _, _ = google()
    argv = ["all", "--limit", "1", "--no-requests", "--max-age-days", "0"]
    assert main(argv, settings, mirrors, client) == 0  # type: ignore[arg-type]
    said = capsys.readouterr().out
    assert "Left for a later run, because of the limit: 1." in said  # parse
    assert "Embeddings made: 1" in said


def test_a_step_that_fails_makes_the_command_fail_and_the_steps_before_it_stay(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    client, fake, _ = google()
    fake.fail_with = (400, "Invalid request")
    mirrors = {"testnet": StandInMirror("testnet"), "mainnet": StandInMirror("mainnet")}
    assert main(["all"], settings, mirrors, client) == 1  # type: ignore[arg-type]
    said = capsys.readouterr().out
    assert "== check ==" in said and "== embed ==" in said
    assert "Not made, with what went wrong:\n  project 1: ClientError" in said
    with psycopg.connect(settings.database_conninfo()) as conn:
        assert conn.execute("SELECT count(*) FROM projects").fetchone()[0] == 2
