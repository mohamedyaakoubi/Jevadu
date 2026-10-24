"""The stand-in for the search model (design 8.2): when Gemini fails FAILURES times in a row, the
order of the closest projects and the comparisons come from DeepSeek V4.1 Flash on Vertex AI for
SECONDS; then Gemini is asked again.

The maintainer asked on 24 October 2026 for this switch after five failures in a row. That day
Google's service answered the search model with errors for minutes at a time, and then answered
again. The count lives in the process of the website: it is about the service now, not a fact to
keep.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hackathon_memory.llm.open_models import DEEPSEEK_FLASH

FAILURES = 5  # Gemini's failures in a row before the stand-in takes its place
SECONDS = 600.0  # how long the stand-in keeps its place before Gemini is asked again
MODEL = DEEPSEEK_FLASH
NAME = "DeepSeek V4.1 Flash"  # the name the page shows


@dataclass
class Breaker:
    """Counts the failures of Gemini in a row, and says when the stand-in has its place."""

    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    until: float = 0.0  # on the clock: the end of the stand-in's turn
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def standing_in(self) -> bool:
        """True while the stand-in has Gemini's place."""
        with self._lock:
            return self.clock() < self.until

    def failed(self) -> bool:
        """One more failure of Gemini; True when it was the last one before the stand-in."""
        with self._lock:
            self.failures += 1
            if self.failures < FAILURES:
                return False
            self.failures = 0
            self.until = self.clock() + SECONDS
            return True

    def answered(self) -> None:
        """Gemini answered: the count starts again."""
        with self._lock:
            self.failures = 0

    def left(self) -> int:
        """The failures in a row that Gemini has left before the stand-in takes its place."""
        with self._lock:
            return FAILURES - self.failures
