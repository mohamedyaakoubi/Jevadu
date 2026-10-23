"""The history of a Hedera ID on the ledger (check/history.py), against a stand-in mirror node.
The shapes of the answers are the mirror node's; every value is invented."""

from __future__ import annotations

import pytest

from fakes import StandInMirror
from hackathon_memory.check.history import (
    CONSENSUS,
    CONTRACTS,
    FILES,
    HBAR,
    SCHEDULED,
    TOKENS,
    History,
    read_history,
    service_of,
)
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, SCHEDULE, TOKEN, TOPIC, TRANSACTION

ONE, TWO, THREE = "1780000000.000000001", "1780000060.000000002", "1780000120.000000003"


@pytest.mark.parametrize(
    ("transaction", "service"),
    [
        ({"name": "CONSENSUSSUBMITMESSAGE"}, CONSENSUS),
        ({"name": "CONSENSUSCREATETOPIC"}, CONSENSUS),
        ({"name": "TOKENMINT"}, TOKENS),
        ({"name": "CRYPTOTRANSFER", "token_transfers": [{"token_id": "0.0.7001"}]}, TOKENS),
        ({"name": "CRYPTOTRANSFER", "nft_transfers": [{"token_id": "0.0.7001"}]}, TOKENS),
        ({"name": "CONTRACTCALL"}, CONTRACTS),
        ({"name": "ETHEREUMTRANSACTION"}, CONTRACTS),
        ({"name": "SCHEDULECREATE"}, SCHEDULED),
        ({"name": "FILEAPPEND"}, FILES),
        ({"name": "CRYPTOTRANSFER", "token_transfers": []}, HBAR),
        ({"name": "CRYPTOCREATEACCOUNT"}, HBAR),
        ({}, HBAR),
    ],
)
def test_each_type_of_transaction_has_its_service(transaction: dict, service: str) -> None:
    assert service_of(transaction) == service


def test_an_account_gives_each_transaction_with_its_service() -> None:
    mirror = StandInMirror()
    mirror.lists[("transactions", "0.0.5001")] = [
        {"consensus_timestamp": ONE, "name": "CONSENSUSSUBMITMESSAGE"},
        {"consensus_timestamp": TWO, "name": "TOKENMINT"},
    ]
    assert read_history(mirror, "0.0.5001", ACCOUNT) == History(
        {ONE: CONSENSUS, TWO: TOKENS}, False
    )


def test_a_topic_and_a_contract_give_their_messages_and_their_calls() -> None:
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.5002")] = [{"consensus_timestamp": ONE}]
    mirror.lists[("calls", "0.0.5003")] = [{"timestamp": TWO}, {"timestamp": THREE}]
    assert read_history(mirror, "0.0.5002", TOPIC).events == {ONE: CONSENSUS}
    assert read_history(mirror, "0.0.5003", CONTRACT).events == {TWO: CONTRACTS, THREE: CONTRACTS}


def test_a_token_gives_the_moment_it_was_made_and_each_nft_minted() -> None:
    nft = {"created_timestamp": ONE, "type": "NON_FUNGIBLE_UNIQUE"}
    coin = {"created_timestamp": ONE, "type": "FUNGIBLE_COMMON"}
    mirror = StandInMirror(token={"0.0.5004": nft, "0.0.5005": coin})
    mirror.lists[("nfts", "0.0.5004")] = [{"created_timestamp": TWO}, {"created_timestamp": THREE}]
    assert read_history(mirror, "0.0.5004", TOKEN).events == {
        ONE: TOKENS,
        TWO: TOKENS,
        THREE: TOKENS,
    }
    assert read_history(mirror, "0.0.5005", TOKEN).events == {ONE: TOKENS}  # no NFT is asked
    assert ("nfts", "0.0.5005", "history") not in mirror.asked


def test_a_schedule_gives_the_moment_it_was_made_and_the_moment_it_ran() -> None:
    ran = {"consensus_timestamp": ONE, "executed_timestamp": TWO}
    waiting = {"consensus_timestamp": ONE, "executed_timestamp": None}
    mirror = StandInMirror(schedule={"0.0.5006": ran, "0.0.5007": waiting})
    assert read_history(mirror, "0.0.5006", SCHEDULE).events == {ONE: SCHEDULED, TWO: SCHEDULED}
    assert read_history(mirror, "0.0.5007", SCHEDULE).events == {ONE: SCHEDULED}


def test_a_transaction_gives_its_own_moment_and_its_service() -> None:
    entity = "0.0.5008-1780000000-000000001"
    mirror = StandInMirror(transaction={entity: {"consensus_timestamp": ONE, "name": "TOKENMINT"}})
    assert read_history(mirror, entity, TRANSACTION).events == {ONE: TOKENS}


def test_a_history_that_the_limit_cut_says_so() -> None:
    mirror = StandInMirror()
    mirror.lists[("messages", "0.0.5002")] = [{"consensus_timestamp": s} for s in (ONE, TWO, THREE)]
    history = read_history(mirror, "0.0.5002", TOPIC, max_events=2)
    assert history == History({ONE: CONSENSUS, TWO: CONSENSUS}, cut=True)


def test_a_thing_that_the_node_does_not_know_gives_no_event() -> None:
    mirror = StandInMirror()
    for kind in (TOKEN, SCHEDULE):
        assert read_history(mirror, "0.0.5009", kind) == History({}, False)
    assert read_history(mirror, "0.0.5009-1780000000-000000001", TRANSACTION) == History({}, False)


def test_an_account_is_read_from_the_moment_it_was_made() -> None:
    from datetime import UTC, datetime

    made = datetime(2025, 11, 6, 17, 58, tzinfo=UTC)
    mirror = StandInMirror()
    read_history(mirror, "0.0.5001", ACCOUNT, made_at=made)
    assert mirror.since == {"0.0.5001": made}
