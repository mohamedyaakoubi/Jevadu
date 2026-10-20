"""Are the events of the list blocks that follow each other? And the exact number for each event.

No request. It reads the file of the walk.

Each page of the list shows 33 rows, and its last row is the first row of the next page (seen on
pages 1 and 2: the same project). So the walk counted 20 rows twice, one for each of the 20 page
ends. If the list is sorted by event, the place of each shared row is known: in the list without
repeats they are the rows 33, 65, 97, ... So the exact number for each event can be computed.

    python found_blocks.py            print only
    python found_blocks.py --write    also write the exact numbers into the file
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
path = Path.cwd() / "data" / "found" / "ethglobal.com" / "hedera-list.json"
found = json.loads(path.read_text(encoding="utf-8"))
rows = found["listed_by_event"]  # in the order in which the walk first saw each event
pages = found["pages_read"]
PER_PAGE = 32  # 33 rows are shown, and the last one is shared with the next page

# 1. Do the prize projects of each event sit on pages that follow each other, in that order?
span: dict[str, list[int]] = {}
for project in found["with_prize"]:
    low_high = span.setdefault(project["event"], [project["list_page"], project["list_page"]])
    low_high[0] = min(low_high[0], project["list_page"])
    low_high[1] = max(low_high[1], project["list_page"])
order_ok = True
previous_high = 0
for event in rows:
    low, high = span.get(event, [None, None])
    if low is not None:
        if low < previous_high:
            order_ok = False
        previous_high = max(previous_high, high)

# 2. The exact numbers. A shared row is counted in the walk at the end of page p and again at
#    the start of page p + 1. In the list without repeats it is row 32 * p + 1.
shared = {PER_PAGE * p + 1 for p in range(1, pages)}
exact: dict[str, int] = {}
position = 1  # the place of the first row of the event, in the list without repeats
for event, seen in rows.items():
    size = 0
    counted = 0
    while counted < seen:
        counted += 2 if (position + size) in shared else 1
        size += 1
    if counted != seen:
        print(f"the rows of {event!r} do not fit: a shared row sits on the edge of two events")
    exact[event] = size
    position += size

print(f"{'event':30} {'pages of its prize projects':>28} {'rows seen':>10} {'exact':>6}")
for event, seen in rows.items():
    low, high = span.get(event, ["-", "-"])
    print(f"{event[:30]:30} {str(low) + ' to ' + str(high):>28} {seen:10} {exact[event]:6}")
print(f"events follow each other in blocks (by their prize projects): {order_ok}")
print(f"rows seen: {sum(rows.values())}; exact: {sum(exact.values())}; "
      f"expected exact: {sum(rows.values()) - (pages - 1)}")

if "--write" in sys.argv:
    if not order_ok or sum(exact.values()) != sum(rows.values()) - (pages - 1):
        print("NOT written: the check above did not hold")
        sys.exit(1)
    if found.get("listed_counts") == "exact":
        print("already exact, not written again")
        sys.exit(0)
    found["listed_by_event"] = exact
    found["listed_counts"] = "exact"
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)
    print(f"written: {path}")
