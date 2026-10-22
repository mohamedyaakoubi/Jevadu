"""What the ledger says about an id, against a stand-in for the mirror node.

The shapes of the answers are the real ones (test network, 11 October 2026). Every id is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import StandInMirror
from hackathon_memory.check.ledger import (
    LedgerFacts,
    kinds_to_ask,
    read_facts,
    was_used_inside,
)
from hackathon_memory.hedera.mirror import MirrorError, when
from hackathon_memory.parse.hedera_ids import (
    ACCOUNT,
    CONTRACT,
    SCHEDULE,
    TOKEN,
    TOPIC,
    TRANSACTION,
)

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
    assert kinds_to_ask("0.0.2345671", None) == (TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE)
    assert kinds_to_ask("0.0.2345671", TOPIC) == (TOPIC, TOKEN, CONTRACT, ACCOUNT, SCHEDULE)
    assert kinds_to_ask("0.0.2345671", CONTRACT) == (CONTRACT, TOKEN, TOPIC, ACCOUNT, SCHEDULE)
    assert kinds_to_ask("0.0.2345671", SCHEDULE) == (SCHEDULE, TOKEN, TOPIC, CONTRACT, ACCOUNT)
    assert kinds_to_ask("0.0.2345671", "something else") == (
        TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE)  # fmt: skip


def test_a_transaction_id_is_asked_only_as_a_transaction() -> None:
    assert kinds_to_ask("0.0.2345671-1700000000-123456789", None) == (TRANSACTION,)
    assert kinds_to_ask("0.0.2345671-1700000000-123456789", ACCOUNT) == (TRANSACTION,)


def transaction(result: str = "SUCCESS", **changes: object) -> dict:
    """One item of /transactions/{id}, in the shape of the test network (18 October 2026)."""
    item = {
        "name": "TOKENCREATION",
        "result": result,
        "consensus_timestamp": MADE,
        "valid_start_timestamp": "1785016490.000000001",
        "entity_id": "0.0.4567891",
        "transaction_id": "0.0.2345671-1785016490-1",
        "nonce": 0,
        "scheduled": False,
    }
    item.update(changes)
    return item


def test_a_transaction_is_one_action_at_one_moment() -> None:
    entity = "0.0.2345671-1785016490-1"
    mirror = StandInMirror(transaction={entity: transaction()})
    facts = facts_of(mirror, entity, TRANSACTION)
    assert (facts.found, facts.kind, facts.empty) == (True, TRANSACTION, False)
    assert facts.created_at == facts.first_activity_at == facts.last_activity_at == when(MADE)
    assert facts.details == {
        "name": "TOKENCREATION",
        "result": "SUCCESS",
        "entity_id": "0.0.4567891",
    }
    assert mirror.asked == [("transaction", entity)]  # nothing else is asked


def test_a_failed_transaction_is_empty_and_an_unknown_one_is_not_found() -> None:
    entity = "0.0.2345671-1785016490-1"
    failed = StandInMirror(transaction={entity: transaction("INSUFFICIENT_PAYER_BALANCE")})
    assert facts_of(failed, entity).empty is True
    assert facts_of(StandInMirror(), entity).found is False


def test_a_contract_is_always_asked_before_an_account() -> None:
    # A contract also answers as an account, so "account" must come after "contract".
    assert kinds_to_ask("0.0.2345671", ACCOUNT) == (CONTRACT, ACCOUNT, TOKEN, TOPIC, SCHEDULE)
    for said in (None, TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE):
        order = kinds_to_ask("0.0.2345671", said)
        assert order.index(CONTRACT) < order.index(ACCOUNT)
    assert kinds_to_ask(ADDRESS, TOKEN) == (CONTRACT, ACCOUNT)


# --------------------------------------------------------------------- each kind of thing


def test_a_token() -> None:
    mirror = StandInMirror(
        token={
            "0.0.2345671": {
                "token_id": "0.0.2345671",
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
    assert facts_of(mirror, "0.0.2345671", TOKEN) == LedgerFacts(
        entity_id="0.0.2345671",
        network="testnet",
        asked_at=NOW,
        found=True,
        kind=TOKEN,
        ledger_id="0.0.2345671",
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
    assert mirror.asked == [(TOKEN, "0.0.2345671")]  # one question was enough


def test_a_token_of_which_no_unit_exists_is_empty() -> None:
    token = {"token_id": "0.0.2345671", "total_supply": "0", "created_timestamp": MADE}
    facts = facts_of(StandInMirror(token={"0.0.2345671": token}), "0.0.2345671")
    assert facts.empty is True
    assert facts.last_activity_at == when(MADE)  # never changed: the day it was made


def test_a_topic_with_messages() -> None:
    mirror = StandInMirror(
        topic={"0.0.3456781": {"topic_id": "0.0.3456781", "created_timestamp": MADE, "memo": "x"}}
    )
    mirror.lists[("messages", "0.0.3456781")] = [
        {"sequence_number": 1, "consensus_timestamp": FIRST, "message": "aGVsbG8="},
        {"sequence_number": 49, "consensus_timestamp": LAST, "message": "aGVsbG8="},
    ]
    facts = facts_of(mirror, "0.0.3456781", TOPIC)
    assert (facts.kind, facts.activity_count, facts.empty) == (TOPIC, 49, False)
    assert (facts.first_activity_at, facts.last_activity_at) == (when(FIRST), when(LAST))
    assert facts.created_at == when(MADE)
    assert facts.details == {}  # no memo and no text of a message is kept


def test_a_topic_with_no_message_is_empty_and_its_first_message_is_not_asked() -> None:
    mirror = StandInMirror(topic={"0.0.3456781": {"topic_id": "0.0.3456781", "deleted": True}})
    facts = facts_of(mirror, "0.0.3456781", TOPIC)
    assert (facts.activity_count, facts.empty, facts.deleted) == (0, True, True)
    assert (facts.first_activity_at, facts.last_activity_at, facts.created_at) == (None,) * 3
    assert mirror.asked == [(TOPIC, "0.0.3456781"), ("messages", "0.0.3456781", "newest", {})]


def test_a_contract_is_a_contract_and_not_an_account() -> None:
    contract = {
        "contract_id": "0.0.4567891",
        "created_timestamp": MADE,
        "deleted": False,
        "evm_address": ADDRESS,
        "bytecode": "0x" + "60" * 9000,
    }
    mirror = StandInMirror(
        contract={"0.0.4567891": contract}, account={"0.0.4567891": {"account": "0.0.4567891"}}
    )
    mirror.lists[("calls", "0.0.4567891")] = [{"timestamp": FIRST}, {"timestamp": LAST}]
    facts = facts_of(mirror, "0.0.4567891", ACCOUNT)  # the page calls it an account
    assert facts.kind == CONTRACT
    assert (facts.first_activity_at, facts.last_activity_at) == (when(FIRST), when(LAST))
    assert facts.activity_count is None  # calls are not counted
    assert facts.details == {"evm_address": ADDRESS}  # and no code of the contract
    assert (ACCOUNT, "0.0.4567891") not in mirror.asked


def test_a_contract_found_by_its_address_gets_the_id_of_the_ledger() -> None:
    mirror = StandInMirror(
        contract={ADDRESS: {"contract_id": "0.0.4567891", "created_timestamp": MADE}}
    )
    facts = facts_of(mirror, ADDRESS, CONTRACT)
    assert (facts.entity_id, facts.ledger_id, facts.kind) == (ADDRESS, "0.0.4567891", CONTRACT)
    assert facts.first_activity_at is None and facts.last_activity_at is None  # never called


def test_an_account_with_its_last_transaction() -> None:
    mirror = StandInMirror(
        account={
            "0.0.5678902": {
                "account": "0.0.5678902",
                "created_timestamp": MADE,
                "deleted": False,
                "evm_address": ADDRESS,
                "key": {"_type": "ED25519", "key": "ab" * 32},
                "memo": "an invented memo",
            }
        }
    )
    mirror.lists[("transactions", "0.0.5678902")] = [
        {"consensus_timestamp": FIRST},
        {"consensus_timestamp": LAST},
    ]
    facts = facts_of(mirror, "0.0.5678902", ACCOUNT)
    assert facts.kind == ACCOUNT
    assert (facts.first_activity_at, facts.last_activity_at) == (when(MADE), when(LAST))
    assert facts.details == {"evm_address": ADDRESS}  # no key and no memo
    # The contract was asked first, and the search went back to the day the account was made.
    assert mirror.asked == [
        (CONTRACT, "0.0.5678902"),
        (ACCOUNT, "0.0.5678902"),
        ("transactions", "0.0.5678902", "newest", {"since": when(MADE)}),
    ]


def test_an_account_with_no_transaction_was_last_active_when_it_was_made() -> None:
    mirror = StandInMirror(
        account={"0.0.5678902": {"account": "0.0.5678902", "created_timestamp": MADE}}
    )
    facts = facts_of(mirror, "0.0.5678902")
    assert facts.last_activity_at == when(MADE)


# --------------------------------------------------------------------- the ledger decides


def test_the_ledger_says_what_a_thing_is_and_not_the_page() -> None:
    mirror = StandInMirror(topic={"0.0.3456781": {"topic_id": "0.0.3456781"}})
    facts = facts_of(mirror, "0.0.3456781", TOKEN)  # the page calls it a token
    assert facts.kind == TOPIC
    assert mirror.asked[:2] == [(TOKEN, "0.0.3456781"), (TOPIC, "0.0.3456781")]


def test_an_id_that_is_nothing_on_the_network_is_not_found() -> None:
    mirror = StandInMirror()
    facts = facts_of(mirror, "0.0.9999999")
    assert facts == LedgerFacts("0.0.9999999", "testnet", NOW, found=False)
    assert [kind for kind, _ in mirror.asked] == [TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE]


def schedule(**changes: object) -> dict:
    """The answer of /schedules/{id}, in the shape of the test network (22 October 2026)."""
    return {"schedule_id": "0.0.9743551", "consensus_timestamp": MADE,
            "executed_timestamp": LAST, "creator_account_id": "0.0.9742861",
            "deleted": False, "memo": "an invented memo", **changes}  # fmt: skip


def test_a_scheduled_transaction_was_made_and_then_ran() -> None:
    mirror = StandInMirror(schedule={"0.0.9743551": schedule()})
    facts = facts_of(mirror, "0.0.9743551", SCHEDULE)
    assert (facts.kind, facts.ledger_id, facts.created_at) == (SCHEDULE, "0.0.9743551", when(MADE))
    assert (facts.first_activity_at, facts.last_activity_at) == (when(MADE), when(LAST))
    assert facts.details == {"executed": True} and mirror.asked == [(SCHEDULE, "0.0.9743551")]


def test_a_scheduled_transaction_that_never_ran_was_last_active_when_it_was_made() -> None:
    mirror = StandInMirror(schedule={"0.0.9743551": schedule(executed_timestamp=None)})
    facts = facts_of(mirror, "0.0.9743551")  # no word: the four other kinds are asked first
    assert facts.kind == SCHEDULE and facts.last_activity_at == when(MADE)
    assert facts.details == {"executed": False} and not facts.empty  # it expired: still made
    assert [kind for kind, _ in mirror.asked] == [TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE]


@pytest.mark.parametrize(
    ("ran", "deleted", "empty"),
    [(LAST, False, False), (LAST, True, False), (None, False, False), (None, True, True)],
)
def test_a_scheduled_transaction_is_empty_only_when_deleted_before_it_ran(
    ran: str | None, deleted: bool, empty: bool
) -> None:
    """The mirror node says "deleted" also of a schedule that ran at its time (22 October 2026)."""
    answer = schedule(executed_timestamp=ran, deleted=deleted)
    facts = facts_of(StandInMirror(schedule={"0.0.9743551": answer}), "0.0.9743551", SCHEDULE)
    assert facts.empty is empty


def test_an_error_of_the_node_goes_on_to_the_caller() -> None:
    class Broken(StandInMirror):
        def token(self, entity: str) -> dict | None:
            raise MirrorError("mirror node answered 503 for /tokens")

    with pytest.raises(MirrorError, match="503"):
        facts_of(Broken(), "0.0.2345671")


# --------------------------------------------------------------------- one more question

BEFORE_ALL = datetime(2026, 1, 1, tzinfo=UTC)
AFTER_ALL = datetime(2027, 1, 1, tzinfo=UTC)
EARLY = (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))  # nothing in here


@pytest.mark.parametrize(
    ("kind", "what", "key"),
    [
        (TOPIC, "messages", "consensus_timestamp"),
        (CONTRACT, "calls", "timestamp"),
        (ACCOUNT, "transactions", "consensus_timestamp"),
    ],
)
def test_the_use_inside_a_time_is_asked_from_the_right_list(kind: str, what: str, key: str) -> None:
    mirror = StandInMirror()
    mirror.lists[(what, "0.0.3456781")] = [{key: FIRST}, {key: LAST}]
    facts = LedgerFacts("0.0.3456781", "testnet", NOW, found=True, kind=kind)
    assert was_used_inside(mirror, facts, BEFORE_ALL, AFTER_ALL) is True  # type: ignore[arg-type]
    assert was_used_inside(mirror, facts, *EARLY) is False  # type: ignore[arg-type]
    assert mirror.asked[-1] == (
        what,
        "0.0.3456781",
        "oldest",
        {"since": EARLY[0], "until": EARLY[1]},
    )


def test_the_use_of_a_thing_found_by_its_address_is_asked_with_the_id_of_the_ledger() -> None:
    mirror = StandInMirror()
    mirror.lists[("calls", "0.0.4567891")] = [{"timestamp": FIRST}]
    facts = LedgerFacts(ADDRESS, "testnet", NOW, found=True, kind=CONTRACT, ledger_id="0.0.4567891")
    assert was_used_inside(mirror, facts, BEFORE_ALL, AFTER_ALL) is True  # type: ignore[arg-type]


def test_a_token_has_no_such_question() -> None:
    mirror = StandInMirror()
    facts = LedgerFacts("0.0.2345671", "testnet", NOW, found=True, kind=TOKEN)
    assert was_used_inside(mirror, facts, BEFORE_ALL, AFTER_ALL) is False  # type: ignore[arg-type]
    assert mirror.asked == []  # and the node is not asked
