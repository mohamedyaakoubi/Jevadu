"""What the ledger says about an id, against a stand-in for the mirror node.

The shapes of the answers are the real ones (test network, 11 October 2026). Every id is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import StandInMirror
from hackathon_memory.check.ledger import LedgerFacts, kinds_to_ask, read_facts
from hackathon_memory.hedera.mirror import MirrorError, when
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC

NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
ADDRESS = "0x00000000000000000000000000000000002345ab"
MADE = "1785016492.973922171"
CHANGED = "1785100000.000000001"
FIRST = "1785016500.000000001"
LAST = "1785200000.000000001"


def facts_of(mirror: StandInMirror, entity: str, said_kind: str | None = None) -> LedgerFacts:
    return read_facts(mirror, entity, said_kind, now=lambda: NOW)  # type: ignore[arg-type]


# --------------------------------------------------------------------- the order of the questions


def test_the_kind_that_the_page_names_is_asked_first() -> None:
    assert kinds_to_ask("0.0.2345678", None) == (TOKEN, TOPIC, CONTRACT, ACCOUNT)
    assert kinds_to_ask("0.0.2345678", TOPIC) == (TOPIC, TOKEN, CONTRACT, ACCOUNT)
    assert kinds_to_ask("0.0.2345678", CONTRACT) == (CONTRACT, TOKEN, TOPIC, ACCOUNT)
    assert kinds_to_ask("0.0.2345678", "something else") == (TOKEN, TOPIC, CONTRACT, ACCOUNT)


def test_a_contract_is_always_asked_before_an_account() -> None:
    # A contract also answers as an account, so "account" must come after "contract".
    assert kinds_to_ask("0.0.2345678", ACCOUNT) == (CONTRACT, ACCOUNT, TOKEN, TOPIC)
    for said in (None, TOKEN, TOPIC, CONTRACT, ACCOUNT):
        order = kinds_to_ask("0.0.2345678", said)
        assert order.index(CONTRACT) < order.index(ACCOUNT)
    assert kinds_to_ask(ADDRESS, TOKEN) == (CONTRACT, ACCOUNT)


# --------------------------------------------------------------------- each kind of thing


def test_a_token() -> None:
    mirror = StandInMirror(
        token={
            "0.0.2345678": {
                "token_id": "0.0.2345678",
                "type": "FUNGIBLE_COMMON",
                "total_supply": "1000000",
                "name": "Pebble",
                "symbol": "PBL",
                "created_timestamp": MADE,
                "modified_timestamp": CHANGED,
                "deleted": False,
                "admin_key": {"_type": "ED25519", "key": "ab" * 32},
                "memo": "an invented memo",
            }
        }
    )
    assert facts_of(mirror, "0.0.2345678", TOKEN) == LedgerFacts(
        entity_id="0.0.2345678",
        network="testnet",
        asked_at=NOW,
        found=True,
        kind=TOKEN,
        ledger_id="0.0.2345678",
        created_at=when(MADE),
        deleted=False,
        first_activity_at=when(MADE),
        last_activity_at=when(CHANGED),
        activity_count=None,
        empty=False,
        details={
            "type": "FUNGIBLE_COMMON",
            "total_supply": "1000000",
            "name": "Pebble",
            "symbol": "PBL",
        },
    )
    assert mirror.asked == [(TOKEN, "0.0.2345678")]  # one question was enough


def test_a_token_of_which_no_unit_exists_is_empty() -> None:
    token = {"token_id": "0.0.2345678", "total_supply": "0", "created_timestamp": MADE}
    facts = facts_of(StandInMirror(token={"0.0.2345678": token}), "0.0.2345678")
    assert facts.empty is True
    assert facts.last_activity_at == when(MADE)  # never changed: the day it was made


def test_a_topic_with_messages() -> None:
    mirror = StandInMirror(
        topic={"0.0.3456789": {"topic_id": "0.0.3456789", "created_timestamp": MADE, "memo": "x"}}
    )
    mirror.lists[("messages", "0.0.3456789")] = [
        {"sequence_number": 1, "consensus_timestamp": FIRST, "message": "aGVsbG8="},
        {"sequence_number": 49, "consensus_timestamp": LAST, "message": "aGVsbG8="},
    ]
    facts = facts_of(mirror, "0.0.3456789", TOPIC)
    assert (facts.kind, facts.activity_count, facts.empty) == (TOPIC, 49, False)
    assert (facts.first_activity_at, facts.last_activity_at) == (when(FIRST), when(LAST))
    assert facts.created_at == when(MADE)
    assert facts.details == {}  # no memo and no text of a message is kept


def test_a_topic_with_no_message_is_empty_and_its_first_message_is_not_asked() -> None:
    mirror = StandInMirror(topic={"0.0.3456789": {"topic_id": "0.0.3456789", "deleted": True}})
    facts = facts_of(mirror, "0.0.3456789", TOPIC)
    assert (facts.activity_count, facts.empty, facts.deleted) == (0, True, True)
    assert (facts.first_activity_at, facts.last_activity_at, facts.created_at) == (None,) * 3
    assert mirror.asked == [(TOPIC, "0.0.3456789"), ("messages", "0.0.3456789", "newest", {})]


def test_a_contract_is_a_contract_and_not_an_account() -> None:
    contract = {
        "contract_id": "0.0.4567890",
        "created_timestamp": MADE,
        "deleted": False,
        "evm_address": ADDRESS,
        "bytecode": "0x" + "60" * 9000,
    }
    mirror = StandInMirror(
        contract={"0.0.4567890": contract}, account={"0.0.4567890": {"account": "0.0.4567890"}}
    )
    mirror.lists[("calls", "0.0.4567890")] = [{"timestamp": FIRST}, {"timestamp": LAST}]
    facts = facts_of(mirror, "0.0.4567890", ACCOUNT)  # the page calls it an account
    assert facts.kind == CONTRACT
    assert (facts.first_activity_at, facts.last_activity_at) == (when(FIRST), when(LAST))
    assert facts.activity_count is None  # calls are not counted
    assert facts.details == {"evm_address": ADDRESS}  # and no code of the contract
    assert (ACCOUNT, "0.0.4567890") not in mirror.asked


def test_a_contract_found_by_its_address_gets_the_id_of_the_ledger() -> None:
    mirror = StandInMirror(
        contract={ADDRESS: {"contract_id": "0.0.4567890", "created_timestamp": MADE}}
    )
    facts = facts_of(mirror, ADDRESS, CONTRACT)
    assert (facts.entity_id, facts.ledger_id, facts.kind) == (ADDRESS, "0.0.4567890", CONTRACT)
    assert facts.first_activity_at is None and facts.last_activity_at is None  # never called


def test_an_account_with_its_last_transaction() -> None:
    mirror = StandInMirror(
        account={
            "0.0.5678901": {
                "account": "0.0.5678901",
                "created_timestamp": MADE,
                "deleted": False,
                "evm_address": ADDRESS,
                "key": {"_type": "ED25519", "key": "ab" * 32},
                "memo": "an invented memo",
            }
        }
    )
    mirror.lists[("transactions", "0.0.5678901")] = [
        {"consensus_timestamp": FIRST},
        {"consensus_timestamp": LAST},
    ]
    facts = facts_of(mirror, "0.0.5678901", ACCOUNT)
    assert facts.kind == ACCOUNT
    assert (facts.first_activity_at, facts.last_activity_at) == (when(MADE), when(LAST))
    assert facts.details == {"evm_address": ADDRESS}  # no key and no memo
    # The contract was asked first, and the search went back to the day the account was made.
    assert mirror.asked == [
        (CONTRACT, "0.0.5678901"),
        (ACCOUNT, "0.0.5678901"),
        ("transactions", "0.0.5678901", "newest", {"since": when(MADE)}),
    ]


def test_an_account_with_no_transaction_was_last_active_when_it_was_made() -> None:
    mirror = StandInMirror(
        account={"0.0.5678901": {"account": "0.0.5678901", "created_timestamp": MADE}}
    )
    facts = facts_of(mirror, "0.0.5678901")
    assert facts.last_activity_at == when(MADE)


# --------------------------------------------------------------------- the ledger decides


def test_the_ledger_says_what_a_thing_is_and_not_the_page() -> None:
    mirror = StandInMirror(topic={"0.0.3456789": {"topic_id": "0.0.3456789"}})
    facts = facts_of(mirror, "0.0.3456789", TOKEN)  # the page calls it a token
    assert facts.kind == TOPIC
    assert mirror.asked[:2] == [(TOKEN, "0.0.3456789"), (TOPIC, "0.0.3456789")]


def test_an_id_that_is_nothing_on_the_network_is_not_found() -> None:
    mirror = StandInMirror()
    facts = facts_of(mirror, "0.0.9999999")
    assert facts == LedgerFacts("0.0.9999999", "testnet", NOW, found=False)
    assert [kind for kind, _ in mirror.asked] == [TOKEN, TOPIC, CONTRACT, ACCOUNT]


def test_an_error_of_the_node_goes_on_to_the_caller() -> None:
    class Broken(StandInMirror):
        def token(self, entity: str) -> dict | None:
            raise MirrorError("mirror node answered 503 for /tokens")

    with pytest.raises(MirrorError, match="503"):
        facts_of(Broken(), "0.0.2345678")
