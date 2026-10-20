"""When the judging of each event took place, from the "timer" of the project pages.

The data of a project page holds a timer for the demo of the project to the judges: when the demo
started and ended, when the questions started and ended. This tool prints, for each event, how
many pages have such a time, and the first and the last of them, in days after the start of the
event. Dates and counts only. The scores of the site, which stand next to the timer, are not read.

    .venv/Scripts/python.exe backlog/tools/ethglobal/judging_times.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
JUDGING_KEYS = ("demoStartedAt", "demoEndedAt", "questionsStartedAt", "questionsEndedAt", "completedAt")


def when(value: object) -> datetime | None:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


pages: dict[str, int] = defaultdict(int)
with_timer: dict[str, int] = defaultdict(int)
moments: dict[str, list[datetime]] = defaultdict(list)
starts: dict[str, datetime] = {}

for body_path in sorted(RAW.glob("*.html")):
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    objects = [o for o in objects_with_key(page_data_text(soup), "tagline") if "slug" in o]
    if not objects:
        continue
    project = objects[0]
    event = project.get("event") or {}
    slug = str(event.get("slug"))
    start = when(event.get("startTime"))
    if start:
        starts[slug] = start
    pages[slug] += 1
    timer = (project.get("meta") or {}).get("timer")
    if not isinstance(timer, dict):
        continue
    found = [moment for key in JUDGING_KEYS if (moment := when(timer.get(key)))]
    if found:
        with_timer[slug] += 1
        moments[slug].extend(found)

print("event, start (UTC), pages, pages with a judging time, first and last judging time")
for slug in sorted(starts, key=starts.get):
    start = starts[slug]
    line = f"  {slug:18} {start:%a %Y-%m-%d %H:%M}  {pages[slug]:4} {with_timer[slug]:4}"
    if moments[slug]:
        first, last = min(moments[slug]), max(moments[slug])
        line += (
            f"   {first:%a %Y-%m-%d %H:%M} ({(first - start).total_seconds() / 86400:.1f} d)"
            f"   {last:%a %Y-%m-%d %H:%M} ({(last - start).total_seconds() / 86400:.1f} d)"
        )
    print(line)
print(f"now: {datetime.now(UTC):%Y-%m-%d %H:%M}")
