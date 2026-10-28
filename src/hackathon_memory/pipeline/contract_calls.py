"""The step `contract_calls`: what the calls of each project's own contracts reached among
Hedera's system contracts (design 7.5, 28 October 2026).

For each own contract whose kind fits, in the time of the ledger story of each project that names
it, the first calls are read from the mirror node with their actions (check/system_calls.py), and
what they reached is kept (db/contract_calls.py). A second run reads only the contracts not read
in that time yet, and those read before that time was over. The mirror node is a public API,
asked one request at a time with a pause. Like "history", the step is not part of "all".

An error of the node does not stop the step: the contract is named in the run and left for the
next run. Five errors in a row stop the step, because then the node is away (design rule 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from hackathon_memory.check.system_calls import read_calls
from hackathon_memory.db.contract_calls import ContractCallStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.pipeline.check_ids import NodeIsAway

STEP = "contract_calls"
MAX_ERRORS_IN_A_ROW = 5


def _now() -> datetime:
    return datetime.now(UTC)


def read_contract_calls(
    store: ContractCallStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    limit: int | None = None,
    now: Callable[[], datetime] = _now,
    projects: set[int] | None = None,
) -> None:
    """Read the calls of every own contract that is to be read, at most `limit` of them; with
    `projects`, of these projects only."""
    todo = store.to_read(projects=projects)
    if limit is not None and len(todo) > limit:
        run.counts["left_for_later"] = len(todo) - limit
        todo = todo[:limit]
    errors_in_a_row = 0
    for item in todo:
        mirror = mirrors.get(item.network)
        if mirror is None:
            run.counts["on_a_network_that_is_not_asked"] += 1
            continue
        try:
            calls = read_calls(mirror, item.ledger_id, item.network, item.starts_at,
                               item.ends_at, entity_id=item.entity_id)  # fmt: skip
        except MirrorError as error:
            run.counts["errors_of_the_node"] += 1
            run.problem(f"{item.entity_id} on {item.network}", str(error))
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                failed = f"the mirror node failed {errors_in_a_row} times in a row"
                raise NodeIsAway(failed) from None
            continue
        errors_in_a_row = 0
        store.save(calls, now())
        run.counts["contracts_read"] += 1
        run.counts["calls_read"] += calls.read
        run.counts["contracts_cut"] += int(calls.cut)
        run.counts["contracts_that_reached_one"] += int(bool(calls.reached))


def contract_call_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Contracts read: {counts['contracts_read']}, with {counts['calls_read']:,} calls read. "
        f"Cut by the limit of calls: {counts['contracts_cut']}. Contracts whose calls reached "
        f"one of Hedera's system contracts: {counts['contracts_that_reached_one']}."
    ]
    if counts["left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: {counts['left_for_later']}.")
    if counts["errors_of_the_node"]:
        lines.append(f"Not read, because the mirror node failed: {counts['errors_of_the_node']}.")
    return lines
