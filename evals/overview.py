"""The counts of the event overview (design 12.1, S5): facts read by programs, never by a model.

    python -m evals.overview

For each event, the projects by prize, by Hedera proof, by life, by the kinds of Hedera ID that
the ledger confirms, and by theme (only the projects whose card keeps a category); each count for
all the projects of the event and for those that took a Hedera prize. Also how many projects are
linked across events: the same repository, or the same Hedera ID that is not a shared service
(design 8.4, search/seen.py). The charts of the website count in the same way
(search/counts.py), for the list on the screen. Also how many projects have a proof that only the
IDs of their code give, as their mark "Proof: found in the code" says (design 7.3). Also the cards
of the model and the version of the website: how many there are, how many quotes the model gave,
how many of them were found word for word in their page, and how many fields were dropped for a
quote that was not found (design 6.3).

It writes evals/results/<UTC time>-overview.json, in numbers only: an event is named by its site
and its short name in the address, never by a text of a page. The life of a project depends on
the day, so the counts are those of the day the file was made.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.db.cards import CardStore
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.search import counts as counting
from hackathon_memory.search import filters, seen
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
WON = counting.WON
# The projects whose proof only the IDs of their code give: each ID with the status "proof found"
# was found in the code (search/listing.py, proven_by_code_only).
_CODE_ONLY = (
    "SELECT count(*) FROM (SELECT h.project_id FROM hedera_ids h "
    "JOIN id_checks c ON c.hedera_id = h.id WHERE c.status = 'proof_found' "
    "GROUP BY h.project_id HAVING bool_and(h.found_in = 'code')) only_the_code"
)


def counts(conninfo: str, *, model: str, version: str, now: datetime) -> dict:
    """The counts of every event, the projects in all, and the projects linked across events."""
    rows = filters.facts(conninfo, model=model, version=version, now=now)
    with psycopg.connect(conninfo) as conn:
        names = {str(event_id): (site, slug) for event_id, site, slug in
                 conn.execute("SELECT id, site, slug FROM events").fetchall()}  # fmt: skip
        (code_only,) = conn.execute(_CODE_ONLY).fetchone()
    by_event: dict[str, list[filters.Facts]] = defaultdict(list)
    for row in rows:
        by_event[row.event].append(row)
    events = []
    for event, members in by_event.items():
        found = counting.tally(members)
        site, slug = names[event]
        events.append({
            "site": site, "slug": slug,
            "year": int(members[0].year) if members[0].year else None,
            "projects": found.projects, "winner_entries": found.winner_entries,
            "with_theme": found.with_theme, "prize": dict(found.prize),
            "proof": {"all": dict(found.proof), WON: dict(found.proof_won)},
            "life": {"all": dict(found.life), WON: dict(found.life_won)},
            "services": {"all": dict(found.services), WON: dict(found.services_won)},
            "themes": {"all": dict(found.themes), WON: dict(found.themes_won)},
        })  # fmt: skip
    events.sort(key=lambda e: (-(e["year"] or 0), e["site"], e["slug"]))
    return {
        "test": "overview",
        "made_on": now.date().isoformat(),
        "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "share_needs": 20,
        "projects": len(rows),
        "proof_from_the_code_only": code_only,
        "events": events,
        "came_back": seen.counted(seen.came_back(conninfo)),
        "cards": CardStore(conninfo).counts(model, version),
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
    linked = found["came_back"]["groups"]
    print(f"{found['projects']} projects in {len(found['events'])} events; "
          f"{linked} groups linked across events. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
