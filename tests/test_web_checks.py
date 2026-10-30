"""The checks that run while their page waits (web/checks.py): the steps as they are reported, the
bar that moves with the usual time of each step, and what is read out, with a clock that the test
moves."""

from __future__ import annotations

import contextvars
import threading

import pytest

from hackathon_memory.web import checks
from hackathon_memory.web.checks import (
    CODE,
    COLLECTION,
    DONE,
    GITHUB,
    HISTORY,
    LEDGER,
    PACE,
    RUNNING,
    SAVED,
    SKIPPED,
    WAITING,
    CheckJobs,
    share_done,
    still_to_come,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_the_bar_is_the_time_spent_out_of_the_time_spent_and_still_to_come() -> None:
    waiting = {key: WAITING for key, _ in checks.STEPS}
    assert still_to_come(waiting, 0.0) == sum(PACE.values())
    running = {**waiting, GITHUB: RUNNING}
    assert still_to_come(running, 1.0) == sum(PACE.values()) - 1.0
    late = still_to_come(running, 60.0)  # a step that takes long still has a quarter to come
    assert late == sum(PACE.values()) - PACE[GITHUB] + PACE[GITHUB] / 4
    assert share_done(0.0, 10.0) == 0.0
    assert share_done(5.0, 5.0) == pytest.approx(0.5)
    assert share_done(5.0, 0.0) == checks.MOST  # never full before the answer
    moving = [share_done(t, still_to_come({**waiting, GITHUB: RUNNING}, t)) for t in (1, 3, 9)]
    assert moving == sorted(moving) and len(set(moving)) == 3  # it always moves


def test_the_steps_show_their_states_and_the_bar_follows_them() -> None:
    clock = Clock()
    jobs = CheckJobs(clock=clock)
    gate, reached = threading.Event(), threading.Event()

    def work(report: checks.Progress) -> checks.Answer:
        report(GITHUB, RUNNING)
        report(GITHUB, SAVED)
        report(CODE, RUNNING)
        reached.set()
        gate.wait(5)
        for step, state in ((CODE, DONE), (LEDGER, SKIPPED), (HISTORY, SKIPPED),
                            (COLLECTION, DONE)):  # fmt: skip
            report(step, state)
        return 200, {"result": "shown"}

    job = jobs.start(work)
    assert reached.wait(5)
    first = jobs.view(job, announce=False)
    assert [step.state for step in first.steps] == [SAVED, RUNNING, WAITING, WAITING, WAITING]
    assert first.say is None and first.running == CODE  # the first page reads out nothing yet
    assert first.percent == 0  # no time has passed yet
    clock.now += 2.0
    later = jobs.view(job)
    assert later.say == "The code: read for Hedera" and jobs.view(job).say is None  # read once
    to_come = PACE[CODE] - 2.0 + PACE[LEDGER] + PACE[HISTORY] + PACE[COLLECTION]
    assert later.percent == round(100 * 2.0 / (2.0 + to_come))
    assert [step.elapsed_ms for step in later.steps][1] == 2000  # the code ran for 2 seconds
    assert job.answer is None
    gate.set()
    job.done.result(5)
    assert job.answer == (200, {"result": "shown"})
    assert jobs.get(job.id) is job
    jobs.forget(job.id)
    assert jobs.get(job.id) is None


def test_a_check_that_fails_answers_with_the_status_of_a_failure() -> None:
    jobs = CheckJobs()

    def broken(report: checks.Progress) -> checks.Answer:
        raise RuntimeError("invented")

    job = jobs.start(broken)
    job.done.result(5)
    assert job.answer == (500, {})


def test_a_check_runs_with_what_its_request_knew() -> None:
    """The visitor of the public copy goes with the request (web/public.py): a check that ran in a
    bare thread of the pool knew no visitor, so its call to a model was refused."""
    visitor: contextvars.ContextVar[str | None] = contextvars.ContextVar("visitor", default=None)
    jobs = CheckJobs()
    token = visitor.set("one visitor")
    try:
        job = jobs.start(lambda report: (200, {"visitor": visitor.get()}))
    finally:
        visitor.reset(token)
    job.done.result(5)
    assert job.answer == (200, {"visitor": "one visitor"})
    alone = jobs.start(lambda report: (200, {"visitor": visitor.get()}))
    alone.done.result(5)
    assert alone.answer == (200, {"visitor": None})  # a check of no request knows nobody


def test_a_check_that_nobody_asks_for_is_forgotten() -> None:
    clock = Clock()
    jobs = CheckJobs(clock=clock)
    old = jobs.start(lambda report: (200, {}))
    old.done.result(5)
    clock.now += checks.KEEP_SECONDS + 1
    jobs.start(lambda report: (200, {})).done.result(5)  # a new check clears the old ones
    assert jobs.get(old.id) is None
