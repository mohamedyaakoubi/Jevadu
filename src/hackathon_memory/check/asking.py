"""Ask the ledger about one id for the proof rule, or take a young enough answer from the table
(design 7.1 and 7.2).

The step that checks every project (pipeline/check_ids.py) and the check of one submission on the
website ask in the same way: the facts of an id on one network, kept in the table and asked again
after `max_age`, and the one more question of the proof rule when the rule needs it, kept for its
window. Each adds what it did to `counts`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta

from hackathon_memory.check.ledger import LedgerFacts, read_facts, was_used_inside
from hackathon_memory.check.proof import Window, needs_a_look_inside
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.hedera.mirror import MirrorNode


def facts_of(
    ledger: LedgerStore,
    mirror: MirrorNode,
    entity_id: str,
    said_kind: str | None,
    *,
    max_age: timedelta,
    now: Callable[[], datetime],
    counts: Counter[str],
) -> LedgerFacts:
    """The facts of an id on the network of `mirror`: from the table when young enough. With a
    `max_age` of nothing, no answer is young enough, whatever the clock says."""
    kept = ledger.facts(entity_id, mirror.network)
    if kept is not None and max_age and now() - kept.asked_at <= max_age:
        counts["answers_from_the_table"] += 1
        return kept
    facts = read_facts(mirror, entity_id, said_kind, now=now)
    ledger.save_facts(facts)
    counts["answers_from_the_node"] += 1
    return facts


def used_inside(
    ledger: LedgerStore,
    mirror: MirrorNode,
    facts: LedgerFacts,
    window: Window | None,
    *,
    now: Callable[[], datetime],
    counts: Counter[str],
    again: bool = False,
) -> bool | None:
    """The answer to the one more question of the proof rule, when the rule needs it: the kept
    one, unless it must be asked `again`."""
    if window is None or not needs_a_look_inside(facts, window):
        return None
    used = None if again else ledger.use(facts.entity_id, facts.network, window.start, window.end)
    if used is None:
        used = was_used_inside(mirror, facts, window.start, window.end)
        ledger.save_use(facts.entity_id, facts.network, window.start, window.end, used, now())
        counts["looks_inside_a_window"] += 1
    return used
