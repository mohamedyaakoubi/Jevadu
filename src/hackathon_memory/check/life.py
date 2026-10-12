"""The life rule: is a project still alive? (design 7.4)

| Status | When |
|---|---|
| active | a change to the code, or activity on the ledger, in the last 90 days |
| quiet | nothing in the last 90 days, but something later than 30 days after the event |
| stopped | nothing later than 30 days after the event |
| unknown | nothing to look at: no date of the code and no activity of an id |

The signs are two dates: the last push of code to the repository (GitHub's facts, design 7.3),
and the last activity on the ledger of the project's own ids (the mirror node, design 7.1). An id
that projects with other code name too is not a sign: it is most likely a shared service, used by
many teams (design 8.4), and its activity says nothing about this project.

When the end of the event is not known, a project that shows no sign in the last 90 days cannot
be told quiet or stopped, and is "unknown", with the reason. The rule guesses no end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

ACTIVE = "active"
QUIET = "quiet"
STOPPED = "stopped"
UNKNOWN = "unknown"

RECENT = timedelta(days=90)
AFTER_THE_EVENT = timedelta(days=30)


@dataclass(frozen=True)
class Life:
    status: str
    last_sign: datetime | None  # the newest change of code or activity on the ledger
    why: str  # in plain words


def life_of(
    *,
    event_end: date | None,
    last_push: datetime | None,
    last_ledger_activity: datetime | None,
    now: datetime,
) -> Life:
    """The status of a project by the rule of design 7.4."""
    signs = [sign for sign in (last_push, last_ledger_activity) if sign is not None]
    if not signs:
        return Life(UNKNOWN, None, "no date of the code and no activity of its own ids")
    last = max(signs)
    if last >= now - RECENT:
        return Life(ACTIVE, last, "a sign of life in the last 90 days")
    if event_end is None:
        return Life(UNKNOWN, last, "the end of the event is not known")
    line = datetime.combine(event_end, time.max, tzinfo=UTC) + AFTER_THE_EVENT
    if last > line:
        return Life(QUIET, last, "nothing in the last 90 days, something after the event")
    return Life(STOPPED, last, "nothing later than 30 days after the event")
