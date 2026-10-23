"""The checks that run while their page waits (web/checks.py): the steps as they are reported, the
bar that moves with the usual time of each step, and what is read out, with a clock that the test
moves."""

from __future__ import annotations

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
    part_done,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_a_running_step_moves_to_ninety_percent_at_its_usual_time_and_never_ends() -> None:
    assert part_done(0.0, 2.0) == 0.0
    assert part_done(1.0, 2.0) == pytest.approx(0.45)
    assert part_done(2.0, 2.0) == pytest.approx(0.9)
    assert 0.9 < part_done(4.0, 2.0) < part_done(40.0, 2.0) < 0.99


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
    done_before = PACE[GITHUB] / sum(PACE.values())
    assert first.percent == round(100 * done_before)
    clock.now += PACE[CODE]  # the code took its usual time
    later = jobs.view(job)
    assert later.say == "The code: read for Hedera" and jobs.view(job).say is None  # read once
    assert later.percent == round(100 * (PACE[GITHUB] + 0.9 * PACE[CODE]) / sum(PACE.values()))
    assert [step.elapsed_ms for step in later.steps][1] == round(1000 * PACE[CODE])
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


def test_a_check_that_nobody_asks_for_is_forgotten() -> None:
    clock = Clock()
    jobs = CheckJobs(clock=clock)
    old = jobs.start(lambda report: (200, {}))
    old.done.result(5)
    clock.now += checks.KEEP_SECONDS + 1
    jobs.start(lambda report: (200, {})).done.result(5)  # a new check clears the old ones
    assert jobs.get(old.id) is None
