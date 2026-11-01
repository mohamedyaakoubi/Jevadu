"""Signs of a life after the event (evals/afterlife.py): the counts of the code and the test
network, and the same keys on the main network, with stand-in mirror nodes. Everything is
invented."""

from __future__ import annotations

from datetime import UTC, date, datetime

from evals.afterlife import Behind, accounts_behind, code_and_testnet, makers_after, same_keys
from fakes import StandInMirror
from hackathon_memory.hedera.signing import evm_address_of

NOW = datetime(2026, 11, 1, tzinfo=UTC)
ED = "ab" * 32
ECDSA = "0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798"  # private key 1


def row(ends_on: date, last_push: datetime | None, testnet_last: datetime | None = None,
        used: int = 0, url: str = "https://github.com/a/b",
        now_at: str | None = None) -> tuple:  # fmt: skip
    return (1, ends_on, None, url, now_at or url, last_push, testnet_last, used)


def test_a_push_or_a_use_counts_only_long_enough_after_an_event_old_enough() -> None:
    rows = [
        row(date(2025, 1, 10), datetime(2025, 6, 1, tzinfo=UTC)),  # pushed 142 days after
        row(date(2025, 1, 10), datetime(2025, 1, 20, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC),
            used=2),  # pushed 10 days after; its testnet IDs used a year after
        row(date(2026, 10, 20), datetime(2026, 10, 30, tzinfo=UTC)),  # an event too young
        row(date(2025, 1, 10), None, url="https://github.com/a/c",
            now_at="https://github.com/acme-labs/c"),  # moved to another owner, no push known
    ]  # fmt: skip
    found = code_and_testnet(rows, NOW)
    thirty, year = found["30_days"], found["365_days"]
    assert (thirty["events_old_enough"], thirty["repositories_with_a_known_push"]) == (3, 2)
    assert (thirty["code_pushed"], thirty["code_pushed_share"]) == (1, 0.5)
    assert (year["code_pushed"], year["testnet_still_used"], year["testnet_ever_used"]) == (0, 1, 1)
    assert found["repositories_at_a_new_address"] == found["repositories_under_another_owner"] == 1


def test_a_key_on_both_networks_is_counted_and_what_it_built_after_the_event() -> None:
    ends = datetime(2025, 6, 1, tzinfo=UTC)
    behind = accounts_behind([
        (1, "account", "0.0.101", None, date(2025, 5, 31), None),
        (2, "topic", "0.0.300", "0.0.102", date(2025, 5, 31), None),
        (2, "contract", "0.0.301", "0.0.103", date(2025, 5, 31), None),
    ])  # fmt: skip
    assert [one.account for one in behind] == ["0.0.101", "0.0.102", "0.0.103"]
    testnet = StandInMirror("testnet", account={
        "0.0.101": {"key": {"_type": "ED25519", "key": ED}},
        "0.0.102": {"key": {"_type": "ECDSA_SECP256K1", "key": ECDSA}},
        "0.0.103": {"key": {"_type": "ProtobufEncoded", "key": "0a"}},
    })  # fmt: skip
    mainnet = StandInMirror("mainnet", account={evm_address_of(ECDSA): {"account": "0.0.9002"}})
    mainnet.lists[("key", ED)] = ["0.0.9001"]
    mainnet.lists[("transactions", "0.0.9002")] = [
        {"consensus_timestamp": str(ends.timestamp() + 86_400), "name": "CONTRACTCREATEINSTANCE"},
    ]
    found = same_keys(behind, testnet, mainnet)
    assert found == {"accounts_behind_testnet_ids": 3, "projects_behind_them": 2,
                     "with_one_simple_key": 2, "not_read": 0,
                     "key_also_on_the_main_network": 2, "projects_of_those_keys": 2,
                     "built_there_after_the_event": 1,
                     "projects_that_built_there_after_the_event": 1}  # fmt: skip
    assert (
        Behind("0.0.101", frozenset({1}), datetime(2025, 5, 31, 23, 59, 59, 999999, tzinfo=UTC))
        in behind
    )


def test_the_makers_on_the_main_network_are_counted() -> None:
    assert makers_after([("0.0.7001", False), ("0.0.7002", True)]) == {
        "accounts_that_made_own_mainnet_ids": 2, "made_something_after_the_event": 1}  # fmt: skip
