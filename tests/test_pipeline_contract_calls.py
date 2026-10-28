"""The step `contract_calls` (pipeline/contract_calls.py), with a stand-in store and mirror node.
Everything is invented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hackathon_memory.check.system_calls import ContractCalls
from hackathon_memory.db.contract_calls import ContractToRead
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.pipeline.check_ids import NodeIsAway
from hackathon_memory.pipeline.contract_calls import (
    MAX_ERRORS_IN_A_ROW,
    STEP,
    contract_call_lines,
    read_contract_calls,
)

NOW = datetime(2026, 10, 28, 22, 0, tzinfo=UTC)
SINCE, UNTIL = datetime(2026, 2, 4, tzinfo=UTC), datetime(2026, 5, 6, tzinfo=UTC)
ADDRESS = "0x" + "ab" * 20
CONTRACT = ContractToRead(ADDRESS, "testnet", "0.0.5003", SINCE, UNTIL)


class StandInStore:
    def __init__(self, *todo: ContractToRead) -> None:
        self.todo = list(todo)
        self.saved: dict[tuple[str, str], tuple[ContractCalls, datetime]] = {}

    def to_read(self, *, projects: set[int] | None = None) -> list[ContractToRead]:
        del projects  # the stand-in holds no project
        return [one for one in self.todo if (one.entity_id, one.network) not in self.saved]

    def save(self, calls: ContractCalls, asked_at: datetime) -> None:
        self.saved[(calls.entity_id, calls.network)] = (calls, asked_at)


class Node:
    """The calls of 0.0.5003 and their actions; `away` makes every question fail."""

    def __init__(self, away: bool = False) -> None:
        self.away = away
        self.asked: list[str] = []

    def contract_results(self, contract: str, **_: object) -> list[dict]:
        self.asked.append(contract)
        if self.away:
            raise MirrorError("mirror node answered 503 for /contracts")
        return [{"hash": "0x01"}, {"hash": "0x02"}]

    def contract_actions(self, hashed: str) -> list[dict]:
        return [{"call_type": "SYSTEM", "recipient": "0.0.359"}] if hashed == "0x01" else []


def run_once(store: StandInStore, mirrors: dict, **options: object) -> Run:
    run = Run(id=1, step=STEP)
    read_contract_calls(store, mirrors, run, now=lambda: NOW, **options)  # type: ignore[arg-type]
    return run


def test_each_contract_is_read_once_by_the_id_that_the_ledger_gives() -> None:
    store, node = StandInStore(CONTRACT), Node()
    run = run_once(store, {"testnet": node})
    calls, asked_at = store.saved[(ADDRESS, "testnet")]  # kept under the ID that the page names
    assert calls == ContractCalls(ADDRESS, "testnet", SINCE, UNTIL, 2, False, {"0.0.359": 1})
    assert asked_at == NOW and node.asked == ["0.0.5003"]
    assert contract_call_lines(run) == [
        "Contracts read: 1, with 2 calls read. Cut by the limit of calls: 0. Contracts whose "
        "calls reached one of Hedera's system contracts: 1."
    ]
    run_once(store, {"testnet": node})
    assert node.asked == ["0.0.5003"]  # a second run asks nothing


def test_the_limit_and_a_network_that_is_not_asked_leave_contracts() -> None:
    other = ContractToRead("0.0.5004", "testnet", "0.0.5004", SINCE, UNTIL)
    run = run_once(StandInStore(CONTRACT, other), {"testnet": Node()}, limit=1)
    assert (run.counts["contracts_read"], run.counts["left_for_later"]) == (1, 1)
    elsewhere = run_once(StandInStore(CONTRACT), {"mainnet": Node()})
    assert elsewhere.counts["on_a_network_that_is_not_asked"] == 1


def test_errors_in_a_row_stop_the_step() -> None:
    todo = [ContractToRead(f"0.0.60{n:02d}", "testnet", f"0.0.60{n:02d}", SINCE, UNTIL)
            for n in range(MAX_ERRORS_IN_A_ROW + 2)]  # fmt: skip
    node = Node(away=True)
    with pytest.raises(NodeIsAway, match=f"{MAX_ERRORS_IN_A_ROW} times in a row"):
        run_once(StandInStore(*todo), {"testnet": node})
    assert len(node.asked) == MAX_ERRORS_IN_A_ROW
