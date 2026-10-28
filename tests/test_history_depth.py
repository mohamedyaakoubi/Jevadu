"""What each transaction of an own ID was (check/history.py, design 7.5, depth of use), kept
with its history (db/history.py), and a history read on from its newest event (design 7.3).
Against a stand-in mirror node and a real PostgreSQL. Every value is invented."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from fakes import PROJECT_PAGE, StandInMirror, project_page
from hackathon_memory.check.history import (
    CONSENSUS,
    MINTED,
    RAN,
    Act,
    History,
    account_of_address,
    act_of,
    payer_of,
    read_history,
)
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, SCHEDULE, TOKEN, TOPIC
from hackathon_memory.pipeline.history import STEP, read_histories, read_histories_on

ONE, TWO, THREE = "1780000000.000000001", "1780000060.000000002", "1790000000.000000003"
MADE = datetime(2026, 5, 1, tzinfo=UTC)
ASKED = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------- what each was


def test_a_transaction_names_its_kind_its_payer_and_the_accounts_that_took_part() -> None:
    transfer = {
        "name": "CRYPTOTRANSFER", "result": "SUCCESS", "node": "0.0.5",
        "transaction_id": "0.0.8504405-1789139309-785362819",
        "transfers": [{"account": "0.0.802", "amount": 5}, {"account": "0.0.5", "amount": 1},
                      {"account": "0.0.8504405", "amount": -6}],
        "token_transfers": [{"token_id": "0.0.429274", "account": "0.0.8504300", "amount": 4}],
        "nft_transfers": [{"sender_account_id": "0.0.7001", "receiver_account_id": "0.0.7002"}],
    }  # fmt: skip
    parties = ("0.0.7001", "0.0.7002", "0.0.8504300", "0.0.8504405")  # no node, no fee account
    assert act_of(transfer) == Act("CRYPTOTRANSFER", True, "0.0.8504405", parties)
    failed = {"name": "CRYPTODELETEALLOWANCE", "result": "SENDER_DOES_NOT_OWN_NFT_SERIAL_NO"}
    assert act_of(failed).ok is False and act_of({}).ok is None
    assert payer_of("0.0.12-1700000000-1") == "0.0.12" and payer_of(None) is None


def test_the_caller_of_a_contract_is_its_account_when_its_address_is_made_from_one() -> None:
    assert account_of_address("0x00000000000000000000000000000000006c0170") == "0.0.7078256"
    assert account_of_address("0xAbC0000000000000000000000000000000000001") == (
        "0xabc0000000000000000000000000000000000001"
    )
    assert account_of_address(None) is None


def test_each_kind_of_id_says_what_its_transactions_were() -> None:
    mirror = StandInMirror(
        token={"0.0.6001": {"created_timestamp": ONE, "type": "NON_FUNGIBLE_UNIQUE",
                            "treasury_account_id": "0.0.7001"}},
        schedule={"0.0.6002": {"consensus_timestamp": ONE, "executed_timestamp": TWO,
                               "payer_account_id": "0.0.7001", "creator_account_id": "0.0.7002"}},
    )  # fmt: skip
    mirror.lists[("messages", "0.0.6003")] = [{"consensus_timestamp": ONE,
                                               "payer_account_id": "0.0.7003"}]  # fmt: skip
    mirror.lists[("calls", "0.0.6004")] = [
        {"timestamp": ONE, "from": "0x0000000000000000000000000000000000001b59",
         "created_contract_ids": ["0.0.6004"]},
        {"timestamp": TWO, "from": "0x0000000000000000000000000000000000001b5a",
         "error_message": "0x08c379a0"},
    ]  # fmt: skip
    mirror.lists[("nfts", "0.0.6001")] = [{"created_timestamp": TWO, "account_id": "0.0.7004"}]
    mirror.lists[("holders", "0.0.6001")] = ["0.0.7001", "0.0.7004"]
    token = read_history(mirror, "0.0.6001", TOKEN)
    assert token.acts == {ONE: Act("TOKENCREATION", True, None, ("0.0.7001",)),
                          TWO: Act(MINTED, True, None, ("0.0.7004",))}  # fmt: skip
    assert (token.holders, token.holders_cut) == (("0.0.7001", "0.0.7004"), False)
    schedule = read_history(mirror, "0.0.6002", SCHEDULE).acts
    assert [schedule[ONE].name, schedule[TWO].name] == ["SCHEDULECREATE", RAN]
    assert schedule[ONE].parties == ("0.0.7001", "0.0.7002")
    topic = read_history(mirror, "0.0.6003", TOPIC)
    assert topic.acts[ONE] == Act("CONSENSUSSUBMITMESSAGE", True, "0.0.7003", ("0.0.7003",))
    calls = read_history(mirror, "0.0.6004", CONTRACT).acts
    assert calls[ONE] == Act("CONTRACTCREATEINSTANCE", True, "0.0.7001", ("0.0.7001",))
    assert calls[TWO] == Act("CONTRACTCALL", False, "0.0.7002", ("0.0.7002",))


def test_a_history_read_on_asks_from_a_moment() -> None:
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.6003")] = [{"consensus_timestamp": ONE},
                                               {"consensus_timestamp": THREE}]  # fmt: skip
    later = datetime.fromtimestamp(float(TWO), UTC)
    assert read_history(mirror, "0.0.6003", TOPIC, since=later).events == {THREE: CONSENSUS}
    mirror.lists[("transactions", "0.0.7001")] = []
    read_history(mirror, "0.0.7001", ACCOUNT, made_at=MADE, since=later)
    assert mirror.since["0.0.7001"] == later  # the later of the two moments


# ---------------------------------------------------------------------------- kept and read on


@pytest.fixture
def database(empty_database: str) -> str:
    """A project that names one topic of its own, judged a proof."""
    migrate(empty_database)
    html = project_page(description="<p>The log is the topic 0.0.3456781.</p>")
    ProjectStore(empty_database).save(read_project_page(html, PROJECT_PAGE), "a" * 64)
    ledger = LedgerStore(empty_database)
    ledger.save_facts(LedgerFacts("0.0.3456781", "testnet", ASKED, found=True, kind=TOPIC,
                                  ledger_id="0.0.3456781", created_at=MADE))  # fmt: skip
    for item in ledger.ids_to_check():
        ledger.save_checks(item.project_id, {item.hedera_id: {"testnet": PROOF_FOUND}},
                           PROOF_FOUND)  # fmt: skip
    return empty_database


def a_topic(*stamps: str) -> History:
    return History({stamp: CONSENSUS for stamp in stamps}, False,
                   {stamp: Act("CONSENSUSSUBMITMESSAGE", True, "0.0.7003", ("0.0.7003",))
                    for stamp in stamps})  # fmt: skip


def test_what_each_transaction_was_is_kept_and_read_back(database: str) -> None:
    store = HistoryStore(database)
    store.save("0.0.3456781", "testnet", TOPIC, a_topic(ONE, TWO), ASKED)
    kept, asked = store.saved("0.0.3456781", "testnet", since=ASKED - timedelta(days=1))
    assert asked == ASKED and kept.acts[ONE].payer == "0.0.7003"
    assert kept.acts[TWO].parties == ("0.0.7003",)


def test_a_history_of_before_the_depth_of_use_is_read_again_once(database: str) -> None:
    store = HistoryStore(database)
    store.save("0.0.3456781", "testnet", TOPIC, a_topic(ONE), ASKED)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE ledger_histories SET depth = 0")  # as read before 25 October
    assert store.ids_to_read() == []  # it was read
    assert [one.entity_id for one in store.ids_to_read(again=True)] == ["0.0.3456781"]
    assert store.saved("0.0.3456781", "testnet", since=ASKED - timedelta(days=1)) is None
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.3456781")] = [{"consensus_timestamp": ONE,
                                                  "payer_account_id": "0.0.7003"}]  # fmt: skip
    read_histories(store, {"testnet": mirror}, Run(id=1, step=STEP), again=True)
    assert store.ids_to_read(again=True) == []  # read again, with the depth of use


def test_a_history_is_read_on_from_its_newest_event(database: str) -> None:
    store = HistoryStore(database)
    store.save("0.0.3456781", "testnet", TOPIC, a_topic(ONE, TWO), ASKED)
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.3456781")] = [
        {"consensus_timestamp": stamp, "payer_account_id": "0.0.7003"}
        for stamp in (ONE, TWO, THREE)
    ]
    run = Run(id=1, step=STEP)
    soon = lambda: ASKED + timedelta(hours=2)  # noqa: E731
    read_histories_on(store, {"testnet": mirror}, run, older_than=timedelta(hours=24), now=soon)
    assert run.counts["histories_read_on"] == 0  # read two hours ago: young enough
    later = lambda: ASKED + timedelta(days=2)  # noqa: E731
    read_histories_on(store, {"testnet": mirror}, run, older_than=timedelta(hours=24), now=later)
    assert (run.counts["histories_read_on"], run.counts["events_new"]) == (1, 1)
    assert mirror.since["0.0.3456781"] == datetime.fromtimestamp(float(TWO), UTC)
    kept, asked = store.saved("0.0.3456781", "testnet", since=ASKED)
    assert sorted(kept.events) == [ONE, TWO, THREE] and asked == later()
    with psycopg.connect(database) as conn:
        (events,) = conn.execute("SELECT events FROM ledger_histories").fetchone()
    assert events == 3


def test_a_history_cut_by_the_limit_is_not_read_on(database: str) -> None:
    store = HistoryStore(database)
    store.save("0.0.3456781", "testnet", TOPIC, History({ONE: CONSENSUS}, True), ASKED)
    assert store.ids_to_read_on(read_before=ASKED + timedelta(days=3)) == []
