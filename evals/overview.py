"""The counts of the event overview (design 12.1, S5): facts read by programs, never by a model.

    python -m evals.overview

For each event, the projects by prize, by Hedera proof, by life, by the kinds of Hedera ID that
the ledger confirms, and by theme (only the projects whose card keeps a category); each count for
all the projects of the event and for those that took a Hedera prize. Also how many projects came
back: the same repository, or the same Hedera ID that is not a shared service, at two events
(design 8.4, search/seen.py).

It writes evals/results/<UTC time>-overview.json, in numbers only: an event is named by its site
and its short name in the address, never by a text of a page. The overview of the website reads
the newest file and shows its date (design rule 6). The life of a project depends on the day, so
the counts are those of the day the file was made.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.search import filters, seen
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
WON = "hedera_prize"
KINDS = ("account", "topic", "token", "contract")

_PROJECTS = """
SELECT p.id, e.site, e.slug, p.prize_state, p.entry_kind
FROM projects p JOIN events e ON e.id = p.event_id
"""
# The kinds of Hedera ID of each project that the ledger confirms (search/seen.py, CONFIRMED).
_SERVICES = """
SELECT DISTINCT h.project_id, f.kind
FROM hedera_ids h
JOIN id_checks c ON c.hedera_id = h.id AND c.status = ANY(%s)
JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network
WHERE f.kind = ANY(%s)
"""


def counts(conninfo: str, *, model: str, version: str, now: datetime) -> dict:
    """The counts of every event, the projects in all, and the projects that came back."""
    facts = {row.project_id: row for row in filters.facts(conninfo, model=model,
                                                          version=version, now=now)}  # fmt: skip
    with psycopg.connect(conninfo) as conn:
        projects = {row[0]: row[1:] for row in conn.execute(_PROJECTS).fetchall()}
        services: dict[int, set[str]] = defaultdict(set)
        for pid, kind in conn.execute(_SERVICES, (list(seen.CONFIRMED), list(KINDS))).fetchall():
            services[pid].add(kind)
    events: dict[tuple[str, str], dict] = {}
    for pid, (site, slug, prize, entry_kind) in sorted(projects.items()):
        one = facts[pid]
        event = events.setdefault((site, slug), {
            "site": site, "slug": slug, "year": int(one.year) if one.year else None,
            "projects": 0, "winner_entries": 0, "with_theme": 0, "prize": Counter(),
            "proof": {"all": Counter(), WON: Counter()}, "life": {"all": Counter(), WON: Counter()},
            "services": {"all": Counter(), WON: Counter()},
            "themes": {"all": Counter(), WON: Counter()},
        })  # fmt: skip
        event["projects"] += 1
        event["winner_entries"] += entry_kind == "winner_entry"
        event["with_theme"] += bool(one.category)
        event["prize"][prize] += 1
        for group in ("all", WON) if prize == WON else ("all",):
            event["proof"][group][one.proof] += 1
            event["life"][group][one.life] += 1
            for kind in services.get(pid, ()):
                event["services"][group][kind] += 1
            if one.category:
                event["themes"][group][one.category] += 1
    ordered = sorted(events.values(), key=lambda e: (-(e["year"] or 0), e["site"], e["slug"]))
    return {
        "test": "overview",
        "made_on": now.date().isoformat(),
        "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "share_needs": 20,
        "projects": len(projects),
        "events": json.loads(json.dumps(ordered)),  # the counters as plain objects
        "came_back": seen.counted(seen.came_back(conninfo)),
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    settings = Settings()
    now = datetime.now(UTC)
    found = counts(settings.database_conninfo(), model=settings.gemini_rewrite_model,
                   version=INSTRUCTIONS_VERSION, now=now)  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-overview.json"
    path.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{found['projects']} projects in {len(found['events'])} events; "
          f"{found['came_back']['groups']} groups came back. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
