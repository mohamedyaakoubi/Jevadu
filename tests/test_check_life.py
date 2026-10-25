"""The life rule of design 7.4, on invented dates."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hackathon_memory.check.life import (
    ACTIVE,
    NOT_OVER,
    QUIET,
    STOPPED,
    TOO_EARLY,
    UNKNOWN,
    life_of,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
END = date(2026, 3, 8)  # the last day of an invented event, long over
RECENT_END = date(2026, 9, 16)  # the last day of an invented event that ended 26 days ago


def at(days_after_the_end: float, end: date = END) -> datetime:
    return datetime.combine(end, datetime.min.time(), tzinfo=UTC) + timedelta(
        days=days_after_the_end, hours=12
    )


@pytest.mark.parametrize(
    ("push", "ledger", "status"),
    [
        (NOW - timedelta(days=10), None, ACTIVE),  # code changed lately
        (at(1), NOW - timedelta(days=89), ACTIVE),  # the ledger is used lately
        (at(60), None, QUIET),  # a sign of life, nothing lately
        (None, at(31), QUIET),
        (at(29), at(2), STOPPED),  # nothing later than 30 days after the event
        (at(-5), None, STOPPED),
        (None, None, UNKNOWN),  # nothing to look at
    ],
)
def test_the_statuses_of_an_event_long_over(
    push: datetime | None, ledger: datetime | None, status: str
) -> None:
    assert life_of(event_end=END, last_push=push, last_ledger_activity=ledger, now=NOW).status == (
        status
    )


def test_the_newest_sign_is_the_one_that_counts() -> None:
    life = life_of(event_end=END, last_push=at(1), last_ledger_activity=at(50), now=NOW)
    assert (life.status, life.last_sign) == (QUIET, at(50))


def test_the_line_is_the_end_of_the_last_day_plus_thirty_days() -> None:
    last_day_end = datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC)
    just_after = last_day_end + timedelta(days=30, seconds=1)
    just_before = last_day_end + timedelta(days=30) - timedelta(seconds=1)
    assert life_of(event_end=END, last_push=just_after, last_ledger_activity=None,
                   now=NOW).status == QUIET  # fmt: skip
    assert life_of(event_end=END, last_push=just_before, last_ledger_activity=None,
                   now=NOW).status == STOPPED  # fmt: skip


def test_the_work_of_a_recent_event_is_not_a_sign_of_life() -> None:
    # A push on the last day, and one three days ago: both are inside the 30 days after the end.
    for push in (at(0, RECENT_END), NOW - timedelta(days=3)):
        life = life_of(event_end=RECENT_END, last_push=push, last_ledger_activity=None, now=NOW)
        assert (life.status, life.last_sign) == (TOO_EARLY, push)


def test_a_sign_of_life_after_a_recent_event_counts_at_once() -> None:
    end = date(2026, 8, 13)  # ended 60 days ago
    later = life_of(event_end=end, last_push=at(45, end), last_ledger_activity=None, now=NOW)
    inside = life_of(event_end=end, last_push=at(10, end), last_ledger_activity=None, now=NOW)
    assert (later.status, inside.status) == (ACTIVE, TOO_EARLY)


def test_too_early_to_tell_lasts_90_days_after_the_last_day() -> None:
    last_day = (NOW - timedelta(days=90)).date()  # its end is a little less than 90 days ago
    push = at(0, last_day)
    early = life_of(event_end=last_day, last_push=push, last_ledger_activity=None, now=NOW)
    over = life_of(event_end=last_day - timedelta(days=1), last_push=push,
                   last_ledger_activity=None, now=NOW)  # fmt: skip
    assert (early.status, over.status) == (TOO_EARLY, STOPPED)


def test_with_no_end_of_the_event_no_sign_can_be_judged() -> None:
    recent = life_of(event_end=None, last_push=NOW - timedelta(days=3), last_ledger_activity=None,
                     now=NOW)  # fmt: skip
    old = life_of(event_end=None, last_push=at(60), last_ledger_activity=None, now=NOW)
    for life in (recent, old):
        assert (life.status, life.why) == (UNKNOWN, "the end of the event is not known")


def test_a_hackathon_that_is_not_over_says_so() -> None:
    """A check can name a hackathon that still runs: its reason never says that it ended (design
    7.4, 25 October 2026)."""
    later = life_of(event_end=(NOW + timedelta(days=12)).date(), last_push=NOW - timedelta(days=1),
                    last_ledger_activity=None, now=NOW)  # fmt: skip
    last_day = life_of(event_end=NOW.date(), last_push=NOW - timedelta(hours=2),
                       last_ledger_activity=None, now=NOW)  # fmt: skip
    ended = life_of(event_end=NOW.date() - timedelta(days=1), last_push=NOW - timedelta(hours=2),
                    last_ledger_activity=None, now=NOW)  # fmt: skip
    assert (later.status, later.why) == (TOO_EARLY, NOT_OVER)
    assert last_day.why == NOT_OVER  # its last day runs until its end
    assert (ended.status, ended.why != NOT_OVER) == (TOO_EARLY, True)
