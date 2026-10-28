"""The test setup itself: a failed test must not print a password (design rule 9)."""

from __future__ import annotations

import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import psycopg
import pytest
from _pytest._io.saferepr import saferepr
from conftest import ROOT, ConnectionText

FAKE = "a-password-that-protects-nothing"
# A failing test whose library function holds the password in an argument, as the database driver
# does when it rebuilds the connection text in its own functions. The source never holds the whole
# word, so only the printed arguments can show it.
INNER = """
FAKE = "a-password-" + "that-protects-nothing"


def connect(conninfo):
    raise ConnectionError("the server closed the connection")


def test_inner():
    connect("host=127.0.0.1 password=" + FAKE)
"""


def test_a_connection_text_does_not_show_itself() -> None:
    text = ConnectionText(f"host=127.0.0.1 user=someone password={FAKE}")
    # What pytest prints for a value of a failed test, and what a log or an f-string would show
    # with !r.
    for shown in (repr(text), saferepr(text), f"{text!r}", repr([text]), repr({"database": text})):
        assert FAKE not in shown
        assert "not shown" in shown
    assert str(text).endswith(f"password={FAKE}")  # still the real text


def run_inner(folder: Path, *options: str) -> str:
    """Runs the failing test INNER in a pytest of its own, with `options`, and returns what it
    printed."""
    (folder / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (folder / "test_inner.py").write_text(INNER, encoding="utf-8")
    done = subprocess.run(  # noqa: S603 (this Python, a file of its own)
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *options, str(folder)],
        cwd=folder, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    return done.stdout + done.stderr


def test_a_failed_test_does_not_print_the_arguments_of_a_library(tmp_path: Path) -> None:
    """The connection text is hidden in the frames of the tests (above), but the database driver
    rebuilds it as a plain string in its own; pytest's long style prints the arguments of a frame,
    so the options of the project choose the short style."""
    ours = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    options = shlex.split(ours["tool"]["pytest"]["ini_options"]["addopts"])
    assert FAKE in run_inner(tmp_path, "--tb=long")  # the inner test does show it, in that style
    shown = run_inner(tmp_path, *options)
    assert "1 failed" in shown
    assert FAKE not in shown


@pytest.mark.integration
def test_the_databases_of_the_tests_are_given_as_hidden_texts(
    server_conninfo: str, empty_database: str
) -> None:
    for given in (server_conninfo, empty_database):
        assert isinstance(given, ConnectionText)
        assert "password" not in repr(given)
    with psycopg.connect(empty_database) as conn:  # and the driver can still use it
        assert conn.execute("SELECT 1").fetchone() == (1,)
