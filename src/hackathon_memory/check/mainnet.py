"""What a transaction of Hedera's main network cost and moved (design 7.6, 1 November 2026).

The mirror node gives one transaction by its moment of consensus (/transactions?timestamp=, read on
1 November 2026): "charged_tx_fee", what the network charged, in tinybars; "transfers", the change
of HBAR of each account, the fee included; and "staking_reward_transfers", the rewards of staking
that it paid out, which the transfers include. A fee goes to the network's own accounts and to the
node, so what the other accounts received, less their rewards, is the HBAR that changed hands. A
transaction sent through an EVM relay names the relay in its ID, but the fee comes out of the
sender's account: the accounts that paid are those whose HBAR went out.

The rate of HBAR in US cents is the network's own, the one that it prices its fees with
(/network/exchangerate?timestamp=, read on 1 November 2026): "current_rate" holds until its
"expiration_time", the top of the next hour.

This module only reads. It judges nothing: the view of the main network (search/mainnet.py) counts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from hackathon_memory.check.history import NETWORK_ACCOUNTS

TINYBARS = 100_000_000  # in one HBAR
HOUR = 3600  # the seconds that one exchange rate of the network holds


@dataclass(frozen=True)
class Detail:
    """What one transaction cost and moved."""

    stamp: str  # its moment of consensus, seconds.nanoseconds
    name: str | None  # its kind as the mirror node names it, such as CONSENSUSSUBMITMESSAGE
    ok: bool | None  # it succeeded; None when the mirror node does not say
    fee: int  # what the network charged, in tinybars
    moved: int  # the HBAR that changed hands, apart from fees and rewards, in tinybars
    paid_by: tuple[str, ...]  # the accounts whose HBAR went out, without the network's own
    tokens: int  # how many transfers of a token or an NFT it holds


@dataclass(frozen=True)
class Rate:
    """The network's exchange rate: `hbars` HBAR are worth `cents` US cents."""

    cents: int
    hbars: int

    def dollars(self, tinybars: int) -> float:
        return tinybars * self.cents / self.hbars / TINYBARS / 100


def detail_of(transaction: Mapping) -> Detail:
    """What a transaction of the mirror node's answer cost and moved."""
    network = NETWORK_ACCOUNTS | {str(transaction.get("node") or "")}
    rewards: Counter[str] = Counter()
    for one in transaction.get("staking_reward_transfers") or []:
        rewards[str(one.get("account") or "")] += int(one.get("amount") or 0)
    received, paid_by = 0, set()
    for one in transaction.get("transfers") or []:
        account = str(one.get("account") or "")
        if not account or account in network:
            continue
        change = int(one.get("amount") or 0) - rewards[account]
        if change > 0:
            received += change
        elif change < 0:
            paid_by.add(account)
    credits = transaction.get("token_transfers") or ()
    tokens = sum(int(one.get("amount") or 0) > 0 for one in credits)
    tokens += len(transaction.get("nft_transfers") or ())
    result = transaction.get("result")
    return Detail(str(transaction.get("consensus_timestamp") or ""),
                  transaction.get("name") or None, None if result is None else result == "SUCCESS",
                  int(transaction.get("charged_tx_fee") or 0), received, tuple(sorted(paid_by)),
                  tokens)  # fmt: skip


def rate_of(answer: Mapping | None) -> Rate | None:
    """The rate of the mirror node's answer about the exchange rate; None when it has none."""
    current = (answer or {}).get("current_rate") or {}
    cents, hbars = current.get("cent_equivalent"), current.get("hbar_equivalent")
    return Rate(int(cents), int(hbars)) if cents and hbars else None


def hour_of(stamp: str) -> int:
    """The hour of a moment of consensus, counted from 1970: one exchange rate holds for it."""
    return int(stamp.split(".", 1)[0]) // HOUR
