"""The calls of a project's own contracts that reach Hedera's system contracts (design 7.5,
28 October 2026).

A smart contract on Hedera reaches the services of the network through system contracts at fixed
addresses (Hedera's page "System Smart Contracts", and the table of its page on hybrid
tokenization, read on 28 October 2026): the Token Service at 0x167, the exchange rate at 0x168,
random numbers at 0x169, the Account Service at 0x16a and the Schedule Service at 0x16b. The
mirror node lists what one call of a contract did inside the EVM, its actions; an action of the
call_type SYSTEM goes to one of them, named as its recipient (0.0.359 for 0x167). An action of the
call_type PRECOMPILE goes to one of the EVM's own helpers, such as a hash, and is not counted.

For each own contract, the calls in the time of the ledger story are read, the first MOST_CALLS
at most: a contract that is called thousands of times is cut there, and the card says so. A call
that reaches a system contract twice counts once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from hackathon_memory.check.history import HBAR, SCHEDULED, TOKENS
from hackathon_memory.hedera.mirror import MirrorNode

TOKEN_SERVICE, EXCHANGE_RATE, RANDOM_NUMBERS, ACCOUNT_SERVICE, SCHEDULE_SERVICE = (
    "0.0.359", "0.0.360", "0.0.361", "0.0.362", "0.0.363"
)  # fmt: skip
SYSTEM_CONTRACTS = {
    TOKEN_SERVICE: "the Token Service",
    EXCHANGE_RATE: "the exchange rate",
    RANDOM_NUMBERS: "random numbers",
    ACCOUNT_SERVICE: "the Account Service",
    SCHEDULE_SERVICE: "the Schedule Service",
}
# The row of the table of the ledger story that a system contract counts for; the exchange rate
# and random numbers have none.
SERVICE_OF = {TOKEN_SERVICE: TOKENS, ACCOUNT_SERVICE: HBAR, SCHEDULE_SERVICE: SCHEDULED}
MOST_CALLS = 100


@dataclass(frozen=True)
class ContractCalls:
    """What the calls of one contract in one time reached."""

    entity_id: str
    network: str
    starts_at: datetime
    ends_at: datetime
    read: int  # the calls whose actions were read
    cut: bool  # it had more calls in that time than MOST_CALLS
    reached: dict[str, int]  # a system contract -> the calls that reached it


def reached_by(actions: Iterable[Mapping]) -> set[str]:
    """The system contracts that the actions of one call reached."""
    systems = (str(one.get("recipient")) for one in actions if one.get("call_type") == "SYSTEM")
    return {system for system in systems if system in SYSTEM_CONTRACTS}


def read_calls(
    mirror: MirrorNode, contract: str, network: str, since: datetime, until: datetime, *,
    entity_id: str | None = None,
) -> ContractCalls:  # fmt: skip
    """The calls of `contract` from `since` to `until`, the first MOST_CALLS, and what their
    actions reached. `entity_id` is the ID as the project names it, when it is an EVM address."""
    results = mirror.contract_results(contract, newest_first=False, since=since, until=until,
                                      limit=MOST_CALLS)  # fmt: skip
    counts: Counter[str] = Counter()
    read = 0
    for result in results:
        hashed = result.get("hash")
        if not isinstance(hashed, str) or not hashed:
            continue
        read += 1
        counts.update(reached_by(mirror.contract_actions(hashed)))
    return ContractCalls(entity_id or contract, network, since, until, read,
                         len(results) >= MOST_CALLS, dict(counts))  # fmt: skip


def by_service(calls: Iterable[ContractCalls]) -> dict[str, int]:
    """The calls that reached each service of the table, over the contracts of one project."""
    counts: Counter[str] = Counter()
    for one in calls:
        for system, count in one.reached.items():
            if system in SERVICE_OF:
                counts[SERVICE_OF[system]] += count
    return dict(counts)


def others_in_words(calls: Iterable[ContractCalls]) -> tuple[str, ...]:
    """The system contracts that have no row in the table, with their calls: "random numbers in
    2 calls"."""
    counts: Counter[str] = Counter()
    for one in calls:
        counts.update({system: count for system, count in one.reached.items()
                       if system in SYSTEM_CONTRACTS and system not in SERVICE_OF})  # fmt: skip
    return tuple(f"{SYSTEM_CONTRACTS[system]} in {count:,} call{'s' if count != 1 else ''}"
                 for system, count in sorted(counts.items()))  # fmt: skip
