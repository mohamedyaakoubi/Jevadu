"""The numbers of the measure of the comparison's thinking levels, on invented calls."""

from __future__ import annotations

from evals.compare_levels import summary


def call(level: str, seconds: float, *, failed: bool = False, answered: int = 10,
         thinking: int = 100, cost: float = 0.01, nothing: int = 0) -> dict:  # fmt: skip
    return {"idea": 1, "level": level, "seconds": seconds, "failed": failed, "projects": 10,
            "answered": 0 if failed else answered, "thinking_tokens": thinking,
            "output_tokens": 700, "cost_usd": cost, "nothing_clear": nothing}  # fmt: skip


def test_each_level_gets_its_middle_and_longest_time() -> None:
    levels = summary([call("LOW", 10.0), call("HIGH", 50.0), call("LOW", 14.0),
                      call("HIGH", 40.0, thinking=3000), call("LOW", 30.0)])  # fmt: skip
    assert list(levels) == ["LOW", "HIGH"]
    assert levels["LOW"]["seconds_middle"] == 14.0 and levels["LOW"]["seconds_longest"] == 30.0
    assert levels["HIGH"]["seconds_middle"] == 45.0
    assert levels["HIGH"]["thinking_tokens_middle"] == 1550
    assert levels["LOW"]["projects_answered"] == 30 and levels["LOW"]["projects_asked"] == 30


def test_a_failed_call_counts_its_cost_but_not_its_time() -> None:
    levels = summary([call("LOW", 12.0, nothing=2), call("LOW", 90.0, failed=True, cost=0.02)])
    low = levels["LOW"]
    assert low["calls"] == 2 and low["failed"] == 1
    assert low["seconds_longest"] == 12.0  # the failed call says nothing about the time
    assert low["cost_usd"] == 0.03  # but its money was spent
    assert low["projects_asked"] == 10 and low["nothing_clear"] == 2
