"""The test setup itself: a failed test must not print a password (design rule 9)."""

from __future__ import annotations

import psycopg
import pytest
from _pytest._io.saferepr import saferepr
from conftest import ConnectionText


def test_a_connection_text_does_not_show_itself() -> None:
    text = ConnectionText("host=127.0.0.1 user=someone password=a-password-that-protects-nothing")
    # What pytest prints for a value of a failed test, and what a log or an f-string would show
    # with !r.
    for shown in (repr(text), saferepr(text), f"{text!r}", repr([text]), repr({"database": text})):
        assert "a-password-that-protects-nothing" not in shown
        assert "not shown" in shown
    assert str(text).endswith("password=a-password-that-protects-nothing")  # still the real text


@pytest.mark.integration
def test_the_databases_of_the_tests_are_given_as_hidden_texts(
    server_conninfo: str, empty_database: str
) -> None:
    for given in (server_conninfo, empty_database):
        assert isinstance(given, ConnectionText)
        assert "password" not in repr(given)
    with psycopg.connect(empty_database) as conn:  # and the driver can still use it
        assert conn.execute("SELECT 1").fetchone() == (1,)
