"""The proof rule: what the ledger facts of an id are worth for a project (design 7.2).

An id that exists proves almost nothing. Nearly every number exists on Hedera as something, and
the same number is another thing on each network. So the rule looks at three things: the kind of
the thing, whether it is empty, and its dates against the time of the event.

The window of an event runs from 30 days before it started to 14 days after it ended. The two
numbers are a first choice (design 7.2). The end of an event is typed in by hand. Until it is,
the dates cannot be judged, and the rule says so in place of guessing.

This module only judges. It asks nothing: the facts come from check/ledger.py.

What the rule does not show: that a project is good, or that an id belongs to the team that
names it. A team can paste the id of somebody else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC, TRANSACTION

# The statuses of design 7.2.
PROOF_FOUND = "proof_found"
DATES_DO_NOT_FIT = "dates_do_not_fit"
FOUND_BUT_EMPTY = "found_but_empty"
NOT_FOUND = "not_found"
CANNOT_BE_CHECKED = "cannot_be_checked"
NO_ID_GIVEN = "no_id_given"
# Two more, which the table of the design implies. The thing exists, and the ledger says that
# it is another kind of thing than the page says.
ANOTHER_KIND = "another_kind"
# The end of the event is not typed in yet, so its window is not known.
WINDOW_NOT_KNOWN = "window_not_known"

# From the best to the worst. For an id that is asked on two networks, and for a project with
# several ids, the best status is the one that counts.
ORDER = (
    PROOF_FOUND,
    WINDOW_NOT_KNOWN,
    DATES_DO_NOT_FIT,
    FOUND_BUT_EMPTY,
    ANOTHER_KIND,
    CANNOT_BE_CHECKED,
    NOT_FOUND,
    NO_ID_GIVEN,
)

DAYS_BEFORE = 30
DAYS_AFTER = 14
# The test network was last emptied on this day (Hedera's page on its test network, read on 9
# and on 11 October 2026). What stood on it before is gone, and its numbers were given again.
TESTNET_LAST_RESET = datetime(2024, 2, 1, tzinfo=UTC)

# What the page may call a thing of each kind. A contract can make a token, and a contract has
# an account, so a page that says "token" or "account" is not wrong about a contract.
_FITS = {
    TOKEN: {TOKEN, CONTRACT},
    ACCOUNT: {ACCOUNT, CONTRACT},
    CONTRACT: {CONTRACT},
    TOPIC: {TOPIC},
    TRANSACTION: {TRANSACTION},  # one action, judged by its own moment
}


@dataclass(frozen=True)
class Window:
    """The time in which a thing of a project should have been made or used."""

    start: datetime
    end: datetime

    def holds(self, moment: datetime | None) -> bool:
        return moment is not None and self.start <= moment <= self.end


def window_of(starts_at: datetime | None, ends_on: date | None) -> Window | None:
    """The window of an event, or None while its start or its end is not known."""
    if starts_at is None or ends_on is None:
        return None
    last_moment = datetime.combine(ends_on, time.max, tzinfo=UTC)
    return Window(starts_at - timedelta(days=DAYS_BEFORE), last_moment + timedelta(days=DAYS_AFTER))


def kind_fits(said_kind: str | None, kind: str | None) -> bool:
    """True if the ledger's kind is one that the page's word can mean. No word fits all."""
    return said_kind is None or kind in _FITS.get(said_kind, {said_kind})


def needs_a_look_inside(facts: LedgerFacts, window: Window) -> bool:
    """True if only one more question can tell whether the thing was used inside the window.

    That is the case when it was made before the window, and used both before the window and
    after it. Then something may have happened in between, or not.
    """
    if not facts.found or window.holds(facts.created_at):
        return False
    first, last = facts.first_activity_at, facts.last_activity_at
    if first is None or last is None or window.holds(first) or window.holds(last):
        return False
    return first < window.start and last > window.end


def judge(
    facts: LedgerFacts,
    said_kind: str | None,
    window: Window | None,
    used_inside: bool | None = None,
) -> str:
    """The status of one id on one network.

    `used_inside` is the answer to the one more question of `needs_a_look_inside`, when it was
    asked. Without it, a thing that was used before and after the window counts as not used
    inside it.
    """
    if window is not None and facts.network == "testnet" and window.end < TESTNET_LAST_RESET:
        return CANNOT_BE_CHECKED
    if not facts.found:
        return NOT_FOUND
    if not kind_fits(said_kind, facts.kind):
        return ANOTHER_KIND
    if facts.empty or (facts.kind == CONTRACT and facts.deleted):
        return FOUND_BUT_EMPTY
    if window is None:
        return WINDOW_NOT_KNOWN
    if (
        window.holds(facts.created_at)
        or window.holds(facts.first_activity_at)
        or window.holds(facts.last_activity_at)
        or used_inside is True
    ):
        return PROOF_FOUND
    return DATES_DO_NOT_FIT


def best(statuses: list[str]) -> str:
    """The best of several statuses. A project with no id has NO_ID_GIVEN."""
    return min(statuses, key=ORDER.index) if statuses else NO_ID_GIVEN
