"""The proof rule (design 7.2). Every id and every date here is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import (
    ANOTHER_KIND,
    CANNOT_BE_CHECKED,
    DATES_DO_NOT_FIT,
    FOUND_BUT_EMPTY,
    NO_ID_GIVEN,
    NOT_FOUND,
    ORDER,
    PROOF_FOUND,
    TESTNET_LAST_RESET,
    WINDOW_NOT_KNOWN,
    Window,
    best,
    judge,
    kind_fits,
    needs_a_look_inside,
    window_of,
)
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC

START = datetime(2026, 3, 6, 16, 0, tzinfo=UTC)  # the event starts on a Friday afternoon
END = date(2026, 3, 8)  # and ends on the Sunday
WINDOW = window_of(START, END)
ASKED = datetime(2026, 10, 11, tzinfo=UTC)
DURING = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
LONG_BEFORE = datetime(2025, 1, 15, tzinfo=UTC)
LONG_AFTER = datetime(2026, 8, 1, tzinfo=UTC)


def thing(kind: str | None = TOPIC, *, network: str = "testnet", **facts: object) -> LedgerFacts:
    values: dict = {"created_at": DURING, "first_activity_at": DURING, "last_activity_at": DURING}
    return LedgerFacts(
        "0.0.3456789",
        network,
        ASKED,
        found=kind is not None,
        kind=kind,
        **((values | facts) if kind else {}),
    )


# --------------------------------------------------------------------- the window


def test_the_window_runs_from_30_days_before_the_start_to_14_days_after_the_end() -> None:
    assert WINDOW is not None
    assert WINDOW.start == datetime(2026, 2, 4, 16, 0, tzinfo=UTC)
    assert WINDOW.end.date() == date(2026, 3, 22)
    assert WINDOW.holds(datetime(2026, 3, 22, 23, 59, tzinfo=UTC))  # the whole last day counts
    assert not WINDOW.holds(datetime(2026, 3, 23, 0, 0, 1, tzinfo=UTC))
    assert not WINDOW.holds(WINDOW.start - timedelta(seconds=1))
    assert not WINDOW.holds(None)


def test_an_event_with_no_start_or_no_end_has_no_window() -> None:
    assert window_of(START, None) is None
    assert window_of(None, END) is None


# --------------------------------------------------------------------- the kind


@pytest.mark.parametrize(
    ("said", "kind", "fits"),
    [
        (None, ACCOUNT, True),  # the page says nothing about the kind
        (TOPIC, TOPIC, True),
        (TOKEN, TOKEN, True),
        (TOKEN, CONTRACT, True),  # a contract can make a token
        (ACCOUNT, CONTRACT, True),  # a contract has an account
        (CONTRACT, CONTRACT, True),
        (CONTRACT, TOKEN, False),
        (TOPIC, ACCOUNT, False),
        (TOPIC, CONTRACT, False),
        (TOKEN, ACCOUNT, False),
        (ACCOUNT, TOPIC, False),
    ],
)
def test_which_kinds_a_word_of_the_page_can_mean(said: str | None, kind: str, fits: bool) -> None:
    assert kind_fits(said, kind) is fits


# --------------------------------------------------------------------- one id on one network


def test_a_thing_made_inside_the_window_is_proof() -> None:
    assert judge(thing(), TOPIC, WINDOW) == PROOF_FOUND
    assert judge(thing(ACCOUNT), None, WINDOW) == PROOF_FOUND


def test_a_thing_made_before_and_used_inside_the_window_is_proof() -> None:
    older = thing(created_at=LONG_BEFORE, first_activity_at=LONG_BEFORE, last_activity_at=DURING)
    assert judge(older, TOPIC, WINDOW) == PROOF_FOUND
    first_use = thing(created_at=LONG_BEFORE, first_activity_at=DURING, last_activity_at=LONG_AFTER)
    assert judge(first_use, TOPIC, WINDOW) == PROOF_FOUND


def test_a_thing_that_exists_with_dates_far_from_the_event_is_not_proof() -> None:
    # The wrong pattern: "the id exists, so the proof is real".
    old = thing(
        ACCOUNT, created_at=LONG_BEFORE, first_activity_at=LONG_BEFORE, last_activity_at=LONG_BEFORE
    )
    assert judge(old, None, WINDOW) == DATES_DO_NOT_FIT
    late = thing(created_at=LONG_AFTER, first_activity_at=LONG_AFTER, last_activity_at=LONG_AFTER)
    assert judge(late, TOPIC, WINDOW) == DATES_DO_NOT_FIT


def test_a_thing_of_another_kind_than_the_page_says_is_not_proof() -> None:
    assert judge(thing(ACCOUNT), TOPIC, WINDOW) == ANOTHER_KIND
    assert judge(thing(CONTRACT), TOKEN, WINDOW) == PROOF_FOUND  # a word that fits


def test_an_empty_thing_is_found_but_empty() -> None:
    assert judge(thing(empty=True, activity_count=0), TOPIC, WINDOW) == FOUND_BUT_EMPTY
    assert judge(thing(TOKEN, empty=True), TOKEN, WINDOW) == FOUND_BUT_EMPTY
    assert judge(thing(CONTRACT, deleted=True), CONTRACT, WINDOW) == FOUND_BUT_EMPTY
    # Only a deleted contract counts as empty. A deleted topic is judged by its dates.
    assert judge(thing(deleted=True), TOPIC, WINDOW) == PROOF_FOUND


def test_an_id_that_is_nothing_on_the_network_is_not_found() -> None:
    assert judge(thing(None), TOPIC, WINDOW) == NOT_FOUND


def test_without_the_end_of_the_event_the_dates_are_not_judged() -> None:
    assert judge(thing(), TOPIC, None) == WINDOW_NOT_KNOWN
    # What does not depend on the dates is still said.
    assert judge(thing(ACCOUNT), TOPIC, None) == ANOTHER_KIND
    assert judge(thing(empty=True), TOPIC, None) == FOUND_BUT_EMPTY
    assert judge(thing(None), TOPIC, None) == NOT_FOUND


def test_a_test_network_id_of_an_event_before_the_last_reset_cannot_be_checked() -> None:
    old_event = window_of(datetime(2023, 9, 1, tzinfo=UTC), date(2023, 9, 30))
    assert old_event is not None and old_event.end < TESTNET_LAST_RESET
    # Whatever answers under that number today is not what the project made.
    assert judge(thing(), TOPIC, old_event) == CANNOT_BE_CHECKED
    assert judge(thing(None), TOPIC, old_event) == CANNOT_BE_CHECKED
    assert judge(thing(None, network="mainnet"), TOPIC, old_event) == NOT_FOUND


# --------------------------------------------------------------------- used before and after


def test_a_thing_used_before_and_after_the_window_needs_one_more_question() -> None:
    assert WINDOW is not None
    spans = thing(
        created_at=LONG_BEFORE, first_activity_at=LONG_BEFORE, last_activity_at=LONG_AFTER
    )
    assert needs_a_look_inside(spans, WINDOW)
    assert judge(spans, TOPIC, WINDOW) == DATES_DO_NOT_FIT  # not asked: not counted as used
    assert judge(spans, TOPIC, WINDOW, used_inside=False) == DATES_DO_NOT_FIT
    assert judge(spans, TOPIC, WINDOW, used_inside=True) == PROOF_FOUND


def test_no_more_question_is_needed_when_the_dates_already_tell() -> None:
    assert WINDOW is not None
    before_only = thing(
        created_at=LONG_BEFORE, first_activity_at=LONG_BEFORE, last_activity_at=LONG_BEFORE
    )
    last_inside = thing(
        created_at=LONG_BEFORE, first_activity_at=LONG_BEFORE, last_activity_at=DURING
    )
    never_used = thing(created_at=LONG_BEFORE, first_activity_at=None, last_activity_at=None)
    for facts in (thing(), before_only, last_inside, never_used, thing(None)):
        assert not needs_a_look_inside(facts, WINDOW)


# --------------------------------------------------------------------- several statuses


def test_the_best_status_counts() -> None:
    assert best([NOT_FOUND, DATES_DO_NOT_FIT, PROOF_FOUND]) == PROOF_FOUND
    assert best([ANOTHER_KIND, NOT_FOUND]) == ANOTHER_KIND
    assert best([DATES_DO_NOT_FIT, FOUND_BUT_EMPTY]) == DATES_DO_NOT_FIT
    assert best([]) == NO_ID_GIVEN
    assert len(set(ORDER)) == len(ORDER) == 8


def test_the_same_number_on_two_networks_is_two_things_and_the_dates_tell_them_apart() -> None:
    # Seen on real ids: the number of a topic on the test network is an old account on the
    # main network.
    on_test = thing(TOPIC, network="testnet")
    on_main = thing(
        ACCOUNT,
        network="mainnet",
        created_at=LONG_BEFORE,
        first_activity_at=LONG_BEFORE,
        last_activity_at=LONG_BEFORE,
    )
    assert judge(on_main, TOPIC, WINDOW) == ANOTHER_KIND
    assert judge(on_main, None, WINDOW) == DATES_DO_NOT_FIT  # the page names no kind
    assert best([judge(on_main, None, WINDOW), judge(on_test, None, WINDOW)]) == PROOF_FOUND


def test_the_window_is_a_plain_record() -> None:
    assert Window(START, START + timedelta(days=1)).holds(START)
