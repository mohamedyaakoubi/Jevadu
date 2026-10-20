"""Write the files the owner needs for the three questions of Gate B. Prints counts only.

1. data/by-hand/gate-b-candidates.txt: every project whose Hedera proof was found, with its
   name, its short line, its event and the link to its page, grouped by event. The owner picks
   three that he finds interesting and different from each other.
2. data/by-hand/gate-b-questions.txt: the file that the proof reads, with the explanation and an
   example in comments. It is written only when it does not exist yet: it never overwrites the
   owner's own questions.

Both files stay in data/, outside git: they hold text of the pages.

    .venv/Scripts/python.exe backlog/tools/gate_b_candidates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
settings = Settings()
folder = Path(settings.data_dir) / "by-hand"

with psycopg.connect(settings.database_conninfo()) as conn:
    rows = conn.execute(
        "SELECT e.name, p.name, p.short_line, p.page_url, p.prize_state FROM projects p "
        "JOIN events e ON e.id = p.event_id WHERE p.proof_status = 'proof_found' "
        "ORDER BY e.starts_at, p.name"
    ).fetchall()

PRIZE = {"hedera_prize": "won a Hedera prize", "other_prize": "won another prize", "no_prize": ""}
lines = [
    "# Projects whose Hedera proof was found (the ledger shows their ids in use during the",
    "# event). Pick three that are different from each other. Open each link, read the page,",
    "# and write one idea for each in gate-b-questions.txt, in your own words.",
    "",
]
event = None
for event_name, name, short_line, page, prize in rows:
    if event_name != event:
        lines += ["", f"== {event_name}"]
        event = event_name
    note = f"  ({PRIZE[prize]})" if PRIZE.get(prize) else ""
    lines += [f"- {name}{note}", f"  {short_line}", f"  {page}"]
(folder / "gate-b-candidates.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

questions = folder / "gate-b-questions.txt"
if not questions.exists():
    questions.write_text(
        "# The three questions of Gate B, written by a person.\n"
        "#\n"
        "# For each question, two lines:\n"
        "#   idea: what a builder would type, in your own words (do not copy the page)\n"
        "#   finds: the link of the project page that this idea must find\n"
        "# Leave an empty line between two questions. A line that starts with # is a note.\n"
        "#\n"
        "# An example, with an invented project (it is a note, so it is not read):\n"
        "# idea: let people at a market pay small sellers with a stable coin\n"
        "# finds: https://ethglobal.com/showcase/pebble-pay-x1y2z\n"
        "\n",
        encoding="utf-8",
    )
    print("the question file was written, empty")
else:
    print("the question file exists already, and was not touched")
print("projects in the list of candidates:", len(rows))
print("events in it:", len({row[0] for row in rows}))
