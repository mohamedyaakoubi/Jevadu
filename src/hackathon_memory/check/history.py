"""The history of a Hedera ID on the ledger, for the ledger story (check/story.py).

An event is one moment of consensus, with the Hedera service that it belongs to. The mirror node
gives the history by the kind of the ID: the transactions of an account, the messages of a topic,
the calls of a contract, the moment a token was made and the moment of each NFT minted, the moments
a schedule was made and ran, and the moment of a transaction. One ID gives at most MAX_EVENTS
events, and a history that the limit cut says so.

This module only reads. It judges nothing: the card (check/story.py) and the measures of
evals/ledger_story count the events.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

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


@dataclass(frozen=True)
class History:
    events: dict[str, str]  # the moment of consensus (seconds.nanoseconds) -> the service
    cut: bool  # True when MAX_EVENTS cut the history


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


def read_history(
    mirror: MirrorNode,
    entity_id: str,
    kind: str,
    *,
    max_events: int = MAX_EVENTS,
    made_at: datetime | None = None,
) -> History:
    """The events of one ID of `kind` on the network of `mirror`. `made_at` is the moment the
    ledger says the ID was made: an account's history is asked from then on."""
    events: dict[str, str] = {}
    cut = False
    if kind == ACCOUNT:
        rows, cut = mirror.account_history(entity_id, max_rows=max_events, since=made_at)
        events = {row["consensus_timestamp"]: service_of(row) for row in rows}
    elif kind == TOPIC:
        rows, cut = mirror.topic_history(entity_id, max_rows=max_events)
        events = {row["consensus_timestamp"]: CONSENSUS for row in rows}
    elif kind == CONTRACT:
        rows, cut = mirror.contract_history(entity_id, max_rows=max_events)
        events = {row["timestamp"]: CONTRACTS for row in rows}
    elif kind == TOKEN:
        token = mirror.token(entity_id) or {}
        if token.get("created_timestamp"):
            events[token["created_timestamp"]] = TOKENS
        if token.get("type") == "NON_FUNGIBLE_UNIQUE":
            rows, cut = mirror.nft_history(entity_id, max_rows=max_events)
            events.update({row["created_timestamp"]: TOKENS for row in rows})
    elif kind == SCHEDULE:
        schedule = mirror.schedule(entity_id) or {}
        for key in ("consensus_timestamp", "executed_timestamp"):
            if schedule.get(key):
                events[schedule[key]] = SCHEDULED
    elif kind == TRANSACTION:
        items = (mirror.transaction(entity_id) or {}).get("transactions") or []
        parent = next((item for item in items if not item.get("nonce")), None)
        if parent:
            events[parent["consensus_timestamp"]] = service_of(parent)
    return History({stamp: service for stamp, service in events.items() if stamp}, cut)
