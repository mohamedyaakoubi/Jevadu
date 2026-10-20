"""When were the requests to ethglobal.com sent, and how many in a row? No request is sent.

    python backlog/tools/ethglobal/request_timeline.py

The site answered "too many requests" (429) on 11 October 2026 at 00:00:11 UTC. This script
rebuilds the timeline of every counted command from the files on disk: the records of the walks
and of the runs (start, end, number of requests), and the time of every saved page. Then it
counts, for every moment, how many requests fell into the window before it: 1, 5, 10 and 60
minutes. So the pace at the 429 can be compared with the highest pace that got no 429.

It prints times and counts only.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DATA = Path.cwd() / "data"
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def moment(stamp: str) -> datetime:
    return datetime.strptime(stamp, STAMP).replace(tzinfo=UTC)


# ---- the commands, from their records
commands = []
for path in sorted((DATA / "runs").glob("*.json")):
    record = json.loads(path.read_text(encoding="utf-8"))
    kind = "walk" if path.name.endswith("-ethglobal-list.json") else "run"
    commands.append(
        {
            "kind": kind,
            "start": moment(record["started_at"]),
            "end": moment(record["finished_at"]),
            "requests": record["requests_made"],
            "saved": record.get("pages_saved"),
            "stopped": record.get("stopped"),
        }
    )

# ---- the time of each request. A saved page gives its own time. A walk saves no page, so its
#      requests are spread evenly between its start and its end. Requests of a run that saved
#      nothing (robots.txt, the refused one) are put at the start and at the end of the run.
pages = sorted(
    moment(json.loads(p.read_text(encoding="utf-8"))["fetched_at"])
    for p in (DATA / "raw" / "ethglobal.com").glob("*.meta.json")
)
times: list[tuple[datetime, str]] = []
for command in commands:
    if command["kind"] == "walk":
        span = (command["end"] - command["start"]).total_seconds()
        for i in range(command["requests"]):
            times.append((command["start"] + timedelta(seconds=span * i / max(1, command["requests"] - 1)), "list page"))
    else:
        own = [t for t in pages if command["start"] <= t <= command["end"]]
        times.append((command["start"], "robots.txt"))
        times.extend((t, "project page") for t in own)
        extra = command["requests"] - 1 - len(own)
        times.extend((command["end"], "not saved") for _ in range(max(0, extra)))
times.sort()

print("The commands that were counted (UTC):")
for command in commands:
    seconds = (command["end"] - command["start"]).total_seconds()
    pace = seconds / max(1, command["requests"] - 1)
    print(
        f"  {command['start']:%d %b %H:%M:%S} to {command['end']:%H:%M:%S}  {command['kind']:4}  "
        f"{command['requests']:3} requests in {seconds:4.0f} s (one every {pace:.1f} s)"
        + (f"  saved {command['saved']}" if command["saved"] is not None else "")
        + ("  STOPPED: 429" if command["stopped"] and "429" in command["stopped"] else "")
    )
print(f"Requests in these records: {len(times)}. (24 earlier ones of 10 October were sent by hand-made scripts, before the count existed.)")


def most_in_window(until: datetime | None, minutes: int) -> tuple[int, datetime]:
    """The highest number of requests in any window of this length that ends before `until`."""
    best, best_end = 0, times[0][0]
    stamps = [t for t, _ in times if until is None or t <= until]
    start = 0
    for end, stamp in enumerate(stamps):
        while stamp - stamps[start] > timedelta(minutes=minutes):
            start += 1
        if end - start + 1 > best:
            best, best_end = end - start + 1, stamp
    return best, best_end


refused_at = next((c["end"] for c in commands if c["stopped"] and "429" in c["stopped"]), None)
quiet_until = max((c["end"] for c in commands if c["end"] < datetime(2026, 10, 10, 23, 0, tzinfo=UTC)), default=None)
print(f"\nThe 429 came at {refused_at:%d %b %H:%M:%S} UTC." if refused_at else "\nNo 429 in the records.")
print(f"{'window':>8} | {'most requests before 23:00 (no 429)':>36} | {'requests in the window that ended with the 429':>46}")
for minutes in (1, 5, 10, 60):
    before, when = most_in_window(quiet_until, minutes)
    at_stop = sum(1 for t, _ in times if refused_at and refused_at - timedelta(minutes=minutes) <= t <= refused_at)
    print(f"{minutes:>5} min | {before:>23} (ended {when:%H:%M:%S}) | {at_stop:>46}")

if refused_at:
    window = [kind for t, kind in times if refused_at - timedelta(minutes=5) <= t <= refused_at]
    print("\nWhat the last 5 minutes before the 429 held:", {k: window.count(k) for k in sorted(set(window))})
    earlier = [kind for t, kind in times if quiet_until and quiet_until - timedelta(minutes=5) <= t <= quiet_until]
    print("What the busiest 5 minutes of the evening held:", {k: earlier.count(k) for k in sorted(set(earlier))})
