"""Reading again while the website runs (design 7.3, 25 October 2026).

The step `refresh` (pipeline/refresh.py) asks GitHub and the ledger again about what is old. The
website runs the same work on a thread of its own, so that what a page shows keeps up with the
repositories and the ledger:

* **rounds:** when REFRESH_IN_BACKGROUND is on, a round every few minutes asks again, at most a
  few requests of each kind, for what is older than its age; the oldest answers come first;
* **one project, at once:** the button "Read again now" of a card asks again about that project
  only, with no age, before the next round. The card asks for the state of its reading and shows
  itself again when it is done.

One thread, one task at a time: GitHub is asked one request after the other, with its pause,
through the one client of the website.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

LOG = logging.getLogger(__name__)
WAITING, RUNNING, DONE, FAILED = "waiting", "running", "done", "failed"
ROUND_EVERY = 300.0  # seconds between two rounds
ROUND_LIMIT = 30  # requests of each kind in one round: about two minutes of GitHub's pace

# What does the work: the projects (None for all), the age, the most requests of each kind.
Work = Callable[[set[int] | None, timedelta, int | None], None]


@dataclass(frozen=True)
class State:
    """Where the reading of one project stands, for its card."""

    status: str  # WAITING, RUNNING, DONE or FAILED
    since: datetime
    problem: str | None = None


class Refresher:
    """Reads again on a thread of its own. `inline` does each asked project at once, on the
    thread that asks, for the tests."""

    def __init__(
        self,
        work: Work,
        *,
        older_than: timedelta,
        round_every: float = ROUND_EVERY,
        limit: int = ROUND_LIMIT,
        inline: bool = False,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._work = work
        self._older_than = older_than
        self._round_every = round_every
        self._limit = limit
        self._inline = inline
        self._now = now
        self._asked: deque[int] = deque()
        self._states: dict[int, State] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._rounds = False
        self._thread: threading.Thread | None = None
        self.rounds_done = 0

    def state(self, project_id: int) -> State | None:
        with self._lock:
            return self._states.get(project_id)

    def ask(self, project_id: int) -> State:
        """Read one project again before the next round. Asked twice while it waits or runs, it
        is read once."""
        with self._lock:
            known = self._states.get(project_id)
            if known is not None and known.status in (WAITING, RUNNING):
                return known
            state = State(WAITING, self._now())
            self._states[project_id] = state
            if not self._inline:
                self._asked.append(project_id)
        if self._inline:
            self._one(project_id)
            return self._states[project_id]
        self._start()
        self._wake.set()
        return state

    def start_rounds(self) -> None:
        """Turn the rounds on, and start the thread."""
        self._rounds = True
        self._start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _start(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="refresher", daemon=True)
                self._thread.start()

    def _one(self, project_id: int) -> None:
        with self._lock:
            self._states[project_id] = State(RUNNING, self._now())
        try:
            self._work({project_id}, timedelta(0), None)
        except Exception as error:  # the card says so; the log keeps the details
            LOG.exception("reading project %s again failed", project_id)
            with self._lock:
                self._states[project_id] = State(FAILED, self._now(), type(error).__name__)
            return
        with self._lock:
            self._states[project_id] = State(DONE, self._now())

    def _loop(self) -> None:
        last_round = -self._round_every  # the first round comes at once
        while not self._stop.is_set():
            with self._lock:
                project_id = self._asked.popleft() if self._asked else None
            if project_id is not None:
                self._one(project_id)
                continue
            if self._rounds and time.monotonic() - last_round >= self._round_every:
                last_round = time.monotonic()
                try:
                    self._work(None, self._older_than, self._limit)
                except Exception:  # the next round tries again; the log keeps the details
                    LOG.exception("a round of reading again failed")
                self.rounds_done += 1
                continue
            self._wake.wait(timeout=self._round_every if self._rounds else None)
            self._wake.clear()
