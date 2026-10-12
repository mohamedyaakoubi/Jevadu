"""The life rule of design 7.4, on invented dates."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hackathon_memory.check.life import ACTIVE, QUIET, STOPPED, UNKNOWN, life_of

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
END = date(2026, 3, 8)  # the last day of an invented event


def at(days_after_the_end: float) -> datetime:
    return datetime(2026, 3, 8, 12, tzinfo=UTC) + timedelta(days=days_after_the_end)


@pytest.mark.parametrize(
    ("push", "ledger", "status"),
    [
        (NOW - timedelta(days=10), None, ACTIVE),  # code changed lately
        (at(1), NOW - timedelta(days=89), ACTIVE),  # the ledger is used lately
        (at(60), None, QUIET),  # something after the event, nothing lately
        (None, at(31), QUIET),
        (at(29), at(2), STOPPED),  # nothing later than 30 days after the event
        (at(-5), None, STOPPED),
        (None, None, UNKNOWN),  # nothing to look at
    ],
)
def test_the_four_statuses_of_the_rule(
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


def test_with_no_end_of_the_event_only_active_can_be_told() -> None:
    recent = life_of(event_end=None, last_push=NOW - timedelta(days=3), last_ledger_activity=None,
                     now=NOW)  # fmt: skip
    old = life_of(event_end=None, last_push=at(60), last_ledger_activity=None, now=NOW)
    assert recent.status == ACTIVE
    assert (old.status, old.why) == (UNKNOWN, "the end of the event is not known")
