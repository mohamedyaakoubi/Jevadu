"""The main network in a list of projects (search/mainnet.py): what transactions count to, and the
words of an amount and of a time. Everything is invented."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.check.mainnet import Rate
from hackathon_memory.search.mainnet import (
    Transaction,
    days_between,
    dollar_words,
    hbar_words,
    used_of,
)

AT = datetime(2026, 3, 7, 10, tzinfo=UTC)
RATE = Rate(600_000, 30_000)  # 20 cents an HBAR


def test_a_transaction_counts_once_and_only_a_read_one_has_a_cost() -> None:
    paid = Transaction("1.1", AT, "consensus", True, True, 50_000_000, 0, ("0.0.7001",), RATE)
    moved = Transaction("1.2", AT.replace(day=8), "hbar", False, True, 10_000_000, 200_000_000,
                        ("0.0.7002",), None)  # fmt: skip
    unread = Transaction("1.3", AT.replace(day=9), "consensus", None, False)
    used = used_of([paid, paid, moved, unread])  # the same moment through two IDs
    assert (used.transactions, used.failed, used.days, used.detailed) == (3, 1, 3, 2)
    assert (used.fee, used.moved, used.without_rate) == (60_000_000, 200_000_000, 1)
    assert used.fee_dollars == 0.1  # only the fee with a rate: 0.5 HBAR at 20 cents
    assert used.payers == ("0.0.7001", "0.0.7002")
    assert (used.first, used.last) == (AT, AT.replace(day=9))
    assert used_of([]).transactions == 0 and used_of([]).first is None


def test_a_time_and_an_amount_read_in_few_words() -> None:
    assert days_between(AT, AT.replace(hour=20)) == "7 March 2026"
    assert days_between(AT, AT.replace(day=21)) == "7 to 21 March 2026"
    assert days_between(AT, AT.replace(month=9, day=5)) == "7 March to 5 September 2026"
    assert days_between(AT.replace(year=2025), AT) == "7 March 2025 to 7 March 2026"
    assert (hbar_words(0), hbar_words(865_932), hbar_words(5_948_228_610)) == (
        "0", "less than 0.01", "59.48")  # fmt: skip
    assert (dollar_words(0), dollar_words(0.0008), dollar_words(11.3648)) == (
        "$0", "less than $0.01", "$11.36")  # fmt: skip
