"""How long a live reading of the history of Hedera IDs takes on the mirror node: the wait that the
ledger story would add to the check of a submission (design 7.5).

    python -m evals.history_times [--projects N]

It draws N projects (25 when not given, with a fixed seed) among those whose own IDs had their
history read by the step "history", and reads the history of each of their own IDs again from the
public mirror node, the same way and with the same limit of events (check/history.py). Each
reading is timed, the pauses between requests included, as a person would wait for it. The
mirror node is free and public, and nothing is saved but the times.

It writes evals/results/<UTC time>-history-times.json, in numbers only and with no ID: the seconds
for one ID and for all the own IDs of one project, at the median, at 90 and at 95 of 100, the
largest and the sum, how many readings the limit of events cut, and how many failed.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from evals.code_times import spread
from hackathon_memory.check.history import read_history
from hackathon_memory.check.story import on_its_network
from hackathon_memory.db.history import KINDS_THAT_FIT, OWN
from hackathon_memory.hedera.mirror import MIRROR_URLS, MirrorError, MirrorNode
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
PROJECTS = 25
SEED = 20261023  # the day of the first draw, so that a run again reads the same projects

OwnId = tuple[str, str, str, datetime | None]  # network, the ledger's ID, kind, made at


def own_ids(conninfo: str) -> dict[int, list[OwnId]]:
    """For each project whose own IDs were read: each of them once, on its network (where its
    status is the best), as the ledger names it, with its kind and the moment it was made."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            OWN  # noqa: S608  (fixed text)
            + "SELECT DISTINCT h.project_id, h.entity_id, c.network, c.status, r.kind, "
            "coalesce(f.ledger_id, h.entity_id), f.created_at "
            "FROM hedera_ids h JOIN own USING (entity_id) "
            "JOIN id_checks c ON c.hedera_id = h.id "
            "JOIN ledger_histories r ON r.entity_id = h.entity_id AND r.network = c.network "
            "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
            "WHERE c.status = ANY(%s)",
            (list(KINDS_THAT_FIT),),
        ).fetchall()
    found: dict[int, set[OwnId]] = {}
    for project, _, network, _, kind, ledger_id, made_at in on_its_network(rows):
        found.setdefault(project, set()).add((network, ledger_id, kind, made_at))
    return {project: sorted(ids, key=str) for project, ids in found.items()}


def measure(
    found: Mapping[int, Sequence[OwnId]],
    mirrors: Mapping[str, MirrorNode],
    *,
    projects: int = PROJECTS,
    seed: int = SEED,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Read the own IDs of `projects` projects drawn with `seed`, and give the numbers."""
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    chosen = chance.sample(sorted(found), min(projects, len(found)))
    per_id: list[float] = []
    per_project: list[float] = []
    cut = failed = 0
    for project in chosen:
        waited = 0.0
        for network, ledger_id, kind, made_at in found[project]:
            started = clock()
            try:
                history = read_history(mirrors[network], ledger_id, kind, made_at=made_at)
            except MirrorError:
                failed += 1
                continue
            took = clock() - started
            per_id.append(took)
            waited += took
            cut += int(history.cut)
        per_project.append(waited)
    numbers: dict = {"projects": len(chosen), "ids": len(per_id), "cut": cut, "failed": failed}
    if per_id:
        numbers["seconds_per_id"] = spread(per_id)
        numbers["seconds_per_project"] = spread(per_project)
    return numbers


def main(
    argv: Sequence[str],
    settings: Settings | None = None,
    mirrors: Mapping[str, MirrorNode] | None = None,
) -> int:
    projects = PROJECTS
    if len(argv) == 2 and argv[0] == "--projects" and argv[1].isdigit() and int(argv[1]) > 0:
        projects = int(argv[1])
    elif argv:
        print("usage: python -m evals.history_times [--projects N]")
        return 2
    settings = settings or Settings()
    mirrors = mirrors or {name: MirrorNode(name) for name in MIRROR_URLS}
    numbers = measure(own_ids(settings.database_conninfo()), mirrors, projects=projects)
    now = datetime.now(UTC)
    result = {"test": "history-times", "made_on": now.date().isoformat(),
              "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "seed": SEED, **numbers}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-history-times.json"
    path.write_bytes((json.dumps(result, indent=1) + "\n").encode("utf-8"))
    if "seconds_per_project" in numbers:
        one, all_of = numbers["seconds_per_id"], numbers["seconds_per_project"]
        print(
            f"Projects: {numbers['projects']}, IDs: {numbers['ids']}, cut: {numbers['cut']}, "
            f"failed: {numbers['failed']}. Seconds for one ID: median {one['median']}, 90 of "
            f"100 under {one['p90']}, largest {one['largest']}. For one project: median "
            f"{all_of['median']}, 90 of 100 under {all_of['p90']}, largest {all_of['largest']}. "
            f"Written: {path}"
        )
    else:
        print(f"No reading was timed. Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
