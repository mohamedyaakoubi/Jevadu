"""The checks of submissions that run while the page waits (design 12.1, S3).

A check runs in a thread of its own and reports each of its steps as it starts and ends. The page
asks for the steps about twice a second and shows them: waiting, running, done, done at once
from the tool's tables, or nothing to read. One bar moves with the time that each step usually
takes, and never fills before the answer is there. When the answer is there, the page takes it
and the check is forgotten; a check that nobody asks for again is forgotten after KEEP_SECONDS.
"""

from __future__ import annotations

import contextvars
import logging
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from hackathon_memory.check.submission import (
    CODE,
    DONE,
    GITHUB,
    HISTORY,
    LEDGER,
    RUNNING,
    SAVED,
    SKIPPED,
)

LOG = logging.getLogger(__name__)
WAITING = "waiting"
COLLECTION = "collection"  # the last step, which the website runs: seen before and the closest
STEPS = (
    (GITHUB, "GitHub: the dates of the code and its README"),
    (CODE, "The code: read for Hedera"),
    (LEDGER, "The Hedera ledger: each ID that the README names"),
    (HISTORY, "The history of those IDs: their transactions"),
    (COLLECTION, "The collection: the same code or IDs, and the most similar past projects"),
)
STATE_WORDS = {
    WAITING: "waiting",
    RUNNING: "running",
    DONE: "done",
    SAVED: "done, from the tool's tables",
    SKIPPED: "nothing to read",
}
# How long each step may take when it asks, in seconds: the pace of the bar only, never shown.
# Generous on purpose, so that the bar runs behind and jumps forward when a step ends, rather than
# running ahead and then standing still near its end. GitHub: three requests, one second apart
# (design 7.3). The code and the histories: between the median and the 90th of 100 of
# evals/results/*-code-times.json (3.45 and 10.8 s) and *-history-times.json (1.4 and 7.0 s).
# The ledger: a few questions to the mirror node for each ID. The collection: an embedding of the
# README and a search in the tables.
PACE = {GITHUB: 3.5, CODE: 6.0, LEDGER: 3.0, HISTORY: 3.0, COLLECTION: 3.0}
KEEP_SECONDS = 600
MOST = 0.97  # the bar never passes this before the answer is there

Answer = tuple[int, dict]  # the status of the page, and what it shows
Progress = Callable[[str, str], None]


@dataclass
class CheckJob:
    id: str
    started: float
    # A check starts with its first step at once, so the page never shows a check that waits.
    states: dict[str, str] = field(
        default_factory=lambda: {
            key: RUNNING if n == 0 else WAITING for n, (key, _) in enumerate(STEPS)
        }
    )
    since: dict[str, float] = field(default_factory=dict)  # when each step took its state
    answer: Answer | None = None
    said: str | None = None  # the step that the page last read out
    done: Future | None = field(default=None, repr=False)  # ends with the check


@dataclass(frozen=True)
class StepView:
    key: str
    label: str
    state: str
    elapsed_ms: int = 0  # how long it has been running, so that its turning mark goes on

    @property
    def words(self) -> str:
        return STATE_WORDS[self.state]


@dataclass(frozen=True)
class JobView:
    """What the page shows of a check that runs."""

    id: str
    steps: tuple[StepView, ...]
    percent: int  # how far the bar is, from the steps done and the time of the running one
    say: str | None  # the step to read out, when it changed since the page last asked
    running: str | None  # the key of the running step


def still_to_come(states: dict[str, str], running_for: float) -> float:
    """The seconds that the check may still take: the pace of each step that waits, and what is
    left of the pace of the running one, never less than a quarter of it."""
    left = 0.0
    for key, _ in STEPS:
        if states[key] == WAITING:
            left += PACE[key]
        elif states[key] == RUNNING:
            left += max(PACE[key] - running_for, PACE[key] / 4)
    return left


def share_done(elapsed: float, left: float) -> float:
    """How far the bar is: the time spent, out of the time spent and the time still to come. It
    always moves, slower near its end, and jumps forward when a step ends early."""
    total = elapsed + left
    return min(MOST, elapsed / total) if total > 0 else 0.0


class CheckJobs:
    """The checks that run, by their number. Thread-safe."""

    def __init__(self, workers: int = 2, clock: Callable[[], float] = time.monotonic) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="check")
        self._jobs: dict[str, CheckJob] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def start(self, work: Callable[[Progress], Answer]) -> CheckJob:
        """Run `work` in a thread; it reports its steps, and returns what the page shows. The
        thread sees what the request that started it knew, such as the visitor of the public
        copy (web/public.py): a thread of the pool starts with nothing of its own."""
        job = CheckJob(secrets.token_urlsafe(12), self._clock())
        with self._lock:
            self._forget_old()
            self._jobs[job.id] = job

        def report(step: str, state: str) -> None:
            with self._lock:
                job.states[step] = state
                job.since[step] = self._clock()

        def run() -> None:
            try:
                answer = work(report)
            except Exception:  # the page says so in plain words; the log keeps the details
                LOG.exception("a check failed")
                answer = (500, {})
            with self._lock:
                job.answer = answer

        job.done = self._pool.submit(contextvars.copy_context().run, run)
        return job

    def get(self, job_id: str) -> CheckJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def view(self, job: CheckJob, *, announce: bool = True) -> JobView:
        """The steps of a check as the page shows them now, and the step to read out when it
        changed: `announce` False keeps it for the next time."""
        with self._lock:
            now = self._clock()
            states = dict(job.states)
            running = next((key for key, _ in STEPS if states[key] == RUNNING), None)
            running_for = now - job.since.get(running, job.started) if running else 0.0
            percent = round(100 * share_done(now - job.started, still_to_come(states, running_for)))
            say = None
            if announce and running is not None and running != job.said:
                job.said = running
                say = dict(STEPS)[running]
            since = {key: now - job.since.get(key, job.started) for key, _ in STEPS}
        steps = tuple(StepView(key, label, states[key], round(1000 * since[key]))
                      for key, label in STEPS)  # fmt: skip
        return JobView(job.id, steps, percent, say, running)

    def _forget_old(self) -> None:
        old = [key for key, job in self._jobs.items()
               if self._clock() - job.started > KEEP_SECONDS]  # fmt: skip
        for key in old:
            del self._jobs[key]
