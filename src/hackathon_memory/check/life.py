"""The life rule: is a project still alive? (design 7.4)

The signs are two dates: the last push of code to the repository (GitHub's facts, design 7.3),
and the last activity on the ledger of the project's own ids (the mirror node, design 7.1). An id
that projects with other code name too is not a sign: it is most likely a shared service, used by
many teams (design 8.4), and its activity says nothing about this project.

A sign of life is a sign later than 30 days after the last day of the event. Before that line,
the work is most likely still the work of the event, with its late fixes.

| Status | When |
|---|---|
| active | a sign of life in the last 90 days |
| quiet | a sign of life, but none in the last 90 days |
| stopped | no sign of life, and the event ended 90 days ago or more |
| too early to tell | no sign of life yet: the event is not over, or ended under 90 days ago |
| unknown | no date of the code and no activity of an id, or no known end of the event |

The 90 days follow the OpenSSF Scorecard: its check Maintained looks at the previous 90 days,
and it calls a project younger than 90 days too new to assess. When the end of the event is not
known, no sign can be told a sign of life, and the project is "unknown", with the reason. The
rule guesses no end. A check of a submission can name a hackathon that is still running; its
reason then says so (25 October 2026: it said "the event ended less than 90 days ago").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

ACTIVE = "active"
QUIET = "quiet"
STOPPED = "stopped"
TOO_EARLY = "too early to tell"
UNKNOWN = "unknown"

RECENT = timedelta(days=90)
AFTER_THE_EVENT = timedelta(days=30)
NOT_OVER = "the event is not over yet"  # the reason of a check whose hackathon still runs


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
    if event_end is None:
        return Life(UNKNOWN, last, "the end of the event is not known")
    ended = datetime.combine(event_end, time.max, tzinfo=UTC)
    if now <= ended:
        return Life(TOO_EARLY, last, NOT_OVER)
    if last > ended + AFTER_THE_EVENT:
        if last >= now - RECENT:
            return Life(ACTIVE, last, "a sign of life in the last 90 days")
        return Life(QUIET, last, "a sign of life, but none in the last 90 days")
    if now - ended < RECENT:
        return Life(
            TOO_EARLY, last, "the event ended less than 90 days ago, nothing later than 30 days yet"
        )
    return Life(STOPPED, last, "nothing later than 30 days after the event")
