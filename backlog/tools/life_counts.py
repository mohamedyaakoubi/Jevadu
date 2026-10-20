"""How many projects are active, quiet, stopped or unknown today? Counts only.

It runs the life rule of the listing over every project, and prints the numbers by status, by
reason, and by prize. No name, no link. For planning: these are counts of a script, not a test.

    .venv/Scripts/python.exe backlog/tools/life_counts.py
"""

from __future__ import annotations

import sys
from collections import Counter

import psycopg

from hackathon_memory.search import listing
from hackathon_memory.search.engine import Hit
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
conninfo = Settings().database_conninfo()
with psycopg.connect(conninfo) as conn:
    ids = [row[0] for row in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
cards = listing.cards(conninfo, [Hit(project, 0.0, None, None) for project in ids])

by_status: Counter[str] = Counter()
by_reason: Counter[str] = Counter()
by_prize: Counter[tuple[str, str]] = Counter()
code: Counter[str] = Counter()
for card in cards:
    assert card.life is not None
    by_status[card.life.status] += 1
    by_reason[card.life.why] += 1
    by_prize[(card.prize_state, card.life.status)] += 1
    code[card.code_status or "not asked or no repository"] += 1

print("projects:", len(cards))
print("by status:", dict(by_status.most_common()))
print("by reason:")
for reason, count in by_reason.most_common():
    print(f"  {count:4}  {reason}")
print("by prize and status:")
for (prize, status), count in sorted(by_prize.items()):
    print(f"  {count:4}  {prize}, {status}")
print("the code:", dict(code.most_common()))
