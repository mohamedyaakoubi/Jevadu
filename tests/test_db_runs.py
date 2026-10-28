"""The table of runs, on a real PostgreSQL."""

from __future__ import annotations

import psycopg
import pytest

from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.runs import MAX_PROBLEMS, last_runs, recorded_run

pytestmark = pytest.mark.integration


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def test_a_run_is_written_at_its_start_and_closed_with_its_counts(database: str) -> None:
    with recorded_run(database, "parse") as run:
        (open_run,) = last_runs(database)
        assert (open_run["step"], open_run["finished_at"], open_run["ok"]) == ("parse", None, None)
        run.counts["new"] += 2
        run.counts["same"] += 1
        run.problem("https://example.test/a-page", "the page has no header")

    (closed,) = last_runs(database)
    assert closed["id"] == run.id
    assert closed["ok"] is True
    assert closed["finished_at"] >= closed["started_at"]
    assert closed["counts"] == {"new": 2, "same": 1}
    assert closed["problems"] == [
        {"what": "https://example.test/a-page", "rule": "the page has no header"}
    ]


def test_a_run_that_fails_is_closed_as_failed_and_the_error_goes_on(database: str) -> None:
    with (
        pytest.raises(RuntimeError, match="a text that must not be stored"),
        recorded_run(database, "check") as run,
    ):
        run.counts["asked"] += 1
        raise RuntimeError("a text that must not be stored")

    (failed,) = last_runs(database)
    assert failed["ok"] is False
    assert failed["finished_at"] is not None
    assert failed["counts"] == {"asked": 1}
    # The kind of the error is kept, and never its text.
    assert failed["problems"] == [{"what": "the step itself", "rule": "RuntimeError"}]


def test_a_run_never_ends_before_it_started_when_the_clock_steps_back(database: str) -> None:
    with recorded_run(database, "check") as run, psycopg.connect(database) as conn:
        # as if the clock of the database stepped back while the run went on
        conn.execute("UPDATE runs SET started_at = now() + interval '1 second' WHERE id = %s",
                     (run.id,))  # fmt: skip
    (row,) = last_runs(database)
    assert row["ok"] and row["finished_at"] == row["started_at"]


def test_a_run_that_was_cut_off_leaves_a_row_with_no_end(database: str) -> None:
    cut_off = recorded_run(database, "embed")
    cut_off.__enter__()  # the process dies here: the block never ends
    (row,) = last_runs(database)
    assert (row["step"], row["finished_at"], row["ok"]) == ("embed", None, None)


def test_a_run_keeps_a_fixed_number_of_problems_and_counts_the_rest(database: str) -> None:
    with recorded_run(database, "parse") as run:
        for number in range(MAX_PROBLEMS + 7):
            run.problem(f"https://example.test/page-{number}", "a rule")
    (row,) = last_runs(database)
    assert len(row["problems"]) == MAX_PROBLEMS
    assert row["counts"] == {"problems_left_out": 7}


def test_the_newest_run_comes_first_and_a_step_can_be_asked_alone(database: str) -> None:
    for step in ("parse", "check", "parse"):
        with recorded_run(database, step):
            pass
    assert [row["step"] for row in last_runs(database)] == ["parse", "check", "parse"]
    assert [row["step"] for row in last_runs(database, "check")] == ["check"]
    assert len(last_runs(database, limit=2)) == 2


@pytest.mark.parametrize(
    "change",
    [
        "INSERT INTO runs (step) VALUES ('Parse Pages')",
        "INSERT INTO runs (step, finished_at) VALUES ('parse', now())",  # an end with no result
        "INSERT INTO runs (step, ok) VALUES ('parse', true)",  # a result with no end
        "INSERT INTO runs (step, counts) VALUES ('parse', '[]')",
        "INSERT INTO runs (step, problems) VALUES ('parse', '{}')",
    ],
)
def test_the_table_refuses_a_row_that_makes_no_sense(database: str, change: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(database) as conn:
        conn.execute(change)
