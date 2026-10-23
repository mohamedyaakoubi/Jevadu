"""The rules of the ledger story that the measure and the card share (check/story.py), on
invented words and events."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hackathon_memory.check.history import CONSENSUS, CONTRACTS, HBAR, SCHEDULED, TOKENS
from hackathon_memory.check.story import Event, merged, named_services, on_its_network

DURING = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
LONG_AFTER = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("words", "named"),
    [
        ("It logs every step on the Hedera Consensus Service.", {CONSENSUS}),
        ("Messages go to an hcs topic; see HCS-10.", {CONSENSUS}),
        ("A loyalty point made with the Hedera Token Service (HTS).", {TOKENS}),
        ("Escrow lives in a Solidity smart contract.", {CONTRACTS}),
        ("Payouts are a scheduled transaction.", {SCHEDULED}),
        ("A JWT token and an NFT gallery.", set()),  # "token" and "NFT" alone do not count
        ("The topics of the talk; the HTTPS server.", set()),
    ],
)
def test_only_the_strict_words_name_a_service(words: str, named: set[str]) -> None:
    assert named_services(words) == named


def test_a_moment_that_an_account_and_a_topic_both_show_belongs_to_the_topic() -> None:
    seen = [("1.1", DURING, CONSENSUS, True), ("1.1", DURING, CONSENSUS, False),
            ("2.2", LONG_AFTER, HBAR, True)]  # fmt: skip
    assert merged(seen) == (Event(DURING, CONSENSUS, False), Event(LONG_AFTER, HBAR, True))


def test_an_id_counts_on_the_network_where_its_status_is_the_best() -> None:
    rows = [(1, "0.0.5001", "testnet", "proof_found", "account", False),
            (1, "0.0.5001", "mainnet", "dates_do_not_fit", "account", False),  # someone else's
            (2, "0.0.5002", "mainnet", "found_but_empty", "topic", False)]  # fmt: skip
    assert on_its_network(rows) == [rows[0], rows[2]]
