"""Counts from the file of the walk. No request. Prints events, sponsor ids and counts only."""

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
root = Path.cwd() / "data"
found = json.loads((root / "found" / "ethglobal.com" / "hedera-list.json").read_text(encoding="utf-8"))
print(f"pages read {found['pages_read']}, complete {found['complete']}")
listed = found["listed_by_event"]
print(f"projects in the list: {sum(listed.values())} in {len(listed)} events")
prize = found["with_prize"]
by_event_prize = Counter(p["event"] for p in prize)
sponsors = Counter(s for p in prize for s in p["sponsors"])
print(f"projects with a prize: {len(prize)}; different sponsor ids: {len(sponsors)}")
print("sponsor ids, by number of projects:", sponsors.most_common(12))

hand = [
    line.split("#", 1)[0].strip()
    for line in (root / "by-hand" / "ethglobal.com" / "project-pages.txt").read_text(encoding="utf-8").splitlines()
]
hand = [line for line in hand if line]
by_page = {p["page"]: p for p in prize}
print("\nthe pages of the hand-made list:")
for page in hand:
    hit = by_page.get(page)
    print(f"  {page.rsplit('/', 1)[1]}: " + (f"sponsors {hit['sponsors']}, event {hit['event']!r}, list page {hit['list_page']}" if hit else "NOT in the walk with a prize"))

anchors = [set(by_page[p]["sponsors"]) for p in hand if p in by_page]
common = set.intersection(*anchors) if anchors else set()
print(f"ids that every one of them has: {sorted(common)}")
if len(common) == 1:
    hedera = next(iter(common))
    winners = [p for p in prize if hedera in p["sponsors"]]
    per_event = Counter(p["event"] for p in winners)
    print(f"\nprojects with a prize of that sponsor: {len(winners)}")
    print(f"{'event':34} {'listed':>7} {'any prize':>10} {'this sponsor':>13}")
    for event, count in sorted(listed.items(), key=lambda kv: -kv[1]):
        print(f"{event[:34]:34} {count:7} {by_event_prize.get(event, 0):10} {per_event.get(event, 0):13}")
    only = sum(1 for p in winners if len(p["sponsors"]) == 1)
    print(f"winners with this sponsor only: {only}; with other sponsors too: {len(winners) - only}")
