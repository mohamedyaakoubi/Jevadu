"""The count of Gemini's failures in a row, after which its stand-in takes its place for a while
(search/stand_in.py, design 8.2)."""

from __future__ import annotations

from hackathon_memory.search import stand_in


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_fifth_failure_in_a_row_gives_the_stand_in_its_turn() -> None:
    clock = Clock()
    breaker = stand_in.Breaker(clock=clock)
    assert not breaker.standing_in() and breaker.left() == stand_in.FAILURES
    assert [breaker.failed() for _ in range(stand_in.FAILURES)] == [False] * 4 + [True]
    assert breaker.standing_in()
    clock.now += stand_in.SECONDS - 1
    assert breaker.standing_in()
    clock.now += 1  # the turn is over: Gemini is asked again
    assert not breaker.standing_in() and breaker.left() == stand_in.FAILURES


def test_an_answer_of_gemini_starts_the_count_again() -> None:
    breaker = stand_in.Breaker(clock=Clock())
    for _ in range(stand_in.FAILURES - 1):
        breaker.failed()
    assert breaker.left() == 1
    breaker.answered()
    assert breaker.left() == stand_in.FAILURES and not breaker.failed()
