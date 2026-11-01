"""The step `mainnet` (pipeline/mainnet.py), with a stand-in store and mirror node. Everything is
invented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import StandInMirror
from hackathon_memory.check.mainnet import Detail, Rate
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.pipeline.check_ids import NodeIsAway
from hackathon_memory.pipeline.mainnet import (
    MAX_ERRORS_IN_A_ROW,
    STEP,
    mainnet_lines,
    read_mainnet,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
# Two moments of one hour, and one of the next day.
ONE, TWO, LATER = "1780000000.000000001", "1780000060.000000002", "1780090000.000000003"
RATE = {"current_rate": {"cent_equivalent": 300_000, "hbar_equivalent": 30_000}}


def message(stamp: str, fee: int = 800_000) -> dict:
    return {"consensus_timestamp": stamp, "name": "CONSENSUSSUBMITMESSAGE", "result": "SUCCESS",
            "charged_tx_fee": fee, "node": "0.0.35",
            "transfers": [{"account": "0.0.802", "amount": fee},
                          {"account": "0.0.7001", "amount": -fee}]}  # fmt: skip


class StandInStore:
    def __init__(self, *todo: str) -> None:
        self.todo = list(todo)
        self.saved: dict[str, tuple[Detail, Rate | None, datetime]] = {}

    def moments_to_read(self, *, projects: set[int] | None = None) -> list[str]:
        del projects  # the stand-in holds no project
        return [one for one in self.todo if one not in self.saved]

    def save(self, detail: Detail, rate: Rate | None, asked_at: datetime) -> None:
        self.saved[detail.stamp] = (detail, rate, asked_at)


def main_node(*stamps: str) -> StandInMirror:
    mirror = StandInMirror("mainnet")
    mirror.at_moment = {stamp: message(stamp) for stamp in stamps}
    mirror.rate = RATE
    return mirror


def run_once(store: StandInStore, mirrors: dict, **options: object) -> Run:
    run = Run(id=1, step=STEP)
    read_mainnet(store, mirrors, run, now=lambda: NOW, **options)  # type: ignore[arg-type]
    return run


def test_each_moment_is_read_once_with_the_rate_of_its_hour() -> None:
    store, mirror = StandInStore(ONE, TWO, LATER), main_node(ONE, TWO, LATER)
    run = run_once(store, {"mainnet": mirror})
    assert run.counts["mainnet_read"] == 3
    detail, rate, asked = store.saved[ONE]
    assert (detail.fee, detail.paid_by, asked) == (800_000, ("0.0.7001",), NOW)
    assert rate == Rate(300_000, 30_000)
    assert mirror.moments_asked == [ONE, TWO, LATER]
    assert mirror.rates_asked == [ONE, LATER]  # one rate for the hour of ONE and TWO
    run_once(store, {"mainnet": mirror})
    assert len(mirror.moments_asked) == 3  # a second run asks nothing
    assert mainnet_lines(run) == ["Transactions on the main network read: 3."]


def test_only_the_main_network_is_asked() -> None:
    store = StandInStore(ONE)
    run = run_once(store, {"testnet": main_node(ONE)})
    assert not store.saved and not run.counts


def test_the_limit_leaves_moments_for_a_later_run() -> None:
    run = run_once(StandInStore(ONE, TWO), {"mainnet": main_node(ONE, TWO)}, limit=1)
    assert (run.counts["mainnet_read"], run.counts["mainnet_left_for_later"]) == (1, 1)
    assert "Left for a later run, because of the limit: 1." in mainnet_lines(run)


def test_a_moment_with_no_transaction_or_no_rate_is_said() -> None:
    store, mirror = StandInStore(ONE, TWO), main_node(ONE)
    mirror.rate = None
    run = run_once(store, {"mainnet": mirror})
    assert (run.counts["mainnet_read"], run.counts["mainnet_not_found"]) == (1, 1)
    assert store.saved[ONE][1] is None and TWO not in store.saved
    lines = mainnet_lines(run)
    assert "Read without the network's exchange rate: 1." in lines
    assert "Not found at their moment: 1." in lines


def test_errors_of_the_node_are_named_and_five_in_a_row_stop_the_step() -> None:
    class Away(StandInMirror):
        def transaction_at(self, stamp: str) -> dict | None:
            raise MirrorError(f"mirror node answered 503 for {stamp}")

    moments = [f"17800000{n:02d}.000000001" for n in range(MAX_ERRORS_IN_A_ROW + 2)]
    run = Run(id=1, step=STEP)
    with pytest.raises(NodeIsAway):
        read_mainnet(StandInStore(*moments), {"mainnet": Away("mainnet")}, run)
    assert run.counts["errors_of_the_node"] == MAX_ERRORS_IN_A_ROW
    assert run.problems[0]["what"] == f"the transaction of {moments[0]} on the main network"
