"""What the ledger says about one id on one network (design 7.1).

Is there such a thing, what kind of thing is it, when was it made, is it deleted, and what
happened on it. The answers come from the mirror node (hedera/mirror.py), and each record keeps
the time of the question.

The mirror node has no question "what is this id". So the kinds are asked one after the other,
the kind that the page names first. A contract also answers as an account, so "contract" is
always asked before "account": a thing is called an account only when it is not a contract.

What "happened on it" means depends on the kind, because the node shows different things:

* a topic: its messages. The first, the last and how many.
* a contract: its calls. The first and the last. They are not counted.
* an account: its transactions. The last one, searched back to the day the account was made.
* a token: only the token itself, when it was made and when it was last changed. Who sent it to
  whom is not looked at. "Empty" means that no unit of it exists.
* a transaction: the one action itself, its kind (a transfer, the creation of a token, a message
  to a topic) and the moment the network agreed on it. "Empty" means that it failed: the network
  wrote it down, but the action did not happen.
* a scheduled transaction: when it was made, and when it ran, if it ran. It is asked after the
  four kinds above, unless the page calls it a schedule (22 October 2026: seven of them, named
  in HashScan links to /schedule/, were "not found" before).

Of an answer only a few named fields are kept. The code of a contract is big and not needed, and
a memo, a key or the text of a message is nothing that the check uses.

How a token, a topic or an account is set up is kept too (design 7.5, 28 October 2026), from the
same answer: which keys are set, never the keys themselves; a token's custom fees, by their kind
and share; its supply; an account's kind of key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from hackathon_memory.hedera.mirror import MirrorNode, when
from hackathon_memory.parse.hedera_ids import (
    ACCOUNT,
    CONTRACT,
    SCHEDULE,
    TOKEN,
    TOPIC,
    TRANSACTION,
)

KINDS = (TOKEN, TOPIC, CONTRACT, ACCOUNT, SCHEDULE)  # the order in which the kinds are asked
# The keys that can still act on a token or a topic, by the names of the mirror node's fields
# without "_key" (read on 28 October 2026).
TOKEN_KEYS = ("admin", "supply", "freeze", "kyc", "wipe", "pause", "fee_schedule", "metadata")
TOPIC_KEYS = ("admin", "submit", "fee_schedule")


def keys_of(entity: dict, names: tuple[str, ...]) -> list[str]:
    """The keys that are set on a token or a topic, by their short names."""
    return [name for name in names if entity.get(f"{name}_key")]


def fees_of(custom: object) -> dict:
    """The custom fees of a token or a topic: how many fixed fees, and the share of each
    fractional fee and royalty as [numerator, denominator]. Nothing when it has none."""
    found: dict = {}
    if not isinstance(custom, dict):
        return found
    if custom.get("fixed_fees"):
        found["fixed"] = len(custom["fixed_fees"])
    for kind in ("fractional", "royalty"):
        amounts = [fee.get("amount") for fee in custom.get(f"{kind}_fees") or []]
        shares = [
            [int(one["numerator"]), int(one["denominator"])]
            for one in amounts
            if isinstance(one, dict) and one.get("denominator")
        ]
        if shares:
            found[kind] = shares
    return found


@dataclass(frozen=True)
class LedgerFacts:
    """What one network says about one id, at the time `asked_at`."""

    entity_id: str  # as it was asked: 0.0.12345, or an EVM address
    network: str
    asked_at: datetime
    found: bool
    kind: str | None = None  # account, token, topic or contract
    ledger_id: str | None = None  # the id that the ledger gives the thing
    created_at: datetime | None = None
    deleted: bool = False
    first_activity_at: datetime | None = None
    last_activity_at: datetime | None = None
    activity_count: int | None = None  # the messages of a topic. Not counted for the others.
    empty: bool | None = None  # a topic with no message, a token of which no unit exists
    details: dict = field(default_factory=dict)  # a few more facts of the kind


def _now() -> datetime:
    return datetime.now(UTC)


def _time(stamp: object) -> datetime | None:
    return when(stamp) if isinstance(stamp, str) and stamp else None


def kinds_to_ask(entity_id: str, said_kind: str | None) -> tuple[str, ...]:
    """The kinds in the order they are asked: the one the page names first, a contract before
    an account. An EVM address can only be a contract or an account, and a transaction ID only
    a transaction."""
    if "-" in entity_id:
        return (TRANSACTION,)
    if entity_id.startswith("0x"):
        return (CONTRACT, ACCOUNT)
    if said_kind == ACCOUNT:
        return (CONTRACT, ACCOUNT, TOKEN, TOPIC, SCHEDULE)
    if said_kind in KINDS:
        return (said_kind, *(kind for kind in KINDS if kind != said_kind))
    return KINDS


def read_facts(
    mirror: MirrorNode,
    entity_id: str,
    said_kind: str | None = None,
    *,
    now: Callable[[], datetime] = _now,
) -> LedgerFacts:
    """Ask the network of `mirror` about one id. A MirrorError goes on to the caller."""
    asked_at = now()
    readers = {TOKEN: _token, TOPIC: _topic, CONTRACT: _contract, ACCOUNT: _account,
               TRANSACTION: _transaction, SCHEDULE: _schedule}  # fmt: skip
    for kind in kinds_to_ask(entity_id, said_kind):
        facts = readers[kind](mirror, entity_id)
        if facts is not None:
            return LedgerFacts(
                entity_id=entity_id,
                network=mirror.network,
                asked_at=asked_at,
                found=True,
                kind=kind,
                **facts,
            )
    return LedgerFacts(entity_id=entity_id, network=mirror.network, asked_at=asked_at, found=False)


def was_used_inside(
    mirror: MirrorNode, facts: LedgerFacts, since: datetime, until: datetime
) -> bool:
    """Ask whether something happened on the thing between two moments.

    This is the one more question of the proof rule, for a thing that was used both before and
    after the window of an event. A token has no such question: who sent it to whom is not
    looked at, so the answer for a token is no.
    """
    entity = facts.ledger_id or facts.entity_id
    if facts.kind == TOPIC:
        found = mirror.topic_messages(entity, newest_first=False, since=since, until=until)
    elif facts.kind == CONTRACT:
        found = mirror.contract_results(entity, newest_first=False, since=since, until=until)
    elif facts.kind == ACCOUNT:
        found = mirror.account_transactions(entity, newest_first=False, since=since, until=until)
    else:
        found = []
    return bool(found)


def _token(mirror: MirrorNode, entity_id: str) -> dict | None:
    token = mirror.token(entity_id)
    if token is None:
        return None
    created = _time(token.get("created_timestamp"))
    return {
        "ledger_id": token.get("token_id"),
        "created_at": created,
        "deleted": token.get("deleted") is True,
        "first_activity_at": created,
        "last_activity_at": _time(token.get("modified_timestamp")) or created,
        "empty": str(token.get("total_supply", "")) == "0",
        "details": {
            **{
                key: token.get(key)
                for key in ("type", "total_supply", "name", "symbol", "supply_type", "max_supply")
                if token.get(key) is not None
            },
            "keys": keys_of(token, TOKEN_KEYS),
            "fees": fees_of(token.get("custom_fees")),
        },
    }


def _topic(mirror: MirrorNode, entity_id: str) -> dict | None:
    topic = mirror.topic(entity_id)
    if topic is None:
        return None
    newest = mirror.topic_messages(entity_id, newest_first=True)
    oldest = mirror.topic_messages(entity_id, newest_first=False) if newest else []
    count = int(newest[0]["sequence_number"]) if newest else 0
    return {
        "ledger_id": topic.get("topic_id"),
        "created_at": _time(topic.get("created_timestamp")),
        "deleted": topic.get("deleted") is True,
        "first_activity_at": _time(oldest[0].get("consensus_timestamp")) if oldest else None,
        "last_activity_at": _time(newest[0].get("consensus_timestamp")) if newest else None,
        "activity_count": count,
        "empty": count == 0,
        "details": {"keys": keys_of(topic, TOPIC_KEYS), "fees": fees_of(topic.get("custom_fees"))},
    }


def _contract(mirror: MirrorNode, entity_id: str) -> dict | None:
    contract = mirror.contract(entity_id)
    if contract is None:
        return None
    newest = mirror.contract_results(entity_id, newest_first=True)
    oldest = mirror.contract_results(entity_id, newest_first=False) if newest else []
    address = contract.get("evm_address")
    return {
        "ledger_id": contract.get("contract_id"),
        "created_at": _time(contract.get("created_timestamp")),
        "deleted": contract.get("deleted") is True,
        "first_activity_at": _time(oldest[0].get("timestamp")) if oldest else None,
        "last_activity_at": _time(newest[0].get("timestamp")) if newest else None,
        "details": {"evm_address": address} if address else {},
    }


def _transaction(mirror: MirrorNode, entity_id: str) -> dict | None:
    items = (mirror.transaction(entity_id) or {}).get("transactions") or []
    parent = next((item for item in items if not item.get("nonce")), items[0] if items else None)
    if not isinstance(parent, dict):
        return None
    moment = _time(parent.get("consensus_timestamp"))
    result = parent.get("result")
    return {
        "ledger_id": parent.get("transaction_id"),
        "created_at": moment,
        "first_activity_at": moment,
        "last_activity_at": moment,
        "empty": result != "SUCCESS",
        "details": {
            key: parent.get(key)
            for key in ("name", "result", "entity_id")
            if parent.get(key) is not None
        },  # fmt: skip
    }


def _schedule(mirror: MirrorNode, entity_id: str) -> dict | None:
    schedule = mirror.schedule(entity_id)
    if schedule is None:
        return None
    made = _time(schedule.get("consensus_timestamp"))
    ran = _time(schedule.get("executed_timestamp"))
    deleted = schedule.get("deleted") is True
    return {
        "ledger_id": schedule.get("schedule_id"),
        "created_at": made,
        "deleted": deleted,
        "first_activity_at": made,
        "last_activity_at": ran or made,
        # Deleted before it ran: empty, like a deleted contract. The mirror node also says
        # "deleted" of a schedule that ran at its time, and one that expired without running was
        # still made and signed (both seen on 22 October 2026): neither is empty.
        "empty": deleted and ran is None,
        "details": {"executed": ran is not None},
    }


def _account(mirror: MirrorNode, entity_id: str) -> dict | None:
    account = mirror.account(entity_id)
    if account is None:
        return None
    created = _time(account.get("created_timestamp"))
    ledger_id = account.get("account")
    newest = (
        mirror.account_transactions(ledger_id, newest_first=True, since=created)
        if isinstance(ledger_id, str)
        else []
    )
    key = account.get("key")
    found = {
        "evm_address": account.get("evm_address"),
        "key_type": key.get("_type") if isinstance(key, dict) else None,  # ED25519, ECDSA_SECP256K1
    }
    return {
        "ledger_id": ledger_id,
        "created_at": created,
        "deleted": account.get("deleted") is True,
        "first_activity_at": created,
        "last_activity_at": (_time(newest[0].get("consensus_timestamp")) if newest else created),
        "details": {name: value for name, value in found.items() if value},
    }
