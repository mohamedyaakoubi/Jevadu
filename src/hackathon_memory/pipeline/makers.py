"""The step `makers`: who made each own thing of the projects (design 7.5, 29 October 2026).

For each own contract, topic, token and schedule that the ledger knows, the account that paid for
the transaction that created it is kept (db/makers.py): from its history when that holds the
moment of creation, which costs no request, or else from one question to the mirror node
(check/makers.py). A thing is asked once. The mirror node is a public API, asked one request at a
time with a pause. Like "history" and "contract_calls", the step is not part of "all".

An error of the node does not stop the step: the thing is named in the run and left for the next
run. Five errors in a row stop the step, because then the node is away (design rule 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from hackathon_memory.check.makers import ask_maker
from hackathon_memory.db.makers import MakerStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.pipeline.check_ids import NodeIsAway

STEP = "makers"
MAX_ERRORS_IN_A_ROW = 5


def _now() -> datetime:
    return datetime.now(UTC)


def read_makers(
    store: MakerStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    limit: int | None = None,
    now: Callable[[], datetime] = _now,
) -> None:
    """Keep who made every own thing not asked yet, at most `limit` of those that need the node."""
    asked = 0
    errors_in_a_row = 0
    for item in store.to_ask():
        if item.payer_read is not None:
            store.save(item.entity_id, item.network, item.payer_read, now())
            run.counts["makers_from_the_histories"] += 1
            continue
        if limit is not None and asked >= limit:
            run.counts["things_left_for_later"] += 1
            continue
        mirror = mirrors.get(item.network)
        if mirror is None:
            run.counts["on_a_network_that_is_not_asked"] += 1
            continue
        asked += 1
        try:
            made_by = ask_maker(mirror, item.ledger_id, item.made_at)
        except MirrorError as error:
            run.counts["errors_of_the_node"] += 1
            run.problem(f"{item.entity_id} on {item.network}", str(error))
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                failed = f"the mirror node failed {errors_in_a_row} times in a row"
                raise NodeIsAway(failed) from None
            continue
        errors_in_a_row = 0
        store.save(item.entity_id, item.network, made_by, now())
        run.counts["makers_from_the_node" if made_by else "makers_not_given"] += 1


def maker_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Makers kept: {counts['makers_from_the_histories']} from the histories already read, "
        f"{counts['makers_from_the_node']} from the mirror node. The node gave no account for "
        f"{counts['makers_not_given']}."
    ]
    if counts["things_left_for_later"]:
        later = counts["things_left_for_later"]
        lines.append(f"Left for a later run, because of the limit: {later}.")
    if counts["errors_of_the_node"]:
        lines.append(f"Not asked, because the mirror node failed: {counts['errors_of_the_node']}.")
    return lines
