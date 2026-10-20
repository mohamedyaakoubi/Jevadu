"""The life rule before and after the change of 12 October 2026 (`f2e26fd`), on the real data.

Counts only, for planning: these are counts of a script, not a test. It runs the old rule (read
from git, at the commit before `f2e26fd`) and the new rule over the same signs of every project,
and prints how many projects went from each old status to each new one. No name, no link.

    .venv/Scripts/python.exe backlog/tools/life_rule_before_after.py
"""

from __future__ import annotations

import subprocess
import sys
import types
from collections import Counter
from datetime import UTC, datetime

import psycopg

from hackathon_memory.check import life as new_rule
from hackathon_memory.search.listing import _SIGNS
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

old_source = subprocess.run(
    ["git", "show", "f2e26fd^:src/hackathon_memory/check/life.py"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    check=True,
).stdout
old_rule = types.ModuleType("old_life_rule")
sys.modules["old_life_rule"] = old_rule  # the dataclass looks its module up
exec(compile(old_source, "old_life_rule.py", "exec"), old_rule.__dict__)

now = datetime.now(UTC)
conninfo = Settings().database_conninfo()
with psycopg.connect(conninfo) as conn:
    ids = [row[0] for row in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    signs = conn.execute(_SIGNS, (ids,)).fetchall()

moves: Counter[tuple[str, str]] = Counter()
before: Counter[str] = Counter()
after: Counter[str] = Counter()
reasons: Counter[str] = Counter()
for _project, end, _code_status, _made_at, last_push, last_activity in signs:
    given = {
        "event_end": end,
        "last_push": last_push,
        "last_ledger_activity": last_activity,
        "now": now,
    }
    old = old_rule.life_of(**given).status
    new = new_rule.life_of(**given)
    moves[(old, new.status)] += 1
    before[old] += 1
    after[new.status] += 1
    reasons[new.why] += 1

print(f"run at {now:%Y-%m-%d %H:%M} UTC, on {len(signs)} projects")
print("old rule:", dict(before.most_common()))
print("new rule:", dict(after.most_common()))
print("from the old status to the new one:")
for (old, new_status), count in sorted(moves.items()):
    note = "" if old == new_status else "   (changed)"
    print(f"  {count:4}  {old} -> {new_status}{note}")
print("the reasons of the new rule:")
for reason, count in reasons.most_common():
    print(f"  {count:4}  {reason}")
