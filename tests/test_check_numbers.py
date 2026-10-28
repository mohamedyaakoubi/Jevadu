"""Whether a thing can have been made inside a window, from its number alone (check/numbers.py).
Every number and moment is invented."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.check.numbers import Numbers
from hackathon_memory.check.proof import Window

DATED = {"testnet": [(datetime(2026, 1, 10, tzinfo=UTC), 100),
                     (datetime(2026, 3, 1, tzinfo=UTC), 200),
                     (datetime(2026, 5, 1, tzinfo=UTC), 300)]}  # fmt: skip
WINDOW = Window(datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC))


def test_a_number_between_the_known_bounds_of_a_window_may_be_inside() -> None:
    numbers = Numbers(DATED)
    assert numbers.could_be_made_inside("0.0.150", "testnet", WINDOW)
    assert numbers.could_be_made_inside("0.0.250", "testnet", WINDOW)


def test_a_number_outside_the_known_bounds_was_made_outside_the_window() -> None:
    numbers = Numbers(DATED)
    assert not numbers.could_be_made_inside("0.0.100", "testnet", WINDOW)  # made before it
    assert not numbers.could_be_made_inside("0.0.42", "testnet", WINDOW)
    assert not numbers.could_be_made_inside("0.0.300", "testnet", WINDOW)  # made after it
    assert not numbers.could_be_made_inside("0.0.9999", "testnet", WINDOW)


def test_what_the_numbers_cannot_tell_is_asked_as_before() -> None:
    numbers = Numbers(DATED)
    assert numbers.could_be_made_inside("0.0.42", "mainnet", WINDOW)  # no known number there
    assert numbers.could_be_made_inside("0x" + "ab" * 20, "testnet", WINDOW)
    assert numbers.could_be_made_inside("0.0.42-1767225600-1", "testnet", WINDOW)
    early = Window(datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 2, 1, tzinfo=UTC))
    assert not numbers.could_be_made_inside("0.0.150", "testnet", early)  # after its bound
    assert numbers.could_be_made_inside("0.0.50", "testnet", early)  # nothing known before
