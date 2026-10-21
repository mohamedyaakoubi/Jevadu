"""What the readings of the code found, counted over the collection (design 7.3).

    python -m evals.code_findings

Read from the tables, after `python -m hackathon_memory.pipeline hedera_code`. It sends no
request. For the projects with a full card, in all and by prize (a Hedera prize, a prize of
another sponsor only, no prize):

* whether their code was read, and what it shows: a use of Hedera (a Hedera package, an import
  of a Hedera library, a call to a Hedera service, or another sign), only a mention, or nothing;
* the same for the projects that name no Hedera ID on their page or in their README, since for
  them the code is the only thing that the tool can read about Hedera;

and, for the repositories that were read, how many name each Hedera package, call each Hedera
service and carry each sign.

It writes evals/results/<UTC time>-code-findings.json, in numbers only: no name of a project or
of a repository.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.check.proof import NO_ID_GIVEN
from hackathon_memory.parse.hedera_code import FEATURE, IMPORT, MENTION, PACKAGE, SIGN
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
USE = frozenset({PACKAGE, IMPORT, FEATURE, SIGN})

_PROJECTS = """
SELECT p.prize_state, p.proof_status, p.repository_id IS NOT NULL, r.archive_status,
       coalesce(array_agg(DISTINCT h.kind) FILTER (WHERE h.kind IS NOT NULL), '{}')
FROM projects p
LEFT JOIN repositories r ON r.id = p.repository_id
LEFT JOIN hedera_in_code h ON h.repository_id = r.id
WHERE p.entry_kind = 'full_card'
GROUP BY p.id, p.prize_state, p.proof_status, r.id, r.archive_status
"""
_NAMES = """
SELECT h.kind, h.name, count(DISTINCT h.repository_id)
FROM hedera_in_code h JOIN repositories r ON r.id = h.repository_id
WHERE r.archive_status IN ('read', 'partial') AND h.kind IN ('package', 'feature', 'sign')
GROUP BY 1, 2
"""


def state(has_repository: bool, archive: str | None, kinds: Sequence[str]) -> str:
    """What the code of one project shows, in one word."""
    if not has_repository:
        return "no_repository_on_github"
    if archive is None:
        return "not_read"
    if archive in ("gone", "blocked"):
        return "gone_or_blocked"
    if USE & set(kinds):
        return "use"
    return "mention_only" if MENTION in kinds else "nothing"


def counts(conninfo: str) -> dict:
    """Every count of this file, from the tables of one database."""
    by_prize: dict[str, Counter[str]] = defaultdict(Counter)
    no_id: dict[str, Counter[str]] = defaultdict(Counter)
    with psycopg.connect(conninfo) as conn:
        for prize, proof, has_repository, archive, kinds in conn.execute(_PROJECTS):
            one = state(has_repository, archive, kinds)
            for group in ("all", prize):
                by_prize[group][one] += 1
                if proof == NO_ID_GIVEN:
                    no_id[group][one] += 1
        names: dict[str, dict[str, int]] = defaultdict(dict)
        for kind, name, repositories in conn.execute(_NAMES):
            names[kind][name] = repositories
        read = dict(
            conn.execute(
                "SELECT archive_status, count(*) FROM repositories "
                "WHERE archive_status IS NOT NULL GROUP BY 1"
            ).fetchall()
        )
    return {
        "repositories_read": read,
        "projects": {group: dict(found) for group, found in sorted(by_prize.items())},
        "projects_with_no_hedera_id": {
            group: dict(found) for group, found in sorted(no_id.items())
        },
        "repositories_per_name": {
            kind: dict(sorted(found.items(), key=lambda one: (-one[1], one[0])))
            for kind, found in sorted(names.items())
        },  # fmt: skip
    }


def main(argv: Sequence[str], settings: Settings | None = None) -> int:
    if argv:
        print("usage: python -m evals.code_findings")
        return 2
    settings = settings or Settings()
    found = counts(settings.database_conninfo())
    now = datetime.now(UTC)
    result = {"test": "code-findings", "made_on": now.date().isoformat(),
              "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **found}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-code-findings.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    every = found["projects"].get("all", {})
    print(f"Projects with a full card: {sum(every.values())}. Their code shows a use of Hedera: "
          f"{every.get('use', 0)}; only a mention: {every.get('mention_only', 0)}; nothing: "
          f"{every.get('nothing', 0)}. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
