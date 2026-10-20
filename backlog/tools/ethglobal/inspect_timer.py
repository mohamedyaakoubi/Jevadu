"""What the "timer" of the page data holds, and how far its dates are from the start of the event.

Counts, key names and numbers of days only. No text of a page, and no score of the site.

    .venv/Scripts/python.exe backlog/tools/ethglobal/inspect_timer.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
SCORES = ("autoOriginality", "autoPracticality", "autoTechnicality", "autoSummary")


def when(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, int | float) and value > 1_000_000_000:
        return datetime.fromtimestamp(value / (1000 if value > 10_000_000_000 else 1)).astimezone()
    return None


meta_keys: Counter[str] = Counter()
timer_kinds: Counter[str] = Counter()
days_after_start: dict[str, list[float]] = defaultdict(list)
by_event: dict[str, list[float]] = defaultdict(list)
pages = 0

for body_path in sorted(RAW.glob("*.html")):
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    objects = [o for o in objects_with_key(page_data_text(soup), "tagline") if "slug" in o]
    if not objects:
        continue
    pages += 1
    data = objects[0]
    meta = data.get("meta") or {}
    meta_keys.update(k for k in meta if k not in SCORES)
    timer = meta.get("timer")
    start = when((data.get("event") or {}).get("startTime"))
    if not isinstance(timer, dict):
        timer_kinds[f"timer is {type(timer).__name__}"] += 1
        continue
    for key, value in timer.items():
        moment = when(value)
        timer_kinds[f"timer.{key}: {'a time' if moment else type(value).__name__}"] += 1
        if moment and start:
            days = (moment - start).total_seconds() / 86400
            days_after_start[key].append(days)
            if key == "startedAt":
                by_event[(data.get("event") or {}).get("slug", "?")].append(days)

print(f"pages: {pages}")
print("keys of meta (the scores of the site are left out):", dict(meta_keys))
for line, count in timer_kinds.most_common():
    print(f"  {count:4}  {line}")
print("days between the start of the event and each time of the timer: smallest, median, largest")
for key, days in sorted(days_after_start.items()):
    days.sort()
    print(f"  {key}: {days[0]:.1f}, {days[len(days) // 2]:.1f}, {days[-1]:.1f}  ({len(days)} pages)")
print("timer.startedAt by event, in days after the start: smallest, largest, pages")
for slug, days in sorted(by_event.items()):
    print(f"  {slug}: {min(days):.1f} to {max(days):.1f}  ({len(days)})")
