"""The table of runs: what ran, when, and what came out (design 11.6, migration 0004).

A step of the path opens a run, counts what it does, and names what it could not do. The row is
written when the step starts, so a step that was cut off leaves a row with no end: that is seen
later, and not taken for a step that never ran.

A count is a number. A problem is an address and the rule that failed. No text of a page goes
into this table.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

# How many problems one run keeps. A step that fails on every page must not fill the table.
MAX_PROBLEMS = 200


@dataclass
class Run:
    """One run of a step, while it goes on."""

    id: int
    step: str
    counts: Counter[str] = field(default_factory=Counter)
    problems: list[dict[str, str]] = field(default_factory=list)
    problems_left_out: int = 0

    def problem(self, what: str, rule: str) -> None:
        """Name something that could not be done: an address, and the rule that failed."""
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append({"what": what, "rule": rule})
        else:
            self.problems_left_out += 1


@contextmanager
def recorded_run(conninfo: str, step: str) -> Iterator[Run]:
    """Open a run of `step`, and close it with its counts when the block ends.

    A block that raises closes the run as failed, with the kind of the error as a problem, and
    the error goes on to the caller.
    """
    with psycopg.connect(conninfo, autocommit=True) as conn:
        row = conn.execute("INSERT INTO runs (step) VALUES (%s) RETURNING id", (step,)).fetchone()
    run = Run(id=row[0], step=step)
    ok = False
    try:
        yield run
        ok = True
    except BaseException as error:
        # The kind of the error only: its text can hold a connection text or a piece of a page.
        run.problem("the step itself", type(error).__name__)
        raise
    finally:
        counts = dict(run.counts)
        if run.problems_left_out:
            counts["problems_left_out"] = run.problems_left_out
        # The clock of the database can step back when its machine sets its time again (the
        # Docker machine of this laptop did, by 0.65 s, on 23 October 2026): a run never ends
        # before it started.
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(
                "UPDATE runs SET finished_at = greatest(now(), started_at), ok = %s, "
                "counts = %s, problems = %s WHERE id = %s",
                (ok, Jsonb(counts), Jsonb(run.problems), run.id),
            )


def last_runs(conninfo: str, step: str | None = None, limit: int = 10) -> list[dict]:
    """The newest runs first, each as a small record."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT id, step, started_at, finished_at, ok, counts, problems FROM runs "
            "WHERE (%s::text IS NULL OR step = %s) ORDER BY id DESC LIMIT %s",
            (step, step, limit),
        ).fetchall()
    names = ("id", "step", "started_at", "finished_at", "ok", "counts", "problems")
    return [dict(zip(names, row, strict=True)) for row in rows]
