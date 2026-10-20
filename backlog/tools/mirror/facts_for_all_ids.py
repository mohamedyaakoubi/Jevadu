"""The ledger facts for every id that the parsed pages give. Counts only: no id, no address.

An id with no network on its page is asked on the main network and on the test network. For each
id the script compares the day it was made with the start of the event of its project.

    .venv/Scripts/python.exe backlog/tools/mirror/facts_for_all_ids.py
"""

from __future__ import annotations

import sys
import time
from collections import Counter

import psycopg

from hackathon_memory.check.ledger import read_facts
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
with psycopg.connect(Settings().database_conninfo()) as conn:
    rows = conn.execute(
        "SELECT h.entity_id, h.network, h.said_kind, e.starts_at FROM hedera_ids h "
        "JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id ORDER BY h.id"
    ).fetchall()

mirrors = {"mainnet": MirrorNode("mainnet"), "testnet": MirrorNode("testnet")}
seen: dict[tuple[str, str, str | None], object] = {}
outcome: Counter[str] = Counter()
kinds: Counter[str] = Counter()
where: Counter[str] = Counter()
distance: Counter[str] = Counter()
errors: Counter[str] = Counter()
started = time.monotonic()

for entity, network, said_kind, event_start in rows:
    found_on = []
    for name in [network] if network else ["testnet", "mainnet"]:
        if name not in mirrors:
            outcome[f"a network that is not asked: {name}"] += 1
            continue
        key = (entity, name, said_kind)
        if key not in seen:
            try:
                seen[key] = read_facts(mirrors[name], entity, said_kind)
            except MirrorError as error:
                seen[key] = None
                errors[str(error)[:60].replace(entity, "<id>")] += 1
        facts = seen[key]
        if facts is None or not facts.found:
            continue
        found_on.append(name)
        kinds[
            f"the page says {said_kind}, the ledger says {facts.kind}"
            + (" (deleted)" if facts.deleted else "")
            + (" (empty)" if facts.empty else "")
        ] += 1
        if facts.created_at and event_start:
            days = (facts.created_at - event_start).days
            distance[
                f"on {name}: made "
                + (
                    "more than 30 days before the start of the event"
                    if days < -30
                    else "in the 30 days before the start"
                    if days < 0
                    else "in the 30 days after the start"
                    if days <= 30
                    else "more than 30 days after the start"
                )
            ] += 1
    said = f"the page names {network}" if network else "the page names no network"
    where[f"{said}: found on {' and '.join(found_on) or 'no network'}"] += 1


def show(title: str, counter: Counter) -> None:
    print(f"{title}:")
    for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:4}  {value}")


print(f"ids on the pages: {len(rows)}; questions: {len(seen)}; "
      f"requests: {sum(m.requests_made for m in mirrors.values())}; "
      f"seconds: {time.monotonic() - started:.0f}")
show("where an id was found", where)
show("what the page says and what the ledger says", kinds)
show("when the thing was made, against the start of the event", distance)
show("errors of the node", errors)
show("other", outcome)
