"""How the own IDs are set up, in plain words (check/setup.py, design 7.5). Everything is
invented."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.check.setup import Setup, percent, read_on, setup_words
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC

READ = datetime(2026, 10, 28, 20, tzinfo=UTC)


def one(entity: str, kind: str, **details: object) -> Setup:
    return Setup(entity, "testnet", kind, dict(details), READ)


def test_a_token_says_its_kind_its_supply_its_fees_and_its_keys() -> None:
    collection = one("0.0.7001", TOKEN, type="NON_FUNGIBLE_UNIQUE", supply_type="INFINITE",
                     keys=["admin", "supply", "freeze"], fees={"royalty": [[1, 10]]})  # fmt: skip
    coin = one("0.0.7002", TOKEN, type="FUNGIBLE_COMMON", supply_type="FINITE", keys=[],
               fees={"fixed": 2, "fractional": [[1, 40]]})  # fmt: skip
    assert setup_words([coin, collection]) == (
        "Its token 0.0.7001: an NFT collection with no supply limit; a royalty of 10% on each "
        "sale; keys for admin, supply and freeze.",
        "Its token 0.0.7002: a fungible token with a supply limit; a fee of 2.5% on each "
        "transfer; 2 fixed fees on each transfer; no key, so nobody can change it.",
    )


def test_the_topics_and_the_accounts_are_said_together() -> None:
    topics = [
        one("0.0.7101", TOPIC, keys=["admin", "submit"], fees={}),
        one("0.0.7102", TOPIC, keys=[], fees={"fixed": 1}),
        one("0.0.7103", TOPIC, keys=["submit"], fees={}),
    ]
    accounts = [one("0.0.7201", ACCOUNT, key_type="ECDSA_SECP256K1"),
                one("0.0.7202", ACCOUNT, key_type="ED25519"),
                one("0.0.7203", ACCOUNT, key_type="ECDSA_SECP256K1")]  # fmt: skip
    assert setup_words([*topics, *accounts]) == (
        "Its 3 topics: 2 take messages only from the holder of a submit key; 1 takes messages "
        "from anyone; 1 has an admin key that can change or delete it; 1 asks a fee for each "
        "message.",
        "Its 3 accounts: 2 with an ECDSA key, the kind that EVM wallets use; 1 with an ED25519 "
        "key.",
    )
    alone = [one("0.0.7101", TOPIC, keys=["submit"], fees={"fixed": 1}),
             one("0.0.7301", ACCOUNT, key_type="ProtobufEncoded")]  # fmt: skip
    assert setup_words(alone) == (
        "Its topic 0.0.7101: only the holder of its submit key can write to it; each message pays "
        "a fee.",
        "Its account 0.0.7301: a key made of several keys or held by a contract.",
    )


def test_an_id_read_before_its_setup_was_kept_says_nothing() -> None:
    # read before 28 October 2026: no keys, no kind of key; a contract has no sentence
    old = [one("0.0.7001", TOKEN, type="FUNGIBLE_COMMON", total_supply="5"),
           one("0.0.7101", TOPIC), one("0.0.7201", ACCOUNT, evm_address="0xab"),
           one("0.0.7401", CONTRACT, evm_address="0xcd")]  # fmt: skip
    assert setup_words(old) == () and read_on(old) is None
    assert read_on([one("0.0.7101", TOPIC, keys=[], fees={})]) == READ


def test_a_share_is_written_in_percent() -> None:
    assert (percent([1, 10]), percent([1, 40]), percent([1, 3])) == ("10%", "2.5%", "33.33%")
