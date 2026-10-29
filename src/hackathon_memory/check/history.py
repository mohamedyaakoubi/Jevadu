"""The history of a Hedera ID on the ledger, for the ledger story (check/story.py).

An event is one moment of consensus, with the Hedera service that it belongs to. The mirror node
gives the history by the kind of the ID: the transactions of an account, the messages of a topic,
the calls of a contract, the moment a token was made and the moment of each NFT minted, the moments
a schedule was made and ran, and the moment of a transaction. One ID gives at most MAX_EVENTS
events, and a history that the limit cut says so.

Since 25 October 2026 each event also says what it was (an Act, for the depth of use of design
7.5): its kind as the mirror node names it, whether it succeeded, the account that paid for it,
and the accounts that took part, without the network's own. A token also gives the accounts that
hold it now. A history can be read on from a moment (`since`), for the step `refresh`.

This module only reads. It judges nothing: the card (check/story.py) and the measures of
evals/ledger_story count the events.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from hackathon_memory.hedera.mirror import MirrorNode
from hackathon_memory.parse.hedera_ids import (
    ACCOUNT,
    CONTRACT,
    SCHEDULE,
    TOKEN,
    TOPIC,
    TRANSACTION,
)

CONSENSUS, TOKENS, CONTRACTS, SCHEDULED, FILES, HBAR = (
    "consensus", "tokens", "contracts", "scheduled", "files", "hbar"
)  # fmt: skip
SERVICES = (CONSENSUS, TOKENS, CONTRACTS, SCHEDULED, FILES, HBAR)
MAX_EVENTS = 2000
MAX_HOLDERS = 500  # the accounts that hold a token, read at most
# The accounts of the network itself, which take part in nearly every transaction: the treasury,
# and the accounts of fees and rewards that Hedera's page "Network accounts" names (read on 25
# October 2026). The node of a transaction is left out too: each transaction names it.
NETWORK_ACCOUNTS = frozenset({"0.0.2", "0.0.98", "0.0.800", "0.0.801", "0.0.802"})
# The made-up kinds of what the mirror node does not name: a minted NFT, a schedule that ran.
MINTED, RAN = "TOKENMINT", "SCHEDULED"
_LONG_ZERO = re.compile(r"^0x0{24}([0-9a-f]{16})$")  # an EVM address made from an account number
# The moment an account was made is kept to the microsecond and rounded, and its own creation is
# a transaction of its history at that moment to the nanosecond: an account is read from a little
# before (found by the second counting of evals/depth.py, 25 October 2026).
BEFORE_ITS_MAKING = timedelta(milliseconds=1)


@dataclass(frozen=True)
class Act:
    """What one transaction of an ID was (design 7.5, depth of use)."""

    name: str | None  # its kind as the mirror node names it, such as CRYPTOTRANSFER
    ok: bool | None  # it succeeded; None when the mirror node does not say
    payer: str | None  # the account that paid, or the EVM address of a contract's caller
    parties: tuple[str, ...] = ()  # the accounts that took part, without the network's own


@dataclass(frozen=True)
class History:
    events: dict[str, str]  # the moment of consensus (seconds.nanoseconds) -> the service
    cut: bool  # True when MAX_EVENTS cut the history
    # What each moment was, and the holders of a token; not compared, so that a history read
    # before them equals one read now.
    acts: dict[str, Act] = field(default_factory=dict, compare=False)
    holders: tuple[str, ...] | None = field(default=None, compare=False)  # a token only
    holders_cut: bool = field(default=False, compare=False)  # more than MAX_HOLDERS hold it

    @property
    def read_until(self) -> datetime | None:
        """The moment of its last event read when MAX_EVENTS cut it: nothing after it was read
        (29 October 2026). None for a whole history."""
        if not self.cut or not self.events:
            return None
        return datetime.fromtimestamp(max(float(stamp) for stamp in self.events), tz=UTC)


def service_of(transaction: Mapping) -> str:
    """The Hedera service of a transaction, from its type ("name" in the mirror node's answer)."""
    name = str(transaction.get("name") or "")
    if name.startswith("CONSENSUS"):
        return CONSENSUS
    if (
        name.startswith("TOKEN")
        or transaction.get("token_transfers")
        or transaction.get("nft_transfers")
    ):
        return TOKENS
    if name.startswith("CONTRACT") or name == "ETHEREUMTRANSACTION":
        return CONTRACTS
    if name.startswith("SCHEDULE"):
        return SCHEDULED
    if name.startswith("FILE"):
        return FILES
    return HBAR


def payer_of(transaction_id: object) -> str | None:
    """The account that paid for a transaction: the first part of its ID, "0.0.5-1700-1"."""
    first = str(transaction_id or "").split("-", 1)[0]
    return first if first.count(".") == 2 else None


def account_of_address(address: object) -> str | None:
    """The caller of a contract: the account behind an EVM address made from an account number
    ("long-zero"), else the address itself."""
    text = str(address or "").lower()
    if not text:
        return None
    long_zero = _LONG_ZERO.match(text)
    return f"0.0.{int(long_zero.group(1), 16)}" if long_zero else text


def parties_of(transaction: Mapping) -> tuple[str, ...]:
    """The accounts of a transaction's transfers of HBAR, tokens and NFTs, without the network's
    own and without the node that took it."""
    found: set[str] = set()
    for key in ("transfers", "token_transfers"):
        found.update(
            str(one.get("account")) for one in transaction.get(key) or [] if one.get("account")
        )
    for one in transaction.get("nft_transfers") or []:
        found.update(str(one.get(side)) for side in ("sender_account_id", "receiver_account_id")
                     if one.get(side))  # fmt: skip
    found -= NETWORK_ACCOUNTS | {str(transaction.get("node") or "")}
    return tuple(sorted(found))


def act_of(transaction: Mapping) -> Act:
    """What a transaction of the mirror node's list was."""
    result = transaction.get("result")
    return Act(transaction.get("name") or None, None if result is None else result == "SUCCESS",
               payer_of(transaction.get("transaction_id")), parties_of(transaction))  # fmt: skip


def _one(*accounts: object) -> tuple[str, ...]:
    return tuple(sorted({str(one) for one in accounts if one} - NETWORK_ACCOUNTS))


def read_history(
    mirror: MirrorNode,
    entity_id: str,
    kind: str,
    *,
    max_events: int = MAX_EVENTS,
    made_at: datetime | None = None,
    since: datetime | None = None,
) -> History:
    """The events of one ID of `kind` on the network of `mirror`, each with what it was. `made_at`
    is the moment the ledger says the ID was made: an account's history is asked from then on.
    With `since`, the transactions of an account, a topic or a contract from that moment on only
    (a token, a schedule and a transaction are read whole: they are small)."""
    acts: dict[str, Act] = {}
    events: dict[str, str] = {}
    cut = False
    holders: tuple[str, ...] | None = None
    holders_cut = False
    if kind == ACCOUNT:
        made = made_at - BEFORE_ITS_MAKING if made_at is not None else None
        start = max((one for one in (made, since) if one is not None), default=None)
        rows, cut = mirror.account_history(entity_id, max_rows=max_events, since=start)
        for row in rows:
            events[row["consensus_timestamp"]] = service_of(row)
            acts[row["consensus_timestamp"]] = act_of(row)
    elif kind == TOPIC:
        rows, cut = mirror.topic_history(entity_id, max_rows=max_events, since=since)
        for row in rows:
            payer = row.get("payer_account_id")
            events[row["consensus_timestamp"]] = CONSENSUS
            acts[row["consensus_timestamp"]] = Act("CONSENSUSSUBMITMESSAGE", True, payer,
                                                   _one(payer))  # fmt: skip
    elif kind == CONTRACT:
        rows, cut = mirror.contract_history(entity_id, max_rows=max_events, since=since)
        for row in rows:
            caller = account_of_address(row.get("from"))
            made = entity_id in (row.get("created_contract_ids") or [])
            events[row["timestamp"]] = CONTRACTS
            name = "CONTRACTCREATEINSTANCE" if made else "CONTRACTCALL"
            acts[row["timestamp"]] = Act(name, not row.get("error_message"), caller, _one(caller))
    elif kind == TOKEN:
        token = mirror.token(entity_id) or {}
        if token.get("created_timestamp"):
            events[token["created_timestamp"]] = TOKENS
            treasury = _one(token.get("treasury_account_id"))
            acts[token["created_timestamp"]] = Act("TOKENCREATION", True, None, treasury)
        if token.get("type") == "NON_FUNGIBLE_UNIQUE":
            rows, cut = mirror.nft_history(entity_id, max_rows=max_events)
            for row in rows:
                events[row["created_timestamp"]] = TOKENS
                acts[row["created_timestamp"]] = Act(
                    MINTED, True, None, _one(row.get("account_id"))
                )
        if token:
            found, holders_cut = mirror.token_holders(entity_id, max_rows=MAX_HOLDERS)
            holders = tuple(found)
    elif kind == SCHEDULE:
        schedule = mirror.schedule(entity_id) or {}
        payer = schedule.get("payer_account_id")
        if schedule.get("consensus_timestamp"):
            events[schedule["consensus_timestamp"]] = SCHEDULED
            acts[schedule["consensus_timestamp"]] = Act(
                "SCHEDULECREATE", True, payer, _one(payer, schedule.get("creator_account_id"))
            )
        if schedule.get("executed_timestamp"):
            events[schedule["executed_timestamp"]] = SCHEDULED
            acts[schedule["executed_timestamp"]] = Act(RAN, True, payer, _one(payer))
    elif kind == TRANSACTION:
        items = (mirror.transaction(entity_id) or {}).get("transactions") or []
        parent = next((item for item in items if not item.get("nonce")), None)
        if parent:
            events[parent["consensus_timestamp"]] = service_of(parent)
            acts[parent["consensus_timestamp"]] = act_of(parent)
    return History({stamp: service for stamp, service in events.items() if stamp}, cut,
                   {stamp: act for stamp, act in acts.items() if stamp}, holders,
                   holders_cut)  # fmt: skip
