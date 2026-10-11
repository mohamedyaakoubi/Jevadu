"""Shared test setup.

Integration tests use the real PostgreSQL that `docker compose up -d db` starts. Each test gets
its own empty database, which is dropped afterwards. If the server is not running, the test
FAILS, it does not skip: a skipped test would look like a pass.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from hackathon_memory.finops import prices
from hackathon_memory.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
TEST_DAY = date(2026, 10, 10)


@pytest.fixture(autouse=True)
def the_day_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs on 10 October 2026.

    The price of a model depends on the day: Gemini 3.8 Flash costs double from 1 January 2027.
    A test that reads the clock would turn red on that day for no fault of the code. A test
    about another day passes the day itself.
    """
    monkeypatch.setattr(prices, "today", lambda: TEST_DAY)


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


class ConnectionText(str):
    """A connection text that does not show itself.

    It holds a password. When a test fails, pytest prints the values that the test was given,
    and a plain text would be printed whole. This one prints as a short note. It is still the
    real text for the database driver.

    One way to print it is left: a test that compares this text with another text and fails
    gets both texts printed side by side. So no test compares a connection text.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<connection text, not shown>"


@pytest.fixture(scope="session")
def server_conninfo() -> str:
    """The local PostgreSQL server. Holds a password: never print it."""
    info = ConnectionText(Settings(_env_file=ROOT / ".env").database_conninfo())
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
        yield ConnectionText(make_conninfo(server_conninfo, dbname=name))
    finally:
        with psycopg.connect(server_conninfo, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
