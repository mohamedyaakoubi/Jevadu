"""The step that checks the Hedera ids of the projects against the ledger (design 7.1, 7.2).

For each id of each project the mirror node is asked what the id is, and the proof rule says
what that is worth for the project. An id whose page names no network is asked on the test
network and on the main network (design 7.1): the same number is another thing on each.

The step is safe to run again. An answer of the node that is younger than `max_age` is taken from
the table, so a second run asks almost nothing. The result of the rule is computed again on
every run, because it also depends on the end of an event, which is typed in by hand.

An error of the node does not stop the step: the id is named in the run, its project keeps its
old result, and the next ids are checked. Five errors in a row stop the step, because then the
node is away and asking on would only add load (design rule 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from hackathon_memory.check import asking
from hackathon_memory.check.proof import best, judge, window_of
from hackathon_memory.db.ledger import IdToCheck, LedgerStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode

STEP = "check"
# The networks that are asked when a page leaves the network open.
NETWORKS_WHEN_OPEN = ("testnet", "mainnet")
MAX_AGE = timedelta(days=7)
MAX_ERRORS_IN_A_ROW = 5


class NodeIsAway(Exception):
    """The mirror node failed several times in a row. The step stops."""


def _now() -> datetime:
    return datetime.now(UTC)


def check_ids(
    ledger: LedgerStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    max_age: timedelta = MAX_AGE,
    now: Callable[[], datetime] = _now,
) -> None:
    """Check every id of every project, and count what was done in `run`."""
    by_project: dict[int, list[IdToCheck]] = {}
    for item in ledger.ids_to_check():
        by_project.setdefault(item.project_id, []).append(item)
    errors_in_a_row = 0
    for project_id, items in by_project.items():
        checks: dict[int, dict[str, str]] = {}
        finished = True
        for item in items:
            window = window_of(item.event_starts_at, item.event_ends_on)
            for network in [item.network] if item.network else NETWORKS_WHEN_OPEN:
                mirror = mirrors.get(network)
                if mirror is None:
                    run.counts["on_a_network_that_is_not_asked"] += 1
                    finished = False
                    continue
                try:
                    facts = asking.facts_of(
                        ledger, mirror, item.entity_id, item.said_kind,
                        max_age=max_age, now=now, counts=run.counts,
                    )  # fmt: skip
                    used = asking.used_inside(
                        ledger, mirror, facts, window, now=now, counts=run.counts
                    )
                except MirrorError as error:
                    run.counts["errors_of_the_node"] += 1
                    run.problem(f"{item.entity_id} on {network}", str(error))
                    finished = False
                    errors_in_a_row += 1
                    if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                        raise NodeIsAway(
                            f"the mirror node failed {errors_in_a_row} times in a row"
                        ) from None
                    continue
                errors_in_a_row = 0
                status = judge(facts, item.said_kind, window, used)
                checks.setdefault(item.hedera_id, {})[network] = status
                run.counts[f"id_{status}"] += 1
        if finished:
            status = best([best(list(by_network.values())) for by_network in checks.values()])
            ledger.save_checks(project_id, checks, status)
            run.counts[f"project_{status}"] += 1
        else:
            run.counts["projects_not_finished"] += 1
    run.counts["projects_with_no_id"] = ledger.mark_projects_with_no_id()
    run.counts["requests"] = sum(mirror.requests_made for mirror in mirrors.values())
