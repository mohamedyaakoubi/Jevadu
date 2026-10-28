"""How a project's own IDs are set up on the ledger, in plain words (design 7.5, 28 October 2026).

The check of the IDs (check/ledger.py) keeps, from the mirror node's answer about each token, topic
and account, which keys are set, a token's custom fees and supply, and an account's kind of key.
This module makes the sentences of the card from those facts, with no AI: one for each own token,
one for the topics together and one for the accounts together. The facts are those of the day of
the check, since keys and fees can change, and the card says that day.

A fact that a reading from before 28 October 2026 did not keep is not guessed: such an ID gives
no sentence until the check reads it again.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from hackathon_memory.parse.hedera_ids import ACCOUNT, TOKEN, TOPIC

KEY_WORDS = {"admin": "admin", "supply": "supply", "freeze": "freeze", "kyc": "KYC",
             "wipe": "wipe", "pause": "pause", "fee_schedule": "fee schedule",
             "metadata": "metadata"}  # fmt: skip
KEY_TYPE_WORDS = {
    "ED25519": "an ED25519 key",
    "ECDSA_SECP256K1": "an ECDSA key, the kind that EVM wallets use",
    "ProtobufEncoded": "a key made of several keys or held by a contract",
}
NFT = "NON_FUNGIBLE_UNIQUE"


@dataclass(frozen=True)
class Setup:
    """What the check kept about one own ID on its network."""

    entity_id: str
    network: str
    kind: str | None
    details: dict
    read_at: datetime | None  # the day of the check


def joined(words: Sequence[str]) -> str:
    """The words joined the way a sentence lists them: "a", "a and b", "a, b and c"."""
    return " and ".join([", ".join(words[:-1]), words[-1]]) if len(words) > 1 else "".join(words)


def percent(share: Sequence[int]) -> str:
    """A share as [numerator, denominator], in percent: "10%", "2.5%"."""
    numerator, denominator = share
    value = round(100 * numerator / denominator, 2)
    return f"{value:g}%"


def counted(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def token_words(token: Setup) -> str:
    """One sentence about an own token: its kind and supply, its custom fees, its keys."""
    details = token.details
    kind = "an NFT collection" if details.get("type") == NFT else "a fungible token"
    supply = "a supply limit" if details.get("supply_type") == "FINITE" else "no supply limit"
    parts = []
    fees = details.get("fees") or {}
    parts += [f"a royalty of {percent(share)} on each sale" for share in fees.get("royalty", [])]
    parts += [f"a fee of {percent(share)} on each transfer" for share in fees.get("fractional", [])]
    fixed = fees.get("fixed", 0)
    if fixed:
        parts.append("a fixed fee on each transfer" if fixed == 1
                     else f"{fixed} fixed fees on each transfer")  # fmt: skip
    keys = details["keys"]
    parts.append(f"keys for {joined([KEY_WORDS.get(key, key) for key in keys])}" if keys
                 else "no key, so nobody can change it")  # fmt: skip
    return f"Its token {token.entity_id}: {kind} with {supply}; {'; '.join(parts)}."


def topics_words(topics: Sequence[Setup]) -> str:
    """One sentence about the own topics: who may write to them, and what can change them."""
    closed = [one for one in topics if "submit" in one.details["keys"]]
    managed = sum("admin" in one.details["keys"] for one in topics)
    paid = sum(bool(one.details.get("fees")) for one in topics)
    if len(topics) == 1:
        parts = ["only the holder of its submit key can write to it" if closed
                 else "anyone can write to it"]  # fmt: skip
        if managed:
            parts.append("its admin key can change or delete it")
        if paid:
            parts.append("each message pays a fee")
        return f"Its topic {topics[0].entity_id}: {'; '.join(parts)}."
    parts = []
    if closed:
        parts.append(f"{counted(len(closed), 'takes', 'take')} messages only from the holder of "
                     "a submit key")  # fmt: skip
    if len(topics) - len(closed):
        parts.append(f"{counted(len(topics) - len(closed), 'takes', 'take')} messages from anyone")
    if managed:
        parts.append(f"{counted(managed, 'has', 'have')} an admin key that can change or delete "
                     f"{'it' if managed == 1 else 'them'}")  # fmt: skip
    if paid:
        parts.append(f"{counted(paid, 'asks', 'ask')} a fee for each message")
    return f"Its {len(topics)} topics: {'; '.join(parts)}."


def accounts_words(accounts: Sequence[Setup]) -> str:
    """One sentence about the own accounts: the kinds of their keys."""
    kinds = Counter(one.details["key_type"] for one in accounts)
    if len(accounts) == 1:
        (kind,) = kinds
        return f"Its account {accounts[0].entity_id}: {KEY_TYPE_WORDS.get(kind, kind)}."
    parts = [f"{count} with {KEY_TYPE_WORDS.get(kind, kind)}" for kind, count in
             sorted(kinds.items(), key=lambda item: (-item[1], item[0]))]  # fmt: skip
    return f"Its {len(accounts)} accounts: {'; '.join(parts)}."


def setup_words(setups: Sequence[Setup]) -> tuple[str, ...]:
    """The sentences of "How they are set up": each own token, then the topics, then the
    accounts; only the IDs whose setup the check kept."""
    tokens = [one for one in setups if one.kind == TOKEN and "keys" in one.details]
    topics = [one for one in setups if one.kind == TOPIC and "keys" in one.details]
    accounts = [one for one in setups if one.kind == ACCOUNT and one.details.get("key_type")]
    words = [token_words(one) for one in sorted(tokens, key=lambda one: one.entity_id)]
    if topics:
        words.append(topics_words(topics))
    if accounts:
        words.append(accounts_words(accounts))
    return tuple(words)


def read_on(setups: Sequence[Setup]) -> datetime | None:
    """The day of the newest check among the IDs that gave a sentence."""
    days = [one.read_at for one in setups if one.read_at is not None and (
        "keys" in one.details or one.details.get("key_type"))]  # fmt: skip
    return max(days) if days else None
