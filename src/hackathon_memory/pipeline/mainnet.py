"""The step `mainnet`: what each transaction of the projects on Hedera's main network cost and
moved (design 7.6, 1 November 2026).

The projects with the tag "Mainnet" (design 7.5) have own IDs on the main network, whose histories
the step `history` reads: each event of them is a moment of consensus, which names one transaction
of the main network. Each moment with no detail yet is asked of the main network's mirror node,
once, with the exchange rate that the network used for its fees in that hour (check/mainnet.py). A
later run asks only for the new moments; the step `refresh` runs it after the histories. The mirror
node is a public API, asked one request at a time with a pause.

An error of the node does not stop the step: the moment is named in the run and left for the next
run. Five errors in a row stop the step, because then the node is away (design rule 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from hackathon_memory.check.mainnet import Rate, detail_of, hour_of, rate_of
from hackathon_memory.db.mainnet import MainnetStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.pipeline.check_ids import NodeIsAway

STEP = "mainnet"
MAX_ERRORS_IN_A_ROW = 5


def _now() -> datetime:
    return datetime.now(UTC)


def read_mainnet(
    store: MainnetStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    limit: int | None = None,
    now: Callable[[], datetime] = _now,
    projects: set[int] | None = None,
) -> None:
    """Ask what each transaction of the own IDs on the main network cost and moved, for the
    moments with no detail yet, at most `limit` of them; with `projects`, of these only."""
    mirror = mirrors.get("mainnet")
    if mirror is None:
        return
    todo = store.moments_to_read(projects=projects)
    if limit is not None and len(todo) > limit:
        run.counts["mainnet_left_for_later"] = len(todo) - limit
        todo = todo[:limit]
    rates: dict[int, Rate | None] = {}
    errors_in_a_row = 0
    for stamp in todo:
        try:
            transaction = mirror.transaction_at(stamp)
            if transaction is not None and hour_of(stamp) not in rates:
                rates[hour_of(stamp)] = rate_of(mirror.exchange_rate(stamp))
        except MirrorError as error:
            run.counts["errors_of_the_node"] += 1
            run.problem(f"the transaction of {stamp} on the main network", str(error))
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                failed = f"the mirror node failed {errors_in_a_row} times in a row"
                raise NodeIsAway(failed) from None
            continue
        errors_in_a_row = 0
        if transaction is None:
            run.counts["mainnet_not_found"] += 1
            run.problem(f"the transaction of {stamp} on the main network",
                        "the mirror node has no transaction at this moment")  # fmt: skip
            continue
        rate = rates[hour_of(stamp)]
        store.save(detail_of(transaction), rate, now())
        run.counts["mainnet_read"] += 1
        run.counts["mainnet_without_rate"] += rate is None


def mainnet_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [f"Transactions on the main network read: {counts['mainnet_read']:,}."]
    if counts["mainnet_without_rate"]:
        lines.append(f"Read without the network's exchange rate: {counts['mainnet_without_rate']}.")
    if counts["mainnet_not_found"]:
        lines.append(f"Not found at their moment: {counts['mainnet_not_found']}.")
    if counts["mainnet_left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: "
                     f"{counts['mainnet_left_for_later']}.")  # fmt: skip
    if counts["errors_of_the_node"]:
        lines.append(f"Not read, because the mirror node failed: {counts['errors_of_the_node']}.")
    return lines
