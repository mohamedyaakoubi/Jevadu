"""The step `history` (pipeline/history.py), with a stand-in store and mirror node. Everything is
invented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import StandInMirror
from hackathon_memory.check.history import CONSENSUS, History
from hackathon_memory.db.history import IdToRead
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.parse.hedera_ids import CONTRACT, TOPIC
from hackathon_memory.pipeline.check_ids import NodeIsAway
from hackathon_memory.pipeline.history import (
    MAX_ERRORS_IN_A_ROW,
    STEP,
    history_lines,
    read_histories,
)

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
ONE, TWO = "1780000000.000000001", "1780000060.000000002"
TOPIC_ID = IdToRead("0.0.5002", "testnet", TOPIC, "0.0.5002")
CONTRACT_ID = IdToRead("0x" + "ab" * 20, "testnet", CONTRACT, "0.0.5003")


class StandInStore:
    def __init__(self, *todo: IdToRead) -> None:
        self.todo = list(todo)
        self.saved: dict[tuple[str, str], tuple[str, History, datetime]] = {}

    def ids_to_read(
        self, *, again: bool = False, projects: set[int] | None = None
    ) -> list[IdToRead]:
        del again, projects  # the stand-in holds no history of before, and no project
        return [one for one in self.todo if (one.entity_id, one.network) not in self.saved]

    def save(
        self, entity_id: str, network: str, kind: str, history: History, asked_at: datetime
    ) -> None:
        self.saved[(entity_id, network)] = (kind, history, asked_at)


def a_node() -> StandInMirror:
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.5002")] = [{"consensus_timestamp": ONE}]
    mirror.lists[("calls", "0.0.5003")] = [{"timestamp": ONE}, {"timestamp": TWO}]
    return mirror


def run_once(store: StandInStore, mirrors: dict, **options: object) -> Run:
    run = Run(id=1, step=STEP)
    read_histories(store, mirrors, run, now=lambda: NOW, **options)  # type: ignore[arg-type]
    return run


def test_each_id_is_read_once_and_counted() -> None:
    store, mirror = StandInStore(TOPIC_ID, CONTRACT_ID), a_node()
    run = run_once(store, {"testnet": mirror})
    assert (run.counts["ids_read"], run.counts["events"], run.counts["ids_cut"]) == (2, 3, 0)
    assert store.saved[("0.0.5002", "testnet")] == (TOPIC, History({ONE: CONSENSUS}, False), NOW)
    asked = len(mirror.asked)
    run_once(store, {"testnet": mirror})
    assert len(mirror.asked) == asked  # a second run asks nothing


def test_an_evm_address_is_asked_by_the_id_that_the_ledger_gives() -> None:
    store, mirror = StandInStore(CONTRACT_ID), a_node()
    run_once(store, {"testnet": mirror})
    assert mirror.asked == [("calls", "0.0.5003", "history")]
    assert ("0x" + "ab" * 20, "testnet") in store.saved  # kept under the ID that the page names


def test_the_limit_leaves_ids_for_a_later_run() -> None:
    run = run_once(StandInStore(TOPIC_ID, CONTRACT_ID), {"testnet": a_node()}, limit=1)
    assert (run.counts["ids_read"], run.counts["left_for_later"]) == (1, 1)
    assert "Left for a later run, because of the limit: 1." in history_lines(run)


def test_an_id_on_a_network_that_is_not_asked_is_counted_and_left() -> None:
    store = StandInStore(IdToRead("0.0.5002", "previewnet", TOPIC, "0.0.5002"))
    run = run_once(store, {"testnet": a_node()})
    assert run.counts["on_a_network_that_is_not_asked"] == 1 and not store.saved


class AwayNode(StandInMirror):
    def topic_history(
        self, entity: str, *, max_rows: int, since: object = None
    ) -> tuple[list[dict], bool]:
        self.asked.append(("messages", entity, "history"))
        raise MirrorError("mirror node answered 503 for /topics")


def test_an_error_is_named_and_several_in_a_row_stop_the_step() -> None:
    ids = [
        IdToRead(f"0.0.60{n:02d}", "testnet", TOPIC, None) for n in range(MAX_ERRORS_IN_A_ROW + 2)
    ]
    node = AwayNode()
    run = Run(id=1, step=STEP)
    with pytest.raises(NodeIsAway, match=f"{MAX_ERRORS_IN_A_ROW} times in a row"):
        read_histories(StandInStore(*ids), {"testnet": node}, run, now=lambda: NOW)
    assert len(node.asked) == MAX_ERRORS_IN_A_ROW  # nothing more was asked
    assert run.problems[0] == {
        "what": "0.0.6000 on testnet",
        "rule": "mirror node answered 503 for /topics",
    }


def test_the_lines_say_what_was_read_in_plain_words() -> None:
    run = run_once(StandInStore(TOPIC_ID, CONTRACT_ID), {"testnet": a_node()})
    assert history_lines(run) == [
        "Histories read: 2, with 3 events in all. Cut by the limit of events: 0."
    ]


def test_an_account_is_asked_from_the_moment_the_ledger_says_it_was_made() -> None:
    from hackathon_memory.parse.hedera_ids import ACCOUNT

    made = datetime(2025, 11, 6, 17, 58, tzinfo=UTC)
    mirror = a_node()
    run_once(
        StandInStore(IdToRead("0.0.5010", "mainnet", ACCOUNT, "0.0.5010", made)),
        {"mainnet": mirror},
    )
    assert mirror.since == {"0.0.5010": made}
