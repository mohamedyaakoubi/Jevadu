"""The measure of the search modes: the typing errors, the lines the model reads, the numbers."""

from __future__ import annotations

from evals.search_modes import _line, summary, with_typos

IDEA = "a wallet that lets street vendors accept payments without banks"


def test_the_typing_errors_are_the_same_for_the_same_seed() -> None:
    assert with_typos(IDEA, 7) == with_typos(IDEA, 7)
    assert with_typos(IDEA, 7) != IDEA


def test_two_long_words_get_one_error_each_and_short_words_none() -> None:
    before, after = IDEA.split(), with_typos(IDEA, 3).split()
    assert len(before) == len(after)
    changed = [(b, a) for b, a in zip(before, after, strict=True) if b != a]
    assert len(changed) == 2
    assert all(len(b) >= 5 for b, _ in changed)
    assert all(len(a) in (len(b), len(b) - 1) for b, a in changed)  # swapped, or one left out


def test_an_idea_with_no_long_word_is_kept() -> None:
    assert with_typos("a pay app", 1) == "a pay app"


def test_a_line_gives_the_name_and_the_short_line_or_the_first_text() -> None:
    texts = ("Pebble Pay", "Pay a vendor   with a coin.", "Long first text. " * 40)
    assert _line(3, texts, 20, False) == "3. Pebble Pay: Pay a vendor with a"
    with_text = _line(1, texts, 20, True)
    assert with_text.startswith("1. Pebble Pay: Pay a vendor with a Long first text.")
    assert _line(2, ("Fern", "", "A ballot."), 20, False) == "2. Fern: A ballot."


def test_each_mode_gets_its_share_time_and_cost() -> None:
    rows = [
        {"case": 1, "group": "g1", "mode": "words", "found": 1, "known": 1, "seconds": 0.2,
         "failed": False},
        {"case": 2, "group": "g2", "mode": "words", "found": 0, "known": 1, "seconds": 0.4,
         "failed": False},
        {"case": 1, "group": "g1", "mode": "both, then AI", "found": 1, "known": 1,
         "seconds": 3.0, "failed": True},
    ]  # fmt: skip
    numbers = summary(rows, {"both, then AI": [0.002, 0.001]})
    assert numbers["words"]["found"] == 1 and numbers["words"]["known"] == 2
    assert numbers["words"]["seconds_middle"] == 0.3
    assert numbers["words"]["cost_usd_per_search"] == 0.0
    assert numbers["both, then AI"]["failed_ai_calls"] == 1
    assert numbers["both, then AI"]["cost_usd_per_search"] == 0.003  # a retry is counted too
    assert "meaning" not in numbers  # a mode with no row is left out
