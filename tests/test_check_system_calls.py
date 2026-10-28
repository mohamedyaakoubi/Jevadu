"""The calls of the own contracts that reach Hedera's system contracts (check/system_calls.py,
design 7.5). Everything is invented."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.check.history import HBAR, TOKENS
from hackathon_memory.check.system_calls import (
    MOST_CALLS,
    ContractCalls,
    by_service,
    others_in_words,
    reached_by,
    read_calls,
)

SINCE, UNTIL = datetime(2026, 2, 4, tzinfo=UTC), datetime(2026, 5, 6, tzinfo=UTC)


class Calls:
    """Stands in for the mirror node: the calls of one contract, and the actions of each."""

    def __init__(self, actions: dict[str, list[dict]], more: int = 0) -> None:
        self.actions = actions
        self.more = more  # calls without a hash, as the node never gives, to fill a page
        self.asked: list[tuple] = []

    def contract_results(self, contract: str, *, newest_first: bool, since: datetime,
                         until: datetime, limit: int) -> list[dict]:  # fmt: skip
        self.asked.append(("results", contract, newest_first, since, until, limit))
        return [{"hash": hashed} for hashed in self.actions] + [{}] * self.more

    def contract_actions(self, hashed: str) -> list[dict]:
        self.asked.append(("actions", hashed))
        return self.actions[hashed]


def system(recipient: str) -> dict:
    return {"call_type": "SYSTEM", "recipient": recipient}


def test_only_a_call_of_the_kind_system_to_a_system_contract_counts() -> None:
    helper = {"call_type": "PRECOMPILE", "recipient": "0.0.1"}  # one of the EVM's own helpers
    other = {"call_type": "CALL", "recipient": "0.0.361"}
    actions = [system("0.0.359"), system("0.0.359"), helper, other, system("0.0.9")]
    assert reached_by(actions) == {"0.0.359"}  # twice in one call counts once


def test_the_calls_of_a_contract_are_read_with_their_actions() -> None:
    mirror = Calls({"0x01": [system("0.0.359")], "0x02": [system("0.0.359"), system("0.0.361")],
                    "0x03": []})  # fmt: skip
    calls = read_calls(mirror, "0.0.6092626", "testnet", SINCE, UNTIL,  # type: ignore[arg-type]
                       entity_id="0x" + "cd" * 20)  # fmt: skip
    assert calls == ContractCalls("0x" + "cd" * 20, "testnet", SINCE, UNTIL, 3, False,
                                  {"0.0.359": 2, "0.0.361": 1})  # fmt: skip
    assert mirror.asked[0] == ("results", "0.0.6092626", False, SINCE, UNTIL, MOST_CALLS)
    full = Calls({"0x01": []}, more=MOST_CALLS - 1)  # a full page: there may be more
    assert read_calls(full, "0.0.6092626", "testnet", SINCE, UNTIL).cut is True  # type: ignore[arg-type]


def test_the_calls_count_for_their_service_or_are_said_in_words() -> None:
    calls = [ContractCalls("0.0.1", "testnet", SINCE, UNTIL, 9, False,
                           {"0.0.359": 4, "0.0.362": 1, "0.0.361": 2}),
             ContractCalls("0.0.2", "testnet", SINCE, UNTIL, 100, True,
                           {"0.0.359": 30, "0.0.360": 1})]  # fmt: skip
    assert by_service(calls) == {TOKENS: 34, HBAR: 1}
    assert others_in_words(calls) == ("the exchange rate in 1 call", "random numbers in 2 calls")
