"""The own IDs on the main network and what their transactions cost, moved and did (db/mainnet.py),
on a real PostgreSQL, with the steps `mainnet` and `mainnet_what`, and the path that the window
reads (search/mainnet_path.py). Everything is invented."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, StandInMirror, project_page
from hackathon_memory.check.history import CONSENSUS, History
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.mainnet_what import Thing
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.mainnet import MainnetStore, mainnet_ids
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import TOPIC
from hackathon_memory.pipeline.mainnet import STEP, read_mainnet
from hackathon_memory.pipeline.mainnet_what import STEP as WHAT
from hackathon_memory.pipeline.mainnet_what import explain_mainnet

pytestmark = pytest.mark.integration

ASKED = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
TOPIC_ID = "0.0.3456781"
ONE, TWO = "1780000000.000000001", "1780000060.000000002"
RATE = {"current_rate": {"cent_equivalent": 300_000, "hbar_equivalent": 30_000}}


@pytest.fixture
def database(empty_database: str) -> str:
    """One project whose page names its topic on the main network, made during its event (from 6
    March 2026), with a history of two messages."""
    migrate(empty_database)
    page = project_page(description=f"<p>The log is our topic {TOPIC_ID} on Hedera mainnet.</p>")
    ProjectStore(empty_database).save(read_project_page(page, PROJECT_PAGE), "a" * 64)
    ledger = LedgerStore(empty_database)
    made = datetime(2026, 3, 7, tzinfo=UTC)
    ledger.save_facts(LedgerFacts(TOPIC_ID, "mainnet", ASKED, found=True, kind=TOPIC,
                                  ledger_id=TOPIC_ID, created_at=made))  # fmt: skip
    for item in ledger.ids_to_check():
        ledger.save_checks(item.project_id, {item.hedera_id: {"mainnet": PROOF_FOUND}}, PROOF_FOUND)
    HistoryStore(empty_database).save(
        TOPIC_ID, "mainnet", TOPIC, History({ONE: CONSENSUS, TWO: CONSENSUS}, False), ASKED
    )
    return empty_database


def message(stamp: str, fee: int) -> dict:
    return {"consensus_timestamp": stamp, "name": "CONSENSUSSUBMITMESSAGE", "result": "SUCCESS",
            "charged_tx_fee": fee,
            "transfers": [{"account": "0.0.802", "amount": fee},
                          {"account": "0.0.7001", "amount": -fee}]}  # fmt: skip


def test_the_moments_of_the_own_ids_on_the_main_network_are_read_once(database: str) -> None:
    with psycopg.connect(database) as conn:
        (project_id,) = conn.execute("SELECT id FROM projects").fetchone()
        assert mainnet_ids(conn, [project_id]) == {project_id: {TOPIC_ID}}
    store = MainnetStore(database)
    assert store.moments_to_read() == [ONE, TWO]
    assert store.moments_to_read(projects={project_id + 1}) == []  # another project
    mirror = StandInMirror("mainnet")
    mirror.at_moment = {ONE: message(ONE, 800_000), TWO: message(TWO, 900_000)}
    mirror.rate = RATE
    run = Run(id=1, step=STEP)
    read_mainnet(store, {"mainnet": mirror}, run, now=lambda: ASKED)
    assert run.counts["mainnet_read"] == 2 and store.moments_to_read() == []
    with psycopg.connect(database) as conn:
        kept = conn.execute(
            "SELECT stamp, at, name, ok, fee, moved, paid_by, tokens, cents, hbars, asked_at "
            "FROM mainnet_transactions ORDER BY stamp"
        ).fetchall()
    assert kept == [
        (ONE, datetime.fromtimestamp(1780000000, UTC), "CONSENSUSSUBMITMESSAGE", True,
         800_000, 0, ["0.0.7001"], 0, 300_000, 30_000, ASKED),
        (TWO, datetime.fromtimestamp(1780000060, UTC), "CONSENSUSSUBMITMESSAGE", True,
         900_000, 0, ["0.0.7001"], 0, 300_000, 30_000, ASKED),
    ]  # fmt: skip


def explained(database: str) -> int:
    """The steps `mainnet` and `mainnet_what` on the topic of the fixture, made by 0.0.7001,
    whose two messages are of the kind "paid" and name Base; 0.0.7001 also made a token. Returns
    the project's ID."""
    with psycopg.connect(database) as conn:
        (project_id,) = conn.execute("SELECT id FROM projects").fetchone()
        conn.execute("UPDATE ledger_facts SET made_by = '0.0.7001', made_by_asked_at = %s "
                     "WHERE entity_id = %s", (ASKED, TOPIC_ID))  # fmt: skip
    store = MainnetStore(database)
    mirror = StandInMirror("mainnet", topic={TOPIC_ID: {"memo": "our log"}},
                           token={"0.0.6100": {"name": "Side", "symbol": "SD",
                                               "treasury_account_id": "0.0.7001"}})  # fmt: skip
    mirror.at_moment = {ONE: message(ONE, 800_000), TWO: message(TWO, 900_000)}
    mirror.rate = RATE
    read_mainnet(store, {"mainnet": mirror}, Run(id=1, step=STEP), now=lambda: ASKED)
    said = base64.b64encode(json.dumps({"kind": "paid", "network": "eip155:8453"}).encode())
    mirror.lists[("messages", TOPIC_ID)] = [
        {"consensus_timestamp": stamp, "sequence_number": number, "message": said.decode()}
        for number, stamp in ((1, ONE), (2, TWO))
    ]  # fmt: skip
    mirror.lists[("transactions", "0.0.7001")] = [
        {"consensus_timestamp": "1780000100.000000001", "name": "TOKENCREATION",
         "result": "SUCCESS", "entity_id": "0.0.6100",
         "transaction_id": "0.0.7001-1780000100-1"},
    ]  # fmt: skip
    run = Run(id=2, step=WHAT)
    explain_mainnet(store, {"mainnet": mirror}, None, run, now=lambda: ASKED)
    assert run.counts["mainnet_explained"] == 2
    return project_id


def test_what_the_transactions_did_is_kept_once(database: str) -> None:
    """The step `mainnet_what` after the step `mainnet` (design 7.6)."""
    explained(database)
    assert [one.todo for one in MainnetStore(database).own_things()] == [()]  # read once
    with psycopg.connect(database) as conn:
        kept = conn.execute("SELECT stamp, what, networks, explained_at FROM "
                            "mainnet_transactions ORDER BY stamp").fetchall()  # fmt: skip
        things = conn.execute(
            "SELECT entity_id, kind, made_by, name, held_by_others, messages, followed "
            "FROM mainnet_things ORDER BY entity_id"
        ).fetchall()
    assert kept == [(ONE, "paid", ["eip155:8453"], ASKED), (TWO, "paid", ["eip155:8453"], ASKED)]
    assert things == [
        (TOPIC_ID, "topic", "0.0.7001", "our log", None, 2, None),
        ("0.0.6100", "token", "0.0.7001", "Side (SD)", 0, None, None),
        ("0.0.7001", "account", None, None, None, None, "read"),
    ]


def test_a_mark_of_following_keeps_who_made_the_thing(database: str) -> None:
    store = MainnetStore(database)
    store.save_thing(Thing("0.0.5004", "account", ASKED, "0.0.7003"), ASKED)
    store.mark_followed("0.0.5004", "read", ASKED)
    store.mark_followed("0.0.7003", "service", ASKED)
    assert store.makers() == {"0.0.5004": "0.0.7003", "0.0.7003": None}
    with psycopg.connect(database) as conn:
        kept = dict(conn.execute("SELECT entity_id, followed FROM mainnet_things").fetchall())
    assert kept == {"0.0.5004": "read", "0.0.7003": "service"}
