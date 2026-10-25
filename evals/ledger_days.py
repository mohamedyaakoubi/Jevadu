"""On how many days the own Hedera IDs of a project were active (design 7.5, 25 October 2026).

    python -m evals.ledger_days

A day-by-day strip of the ledger on the card is worth drawing only if the days differ from one
project to the next. On 23 October 2026 the card got no chart, because nearly every project acts
only around its event (design 7.5, "Why no chart"); that measure counted the time before and after
the event, not the days inside it. This one counts the days.

It reads the same projects as the first measure of the ledger story (evals/ledger_story/run.py):
those with an own ID whose kind fits and whose history was read, and whose event has known days.
For each one, in the time of the card's table (30 days before the first day of the event to 30
days after its last day), it counts the days with at least one transaction of its own IDs, and how
many of them fall before the event, during it, and after it.

The rule, fixed before the first reading: the strip is worth drawing when at least 25% of the
projects with a transaction in that time were active on 3 days or more.

It writes evals/results/<UTC time>-ledger-days.json: numbers only, and the projects by their
number in the database.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, time
from pathlib import Path

from evals.ledger_story.run import Project, projects
from evals.test1.report import Counts, share
from hackathon_memory.check.story import LIFE_LINE, WINDOW_BEFORE
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
WORTH_DRAWING = 0.25  # fixed before the first reading
MANY_DAYS = 3
BANDS = ((1, 1), (2, 2), (3, 5), (6, 10), (11, 30), (31, 10_000))


def days_of(project: Project) -> dict[str, int]:
    """The days with a transaction of the project's own IDs in the time of the card's table."""
    first = project.starts_at - WINDOW_BEFORE
    last = datetime.combine(project.ends_on, time.max, tzinfo=UTC) + LIFE_LINE
    event_first = project.starts_at.date()
    days = {event.at.date() for event in project.events if first <= event.at <= last}
    return {
        "days": len(days),
        "before": sum(day < event_first for day in days),
        "during": sum(event_first <= day <= project.ends_on for day in days),
        "after": sum(day > project.ends_on for day in days),
        "services": len({event.service for event in project.events if first <= event.at <= last}),
    }


def band(days: int) -> str:
    for low, high in BANDS:
        if low <= days <= high:
            return f"{low}" if low == high else f"{low}-{high}" if high < 10_000 else f"{low}+"
    return "0"


def measure(found: Sequence[Project]) -> dict:
    rows = [(project.project_id, days_of(project)) for project in found]
    active = [(pid, row) for pid, row in rows if row["days"]]
    many = share(Counts(tuple(int(row["days"] >= MANY_DAYS) for _, row in active),
                        tuple(1 for _ in active)))  # fmt: skip
    return {
        "projects": len(rows),
        "with_a_transaction_in_the_time": len(active),
        "by_days": dict(
            sorted(
                Counter(band(row["days"]) for _, row in active).items(),
                key=lambda item: int(item[0].split("-")[0].rstrip("+")),
            )
        ),
        "active_on_3_days_or_more": many,
        "worth_drawing_at": WORTH_DRAWING,
        "worth_drawing": many["share"] is not None and many["share"] >= WORTH_DRAWING,
        "with_days_before_the_event": sum(row["before"] > 0 for _, row in active),
        "with_days_during_the_event": sum(row["during"] > 0 for _, row in active),
        "with_days_after_the_event": sum(row["after"] > 0 for _, row in active),
        "only_during_the_event": sum(row["during"] == row["days"] for _, row in active),
        "by_services": dict(sorted(Counter(row["services"] for _, row in active).items())),
        "per_project": [{"project": pid, **row} for pid, row in rows],
    }


def main(argv: Sequence[str]) -> int:
    del argv
    found, read = projects(Settings().database_conninfo())
    now = datetime.now(UTC)
    result = {"test": "ledger-days", "made_on": now.date().isoformat(), "read": read,
              **measure(found)}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-ledger-days.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    many = result["active_on_3_days_or_more"]
    print(f"Projects: {result['projects']}, with a transaction in the time: "
          f"{result['with_a_transaction_in_the_time']}. By days: {result['by_days']}. Active on 3 "
          f"days or more: {many['count']} of {many['of']} ({many['share']}, range "
          f"{many['range']}). Worth drawing: {result['worth_drawing']}. "
          f"Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
