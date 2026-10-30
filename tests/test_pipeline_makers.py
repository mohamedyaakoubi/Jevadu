"""The step `makers` (pipeline/makers.py), with a stand-in store and mirror node. Everything is
invented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hackathon_memory.db.makers import ThingToAsk
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.pipeline.check_ids import NodeIsAway
from hackathon_memory.pipeline.makers import MAX_ERRORS_IN_A_ROW, STEP, maker_lines, read_makers

NOW = datetime(2026, 10, 29, 22, 0, tzinfo=UTC)
MADE = datetime(2026, 3, 7, tzinfo=UTC)
CONTRACT = ThingToAsk("0x" + "ab" * 20, "testnet", "contract", "0.0.5003", MADE, "0.0.7001")
TOPIC = ThingToAsk("0.0.6001", "testnet", "topic", "0.0.6001", MADE, None)
TOKEN = ThingToAsk("0.0.6002", "testnet", "token", "0.0.6002", MADE, None)


class StandInStore:
    def __init__(self, *todo: ThingToAsk) -> None:
        self.todo = list(todo)
        self.saved: dict[tuple[str, str], tuple[str | None, datetime]] = {}

    def to_ask(self, *, projects: set[int] | None = None) -> list[ThingToAsk]:
        del projects  # the stand-in holds no project
        return [one for one in self.todo if (one.entity_id, one.network) not in self.saved]

    def save(self, entity_id: str, network: str, made_by: str | None, asked_at: datetime) -> None:
        self.saved[(entity_id, network)] = (made_by, asked_at)


class Node:
    """The creation of 0.0.6001, paid by 0.0.7002; nothing for any other thing. `away` makes
    every question fail."""

    def __init__(self, away: bool = False) -> None:
        self.away = away
        self.asked = 0

    def transactions_at(self, since: datetime, until: datetime, *, limit: int = 25) -> list[dict]:
        del since, until, limit
        self.asked += 1
        if self.away:
            raise MirrorError("mirror node unreachable (ConnectionError)")
        return [{"entity_id": "0.0.6001", "transaction_id": "0.0.7002-1772841600-000000001"}]


def test_a_maker_comes_from_the_history_or_from_one_question_to_the_node() -> None:
    store, node, run = StandInStore(CONTRACT, TOPIC, TOKEN), Node(), Run(id=1, step=STEP)
    read_makers(store, {"testnet": node}, run, now=lambda: NOW)
    assert store.saved == {
        (CONTRACT.entity_id, "testnet"): ("0.0.7001", NOW),  # its history held the creation
        ("0.0.6001", "testnet"): ("0.0.7002", NOW),
        ("0.0.6002", "testnet"): (None, NOW),  # the node gave none: asked, and not again
    }
    assert node.asked == 2
    assert maker_lines(run) == [
        "Makers kept: 1 from the histories already read, 1 from the mirror node. The node gave "
        "no account for 1."
    ]
    read_makers(store, {"testnet": node}, Run(id=1, step=STEP), now=lambda: NOW)
    assert node.asked == 2  # each thing is asked once


def test_the_limit_counts_the_questions_to_the_node() -> None:
    store, node, run = StandInStore(CONTRACT, TOPIC, TOKEN), Node(), Run(id=1, step=STEP)
    read_makers(store, {"testnet": node}, run, limit=1, now=lambda: NOW)
    assert node.asked == 1 and len(store.saved) == 2
    assert "Left for a later run, because of the limit: 1." in maker_lines(run)


def test_five_errors_of_the_node_in_a_row_stop_the_step() -> None:
    things = [ThingToAsk(f"0.0.{6100 + n}", "testnet", "topic", f"0.0.{6100 + n}", MADE, None)
              for n in range(MAX_ERRORS_IN_A_ROW + 2)]  # fmt: skip
    store, run = StandInStore(*things), Run(id=1, step=STEP)
    with pytest.raises(NodeIsAway):
        read_makers(store, {"testnet": Node(away=True)}, run, now=lambda: NOW)
    assert store.saved == {} and run.counts["errors_of_the_node"] == MAX_ERRORS_IN_A_ROW
