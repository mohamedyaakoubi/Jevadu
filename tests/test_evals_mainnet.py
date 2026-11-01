"""The counts of the main network (evals/mainnet.py), on three invented projects."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import psycopg
import pytest

from evals import mainnet
from hackathon_memory.check.history import CONSENSUS, History
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.mainnet import Detail, Rate
from hackathon_memory.check.mainnet_what import Thing
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.mainnet import MainnetStore
from searchfakes import three_projects

pytestmark = pytest.mark.integration

ASKED = datetime(2026, 11, 1, tzinfo=UTC)


def test_the_counts_of_the_main_network_hold_numbers_and_ledger_ids_only(
    empty_database: str,
) -> None:
    database = three_projects(empty_database)
    LedgerStore(database).save_facts(LedgerFacts(
        "0.0.4517", "mainnet", ASKED, found=True, kind="topic", ledger_id="0.0.4517",
        created_at=datetime(2026, 3, 7, tzinfo=UTC)))  # fmt: skip
    with psycopg.connect(database) as conn:
        (pebble,) = conn.execute("SELECT id FROM projects WHERE name = 'Pebble Pay'").fetchone()
        conn.execute("DELETE FROM hedera_ids WHERE entity_id = '0.0.4517'")
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.4517', 'mainnet', 'topic', 'page', "
            "'invented', false) RETURNING id", (pebble,)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'mainnet', 'proof_found')", (hedera_id,))  # fmt: skip
    one = f"{int(datetime(2026, 3, 7, 10, tzinfo=UTC).timestamp())}.000000001"
    two = f"{int(datetime(2026, 3, 7, 11, tzinfo=UTC).timestamp())}.000000002"
    HistoryStore(database).save(
        "0.0.4517", "mainnet", "topic", History({one: CONSENSUS, two: CONSENSUS}, False), ASKED
    )
    store = MainnetStore(database)
    for stamp in (one, two):
        store.save(
            Detail(stamp, "CONSENSUSSUBMITMESSAGE", True, 50_000_000, 0, ("0.0.7001",), 0),
            Rate(600_000, 30_000), ASKED,
        )  # fmt: skip
    store.explain(one, "paid", ("eip155:8453",), ASKED)  # the step mainnet_what, invented
    store.explain(two, None, (), ASKED)
    store.save_thing(Thing("0.0.4517", "topic", ASKED, "0.0.7001"), ASKED)
    store.save_thing(Thing("0.0.4600", "token", ASKED, "0.0.7001", held_by_others=0), ASKED)
    store.mark_followed("0.0.7001", "read", ASKED)
    found = mainnet.counts(database, models=("m",), version="v", now=ASKED)
    assert found["test"] == "mainnet" and found["made_on"] == "2026-11-01"
    assert (found["projects"], found["own_id_on_the_main_network"]) == (3, 1)
    used = found["on_the_main_network"]
    # two fees of 0.5 HBAR at 20 cents an HBAR: 20 cents
    assert (used["transactions"], used["days"], used["fee_tinybars"]) == (2, 1, 100_000_000)
    assert (used["fee_dollars"], used["accounts_that_paid"], used["with_detail"]) == (0.2, 1, 2)
    (project,) = found["projects_on_the_main_network"]
    assert project["ids"] == [{"id": "0.0.4517", "kind": "topic"}]
    assert project["event"] == {"site": "ethglobal.com", "slug": "sample-event"}
    assert project["transactions"] == 2 and project["services"] == ["consensus"]
    assert project["what"] == {"paid": 1, "CONSENSUSSUBMITMESSAGE": 1}
    assert project["networks_named"] == {"eip155:8453": 1} and project["messages"] == 2
    assert project["made_by_the_same_accounts"] == {"token": 1}
    assert project["accounts_that_made_its_ids"] == {"read": 1}
    assert found["what_they_did"]["what"] == {"paid": 1, "CONSENSUSSUBMITMESSAGE": 1}
    text = json.dumps(found)
    assert "Pebble" not in text and "invented" not in text  # no text of a page
