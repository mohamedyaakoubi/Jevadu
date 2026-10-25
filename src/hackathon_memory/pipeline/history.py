"""The step `history`: what each project's own Hedera IDs did on the ledger, over time.

Each own ID whose kind fits its page is read from the mirror node, whole, up to the limit of
check/history.py, and kept with every event, its Hedera service and what it was (db/history.py).
It feeds the ledger story, its first measure (evals/ledger_story) and the depth of use (design
7.5). A second run reads only the IDs that were not read yet; with --again, also those read
before the depth of use (25 October 2026), once. The step `refresh` reads a history on from its
newest event (read_histories_on). The mirror node is a public API, asked one request at a time
with a pause.

An error of the node does not stop the step: the ID is named in the run and left for the next
run. Five errors in a row stop the step, because then the node is away (design rule 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from hackathon_memory.check.history import read_history
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.pipeline.check_ids import NodeIsAway

STEP = "history"
MAX_ERRORS_IN_A_ROW = 5


def _now() -> datetime:
    return datetime.now(UTC)


def read_histories(
    store: HistoryStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    limit: int | None = None,
    now: Callable[[], datetime] = _now,
    again: bool = False,
    projects: set[int] | None = None,
) -> None:
    """Read the history of every own ID that was not read yet, at most `limit` of them; with
    `again`, also those read before the depth of use; with `projects`, of these only."""
    todo = store.ids_to_read(again=again, projects=projects)
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
            history = read_history(
                mirror, item.ledger_id or item.entity_id, item.kind, made_at=item.made_at
            )
        except MirrorError as error:
            run.counts["errors_of_the_node"] += 1
            run.problem(f"{item.entity_id} on {item.network}", str(error))
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                failed = f"the mirror node failed {errors_in_a_row} times in a row"
                raise NodeIsAway(failed) from None
            continue
        errors_in_a_row = 0
        store.save(item.entity_id, item.network, item.kind, history, now())
        run.counts["ids_read"] += 1
        run.counts["events"] += len(history.events)
        run.counts["ids_cut"] += int(history.cut)


def read_histories_on(
    store: HistoryStore,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    older_than: timedelta,
    limit: int | None = None,
    now: Callable[[], datetime] = _now,
    projects: set[int] | None = None,
) -> None:
    """Read on, from its newest event, every history read more than `older_than` ago (design
    7.3): only the transactions that came since are asked for, and kept with the others."""
    todo = store.ids_to_read_on(read_before=now() - older_than, projects=projects)
    if limit is not None and len(todo) > limit:
        run.counts["read_on_left_for_later"] = len(todo) - limit
        todo = todo[:limit]
    errors_in_a_row = 0
    for item, newest in todo:
        mirror = mirrors.get(item.network)
        if mirror is None:
            continue
        try:
            history = read_history(mirror, item.ledger_id or item.entity_id, item.kind,
                                   made_at=item.made_at, since=newest)  # fmt: skip
        except MirrorError as error:
            run.counts["errors_of_the_node"] += 1
            run.problem(f"{item.entity_id} on {item.network}", str(error))
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                failed = f"the mirror node failed {errors_in_a_row} times in a row"
                raise NodeIsAway(failed) from None
            continue
        errors_in_a_row = 0
        run.counts["histories_read_on"] += 1
        run.counts["events_new"] += store.read_on(item.entity_id, item.network, history, now())


def history_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Histories read: {counts['ids_read']}, with {counts['events']:,} events in all. "
        f"Cut by the limit of events: {counts['ids_cut']}."
    ]
    if counts["histories_read_on"]:
        lines.append(f"Histories read on from their newest event: {counts['histories_read_on']}, "
                     f"with {counts['events_new']:,} new events.")  # fmt: skip
    if counts["left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: {counts['left_for_later']}.")
    if counts["errors_of_the_node"]:
        lines.append(f"Not read, because the mirror node failed: {counts['errors_of_the_node']}.")
    return lines
