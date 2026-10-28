"""The Hedera IDs of a project's code that prove its use of Hedera (design 7.3, 24 October 2026).

The code of a repository names many IDs that are not the team's own: a public token, the account
of a service, a number from a tutorial. So an ID of the code counts only when all of these hold:

* no page and no README of the collection names it, and the code of no other repository, in any
  of its forms: it is the project's own (db/code_ids.py). An EVM address and the 0.0 ID of one
  contract are one ID, which the ledger's answer shows: an ID is looked at again after it;
* the ledger knows it on a network as something that the proof rule finds, not empty, and made
  inside the window of the project's event: the team most likely made it for this event
  (counts_from_the_code, check/proof.py).

Measured before it was built, on 40 repositories drawn at random from the collection: 9 had no
proof and would get one this way (evals/results/20261023T230450Z-ids-in-code.json).

This runs at the start of the check step (pipeline/check_ids.py), which then judges these IDs
like the others. It asks the mirror node only about the candidates, and takes an answer that is
young enough from the table. A project whose candidates could not all be asked keeps the IDs of
the code that an earlier check gave it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from hackathon_memory.check import asking
from hackathon_memory.check.numbers import Numbers
from hackathon_memory.check.proof import counts_from_the_code, window_of
from hackathon_memory.db.code_ids import Candidate, CodeIdStore, Given
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.parse.hedera_ids import ACCOUNT
from hackathon_memory.pipeline.check_ids import (
    MAX_ERRORS_IN_A_ROW,
    NETWORKS_WHEN_OPEN,
    NodeIsAway,
)

# Most IDs of the code are accounts (103 of 128 in evals/results/20261023T230450Z-ids-in-code.json),
# so the ledger is asked about an account first: two questions in place of four. The order changes
# how many questions are asked, not the answer, which no kind that a text gave weighs.
ASK_ACCOUNT_FIRST = ACCOUNT


def _now() -> datetime:
    return datetime.now(UTC)


def give_code_ids(
    store: CodeIdStore,
    ledger: LedgerStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    max_age: timedelta,
    now: Callable[[], datetime] = _now,
    projects: set[int] | None = None,
) -> None:
    """Give each project, or each of `projects`, the IDs of its code that pass the rule, and count
    what was done."""
    by_project: dict[int, list[Candidate]] = {}
    for one in store.candidates():
        by_project.setdefault(one.project_id, []).append(one)
    numbers = Numbers(ledger.dated_numbers())
    errors_in_a_row = 0
    for project_id in sorted(set(by_project) | store.projects_with_code_ids()):
        if projects is not None and project_id not in projects:
            continue
        given: dict[tuple[str, str], Given] = {}
        finished = True
        for one in by_project.get(project_id, []):
            window = window_of(one.event_starts_at, one.event_ends_on)
            if window is None:
                run.counts["code_ids_without_an_event_window"] += 1
                continue
            for network in [one.network] if one.network else NETWORKS_WHEN_OPEN:
                mirror = mirrors.get(network)
                if mirror is None:
                    continue
                if not numbers.could_be_made_inside(one.entity_id, network, window):
                    run.counts["code_ids_ruled_out_by_their_number"] += 1
                    continue
                try:
                    facts = asking.facts_of(ledger, mirror, one.entity_id, ASK_ACCOUNT_FIRST,
                                            max_age=max_age, now=now,
                                            counts=run.counts)  # fmt: skip
                except MirrorError as error:
                    run.counts["errors_of_the_node"] += 1
                    run.problem(f"{one.entity_id} on {network} (code)", str(error))
                    finished = False
                    errors_in_a_row += 1
                    if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                        raise NodeIsAway(
                            f"the mirror node failed {errors_in_a_row} times in a row"
                        ) from None
                    continue
                errors_in_a_row = 0
                run.counts["code_ids_asked"] += 1
                if counts_from_the_code(facts, window):
                    given.setdefault((one.entity_id, network),
                                     Given(one.entity_id, network, one.path))  # fmt: skip
        if not finished:
            run.counts["projects_whose_code_ids_were_not_all_asked"] += 1
            continue
        if given:
            # The answers are in the table now, so an address that stands for a thing that the
            # collection names by its 0.0 ID shows (28 October 2026).
            repository = by_project[project_id][0].repository
            elsewhere = store.named_elsewhere([one.entity_id for one in given.values()], repository)
            run.counts["code_ids_named_elsewhere_in_another_form"] += len(
                [one for one in given.values() if one.entity_id in elsewhere]
            )
            given = {key: one for key, one in given.items() if one.entity_id not in elsewhere}
        store.replace(project_id, list(given.values()))
        run.counts["code_ids_given"] += len(given)
        run.counts["projects_with_code_ids"] += bool(given)
