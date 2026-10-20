"""When do teams stop, and when do they make their Hedera ids? Measured on our own data.

The life rule (design 7.4) and the proof rule (design 7.2) use numbers of days that were written
without a measurement: 90 days for "recent", 30 days after the event for "something after the
event", and a window from 30 days before the start to 14 days after the end. This script looks
at what the data says about them. Counts only: no name, no link, no id.

1. The last push of code, counted in days after the last day of the event. A team that stops
   after the event leaves its last push in the days just after it (the demo, the README, a fix).
   Where that tail ends is where a later push starts to mean "the team went on".
2. The last activity of the project's own ids on the ledger, in the same way.
3. The day each id of a project was made, counted from the start and from the end of its event.

Only events that ended at least 180 days ago are used for 1 and 2: for a newer event, a push
150 days after its end cannot have happened yet, and its tail would look shorter than it is.

    .venv/Scripts/python.exe backlog/tools/measure_days_after_events.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NOW = datetime.now(UTC)
OLD_ENOUGH = timedelta(days=180)

OWN_IDS = """
SELECT h.project_id, e.starts_at, e.ends_on, f.created_at, f.last_activity_at
FROM hedera_ids h
JOIN projects p ON p.id = h.project_id
JOIN events e ON e.id = p.event_id
JOIN id_checks c ON c.hedera_id = h.id AND c.status <> 'not_found'
JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network AND f.found
WHERE NOT EXISTS (
    SELECT 1 FROM hedera_ids o JOIN projects op ON op.id = o.project_id
    WHERE o.entity_id = h.entity_id
      AND coalesce(op.repository_id, -op.id) <> coalesce(p.repository_id, -p.id))
"""


def end_of(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=UTC)


def buckets(days: list[float], edges: list[tuple[str, float, float]]) -> list[str]:
    total = len(days)
    lines = []
    running = 0
    for label, low, high in edges:
        count = sum(1 for d in days if low <= d < high)
        running += count
        lines.append(
            f"  {label:>24}: {count:4}  ({100 * count / total:5.1f}%, "
            f"so far {100 * running / total:5.1f}%)"
        )
    return lines


AFTER = [
    ("before the last day", -1e9, 0),
    ("the last day", 0, 1),
    ("1 to 3 days after", 1, 4),
    ("4 to 7 days after", 4, 8),
    ("8 to 14 days after", 8, 15),
    ("15 to 21 days after", 15, 22),
    ("22 to 30 days after", 22, 31),
    ("31 to 60 days after", 31, 61),
    ("61 to 90 days after", 61, 91),
    ("91 to 180 days after", 91, 181),
    ("more than 180 days after", 181, 1e9),
]

out: list[str] = [f"Measured on {NOW:%Y-%m-%d %H:%M} UTC from the local database. Counts only."]
with psycopg.connect(Settings().database_conninfo()) as conn:
    pushes = conn.execute(
        "SELECT e.slug, e.ends_on, r.last_push_at FROM projects p "
        "JOIN events e ON e.id = p.event_id JOIN repositories r ON r.id = p.repository_id "
        "WHERE r.code_status = 'found' AND r.last_push_at IS NOT NULL AND e.ends_on IS NOT NULL"
    ).fetchall()
    own = conn.execute(OWN_IDS).fetchall()

# 1. the last push
old = [(slug, end, push) for slug, end, push in pushes if NOW - end_of(end) >= OLD_ENOUGH]
days = [(push - end_of(end)).total_seconds() / 86400 + 1 for _, end, push in old]
# +1: a push on the last day itself counts as day 0 to 1, as "the last day".
out.append("")
out.append(
    f"1. The last push of code, in days after the last day of the event: {len(days)} projects "
    f"of {len({s for s, _, _ in old})} events that ended at least 180 days ago."
)
out.extend(buckets(days, AFTER))
for share in (50, 75, 80, 90):
    stopped = sorted(d for d in days if d < 91)  # the ones that did not go on to the last 90 days
    if stopped:
        place = min(len(stopped) - 1, int(len(stopped) * share / 100))
        out.append(f"  {share}% of the projects whose last push is not recent pushed last by day "
                   f"{stopped[place]:.0f} after the end")

# 2. the ledger
ledger_by_project: dict[int, tuple[date, datetime]] = {}
for project, _, end, _, last in own:
    if end is None or last is None or NOW - end_of(end) < OLD_ENOUGH:
        continue
    known = ledger_by_project.get(project)
    if known is None or last > known[1]:
        ledger_by_project[project] = (end, last)
ledger_days = [(last - end_of(end)).total_seconds() / 86400 + 1
               for end, last in ledger_by_project.values()]
out.append("")
out.append(
    f"2. The last activity of a project's own ids on the ledger, in days after the last day: "
    f"{len(ledger_days)} projects of events that ended at least 180 days ago."
)
if ledger_days:
    out.extend(buckets(ledger_days, AFTER))

# 3. when the ids were made
made: list[float] = []
made_after_end: list[float] = []
lengths = Counter()
for _, start, end, created, _ in own:
    if start is None or end is None or created is None:
        continue
    made.append((created - start).total_seconds() / 86400)
    made_after_end.append((created - end_of(end)).total_seconds() / 86400 + 1)
    lengths[(end - start.date()).days] += 1
BEFORE_START = [
    ("more than 90 days before", -1e9, -90),
    ("31 to 90 days before", -90, -30),
    ("15 to 30 days before", -30, -14),
    ("8 to 14 days before", -14, -7),
    ("1 to 7 days before", -7, 0),
    ("from the start on", 0, 1e9),
]
out.append("")
out.append(f"3. The day each own id was made, counted from the start of its event: {len(made)} ids.")
out.extend(buckets(made, BEFORE_START))
out.append("   and counted from the last day of the event, for the ones made from the start on:")
after_start = [a for m, a in zip(made, made_after_end, strict=True) if m >= 0]
out.extend(buckets(after_start, AFTER))
out.append(f"   lengths of the events in days (start to last day), by ids: {dict(sorted(lengths.items()))}")

text = "\n".join(out)
print(text)
folder = Path(__file__).resolve().parent
(folder / f"results-{NOW:%Y%m%d}-days-after-events.txt").write_text(text + "\n", encoding="utf-8")
