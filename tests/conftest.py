"""Shared test setup.

Integration tests use the real PostgreSQL that `docker compose up -d db` starts. Each test gets
its own empty database, which is dropped afterwards. If the server is not running, the test
FAILS, it does not skip: a skipped test would look like a pass.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from hackathon_memory.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_setting_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts without any setting in the environment.

    A value on the machine (a POSTGRES_PASSWORD set by CI, a COLLECT_ETHGLOBAL=on in a shell) must
    not change what a test does. A test that needs a setting passes it itself. The database tests
    read the real environment once, in the session fixture below, which is created before this
    one (a fixture of a wider scope always comes first).
    """
    for name in (*Settings.model_fields, "database_url"):
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture(scope="session")
def server_conninfo() -> str:
    """The local PostgreSQL server. Holds a password: never print it."""
    info = Settings(_env_file=ROOT / ".env").database_conninfo()
    try:
        with psycopg.connect(info, connect_timeout=5):
            pass
    except psycopg.OperationalError:
        # The text of this error is not shown on purpose (it can hold connection details).
        pytest.fail("The test database is not reachable. Start it with: docker compose up -d db")
    return info


@pytest.fixture
def empty_database(server_conninfo: str) -> Iterator[str]:
    """A new empty database on the local server. Yields its connection text."""
    name = "hm_test_" + secrets.token_hex(6)
    with psycopg.connect(server_conninfo, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(server_conninfo, dbname=name)
    finally:
        with psycopg.connect(server_conninfo, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
