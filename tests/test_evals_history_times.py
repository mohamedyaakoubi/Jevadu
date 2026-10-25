"""The times of a live reading of the history of Hedera IDs (evals/history_times.py), with a
stand-in mirror node and a clock that the test moves. Every ID here is invented."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from evals import history_times
from fakes import StandInMirror
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.settings import Settings

MADE = datetime(2026, 9, 1, tzinfo=UTC)


def topic(entity: str) -> history_times.OwnId:
    return ("testnet", entity, "topic", MADE)


class AwayMirror(StandInMirror):
    def topic_history(
        self, entity: str, *, max_rows: int, since: object = None
    ) -> tuple[list[dict], bool]:
        raise MirrorError("the node is away")


def test_each_own_id_of_the_drawn_projects_is_read_and_timed() -> None:
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.4511")] = [{"consensus_timestamp": "1780000000.000000001"}]
    found = {1: [topic("0.0.4511")], 2: [topic("0.0.4512"), topic("0.0.4513")]}
    ticks = iter([0.0, 2.0, 2.0, 5.0, 5.0, 9.0])  # the readings take 2, 3 and 4 seconds
    numbers = history_times.measure(found, {"testnet": mirror}, projects=5,
                                    clock=lambda: next(ticks))  # fmt: skip
    assert (numbers["projects"], numbers["ids"], numbers["cut"], numbers["failed"]) == (2, 3, 0, 0)
    assert numbers["seconds_per_id"]["median"] == 3.0
    assert numbers["seconds_per_project"]["all"] == 9.0  # whichever project is drawn first
    assert numbers["seconds_per_project"]["median"] == 4.5
    assert sorted(asked[1] for asked in mirror.asked) == ["0.0.4511", "0.0.4512", "0.0.4513"]


def test_a_reading_that_fails_is_counted_and_not_timed() -> None:
    numbers = history_times.measure({1: [topic("0.0.4511")]}, {"testnet": AwayMirror()})
    assert (numbers["ids"], numbers["failed"]) == (0, 1) and "seconds_per_id" not in numbers


def test_the_result_file_holds_numbers_and_no_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(history_times, "RESULTS", tmp_path)
    monkeypatch.setattr(history_times, "own_ids", lambda conninfo: {7: [topic("0.0.4511")]})
    settings = Settings(_env_file=None, database_url="postgresql://stand-in/none")
    assert history_times.main([], settings, {"testnet": StandInMirror()}) == 0
    written = next(tmp_path.glob("*-history-times.json")).read_text(encoding="utf-8")
    assert '"ids": 1' in written and "0.0.4511" not in written
    assert "For one project: median" in capsys.readouterr().out
    assert history_times.main(["--projects", "0"], settings, {"testnet": StandInMirror()}) == 2
