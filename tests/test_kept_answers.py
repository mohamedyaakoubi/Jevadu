"""The answers of GitHub that a check saved, shared between the copies of the public copy on Vercel
(web/kept_answers.py, migration 0033, 7 November 2026)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import psycopg
import pytest

from hackathon_memory.db.migrate import migrate
from hackathon_memory.web.kept_answers import persist, restore, written_since

REPOSITORY = "https://github.com/sample-org/pebble-pay"


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def test_a_copy_keeps_what_it_wrote_and_another_writes_it_back(
    database: str, tmp_path: Path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    github = first / "raw" / "api.github.com"
    github.mkdir(parents=True)
    old = github / "before.json"
    old.write_text("{}")  # written before the check: not this check's
    os.utime(old, (time.time() - 60, time.time() - 60))
    bundled = tmp_path / "bundle.json"
    bundled.write_text("{}")
    since = time.time() - 1
    readme = github / "readme" / "abc.json"
    readme.parent.mkdir()
    readme.write_bytes(b'{"content": "a README"}')
    (github / "abc.meta.json").write_text('{"status": 200}')
    try:
        (github / "linked.json").symlink_to(bundled)  # a file of the deployment: every copy has it
    except OSError:
        pass  # Windows may refuse to make a link: the rest of the test still holds
    assert sorted(path.name for path in written_since(github, since)) == [
        "abc.json",
        "abc.meta.json",
    ]
    assert persist(database, first, github, REPOSITORY, since) == 2
    assert persist(database, first, github, REPOSITORY, since) == 0  # kept once
    assert restore(database, second, REPOSITORY) == 2
    copied = second / "raw" / "api.github.com" / "readme" / "abc.json"
    assert copied.read_bytes() == b'{"content": "a README"}'
    copied.write_bytes(b"changed here")
    assert restore(database, second, REPOSITORY) == 0  # what a copy holds is never written over
    assert copied.read_bytes() == b"changed here"
    assert restore(database, second, "https://github.com/someone/else") == 0


def test_a_kept_path_never_reaches_outside_the_data_folder(database: str, tmp_path: Path) -> None:
    with psycopg.connect(database) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO kept_answers (path, repository, body) VALUES "
                     "('../../outside.json', %s, '\\x00')", (REPOSITORY,))  # fmt: skip
    assert restore(database, tmp_path / "copy", REPOSITORY) == 0
    assert not (tmp_path / "outside.json").exists()
