"""Signs of a life after the event, over the whole collection (design 13.11, 1 November 2026): what
a project that lived on after its hackathon, or moved elsewhere, would leave in public data, and
how many projects left it. An answer to "the projects that mattered were rebuilt elsewhere".

    python -m evals.afterlife

1. The code: the projects whose repository got a push N days or more after the last day of their
   event (N = 30, 90, 180, 365), among those whose event ended at least N days before the reading
   and whose repository's last push is known (GitHub, as the step refresh last read it). So a
   young event is never counted as quiet.
2. The test network: the projects whose own testnet IDs had an activity N days or more after the
   end of their event, among those whose own testnet IDs were ever used.
3. A new home: the repositories that GitHub now names at another address, and of these, under
   another owner.
4. The same keys on the main network: the accounts behind the projects' own testnet IDs (their own
   accounts, and the accounts that made their other IDs), how many have one simple key, how many
   of those keys are also a key of an account on Hedera's main network (by the key itself, and for
   an ECDSA key by the EVM address that it gives, as a wallet uses it on every network), and how
   many of those accounts made or used a contract, a topic or a token there after the event. Only
   numbers are kept: no account, no amount.
5. The makers on the main network: the accounts that made the projects' own mainnet IDs, as the
   step `mainnet_what` followed them, and how many made anything there after the event.

It writes evals/results/<UTC time>-afterlife.json. Part 4 asks the test network's and the main
network's mirror nodes about 2,000 times, one request at a time with a pause.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import psycopg

from hackathon_memory.db.history import OWN
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.hedera.signing import evm_address_of
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
DAYS = (30, 90, 180, 365)
# The transactions that make or use a contract, a topic or a token: what a project does.
BUILDING = frozenset({"CONTRACTCREATEINSTANCE", "CONTRACTCALL", "ETHEREUMTRANSACTION",
                      "CONSENSUSCREATETOPIC", "CONSENSUSSUBMITMESSAGE", "TOKENCREATION",
                      "TOKENMINT", "SCHEDULECREATE", "FILECREATE", "FILEAPPEND"})  # fmt: skip
SIMPLE = ("ED25519", "ECDSA_SECP256K1")

_PROJECTS = """
SELECT p.id, e.ends_on, e.starts_at, r.url, r.current_url, r.last_push_at,
       (SELECT max(f.last_activity_at) FROM hedera_ids h JOIN own USING (entity_id)
        JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = 'testnet' AND f.found
        WHERE h.project_id = p.id AND h.network = 'testnet'),
       (SELECT count(*) FROM hedera_ids h JOIN own USING (entity_id)
        JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = 'testnet' AND f.found
        WHERE h.project_id = p.id AND h.network = 'testnet' AND f.first_activity_at IS NOT NULL)
FROM projects p JOIN events e ON e.id = p.event_id
LEFT JOIN repositories r ON r.id = p.repository_id
"""
_ACCOUNTS = """
SELECT h.project_id, f.kind, h.entity_id, f.made_by, e.ends_on, e.starts_at
FROM hedera_ids h JOIN own USING (entity_id)
JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = 'testnet' AND f.found
JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id
WHERE h.network = 'testnet'
"""
_MAKERS = """
SELECT m.made_by, bool_or(t.made_at > e.ends_on + interval '1 day')
FROM mainnet_things m JOIN ledger_facts f ON f.network = 'mainnet'
     AND coalesce(f.ledger_id, f.entity_id) = m.entity_id
JOIN hedera_ids h ON h.entity_id = f.entity_id AND h.network = 'mainnet'
JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id
LEFT JOIN mainnet_things t ON t.made_by = m.made_by AND t.kind <> 'account'
WHERE m.made_by IS NOT NULL AND e.ends_on IS NOT NULL
GROUP BY m.made_by
"""


def end_of(ends_on: date | None, starts_at: datetime | None) -> datetime | None:
    """The end of the last day of an event; its start when its end is not known."""
    if ends_on is not None:
        return datetime.combine(ends_on, time.max, tzinfo=UTC)
    return starts_at


def share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def code_and_testnet(rows: Sequence[tuple], now: datetime) -> dict:
    """Parts 1 to 3, from the rows of _PROJECTS."""
    found: dict = {"projects": len(rows), "with_a_repository": sum(1 for row in rows if row[3])}
    for days in DAYS:
        old = [
            row for row in rows if (end := end_of(row[1], row[2])) and end <= now - timedelta(days)
        ]
        known = [row for row in old if row[3] and row[5]]
        pushed = [row for row in known if row[5] >= end_of(row[1], row[2]) + timedelta(days)]
        used = [row for row in old if row[7]]
        kept = [
            row for row in used if row[6] and row[6] >= end_of(row[1], row[2]) + timedelta(days)
        ]
        found[f"{days}_days"] = {
            "events_old_enough": len(old),
            "code_pushed": len(pushed), "repositories_with_a_known_push": len(known),
            "code_pushed_share": share(len(pushed), len(known)),
            "testnet_still_used": len(kept), "testnet_ever_used": len(used),
            "testnet_still_used_share": share(len(kept), len(used)),
        }  # fmt: skip
    moved = [row for row in rows if row[3] and row[4] and row[3].lower() != row[4].lower()]
    found["repositories_at_a_new_address"] = len(moved)
    found["repositories_under_another_owner"] = sum(
        1 for row in moved if row[3].lower().split("/")[3] != row[4].lower().split("/")[3]
    )
    return found


@dataclass(frozen=True)
class Behind:
    """An account behind the own testnet IDs of some projects, and the first end of their events."""

    account: str
    projects: frozenset[int]
    first_end: datetime | None


def accounts_behind(rows: Sequence[tuple]) -> list[Behind]:
    """The own testnet accounts and the makers of the own testnet IDs (the rows of _ACCOUNTS)."""
    projects: dict[str, set[int]] = {}
    ends: dict[str, list[datetime]] = {}
    for project_id, kind, entity_id, made_by, ends_on, starts_at in rows:
        for account in ((entity_id if kind == "account" else None), made_by):
            if account:
                projects.setdefault(account, set()).add(project_id)
                end = end_of(ends_on, starts_at)
                if end is not None:
                    ends.setdefault(account, []).append(end)
    return [Behind(account, frozenset(projects[account]),
                   min(ends[account]) if ends.get(account) else None)
            for account in sorted(projects)]  # fmt: skip


def same_keys(behind: Sequence[Behind], testnet: MirrorNode, mainnet: MirrorNode,
              progress: Callable[[int], None] = lambda _: None) -> dict:  # fmt: skip
    """Part 4: how many of these accounts have a simple key that is also a key on the main
    network, and how many of those accounts made or used a contract, a topic or a token there
    after the event."""
    simple = matched = built = not_read = 0
    projects_matched: set[int] = set()
    projects_built: set[int] = set()
    for number, one in enumerate(behind, start=1):
        progress(number)
        try:
            key = (testnet.account(one.account) or {}).get("key") or {}
            if key.get("_type") not in SIMPLE or not key.get("key"):
                continue
            simple += 1
            found = set(mainnet.accounts_with_key(str(key["key"])))
            address = evm_address_of(str(key["key"])) if key["_type"] == SIMPLE[1] else None
            if address:
                found.update(str(one_account) for one_account in [
                    (mainnet.account(address) or {}).get("account")] if one_account)  # fmt: skip
            if not found:
                continue
            matched += 1
            projects_matched |= one.projects
            since = one.first_end
            for account in sorted(found):
                rows, _cut = mainnet.account_history(account, max_rows=100, since=since)
                if any(row.get("name") in BUILDING for row in rows):
                    built += 1
                    projects_built |= one.projects
                    break
        except MirrorError:
            not_read += 1
    return {"accounts_behind_testnet_ids": len(behind),
            "projects_behind_them": len({p for one in behind for p in one.projects}),
            "with_one_simple_key": simple, "not_read": not_read,
            "key_also_on_the_main_network": matched,
            "projects_of_those_keys": len(projects_matched),
            "built_there_after_the_event": built,
            "projects_that_built_there_after_the_event": len(projects_built)}  # fmt: skip


def makers_after(rows: Sequence[tuple]) -> dict:
    """Part 5, from the rows of _MAKERS."""
    return {"accounts_that_made_own_mainnet_ids": len(rows),
            "made_something_after_the_event": sum(1 for _, after in rows if after)}  # fmt: skip


def counts(conninfo: str, testnet: MirrorNode, mainnet: MirrorNode, now: datetime,
           progress: Callable[[int], None] = lambda _: None) -> dict:  # fmt: skip
    with psycopg.connect(conninfo) as conn:
        projects = conn.execute(OWN + _PROJECTS).fetchall()  # noqa: S608
        accounts = conn.execute(OWN + _ACCOUNTS).fetchall()  # noqa: S608
        makers = conn.execute(_MAKERS).fetchall()
    return {"test": "afterlife", "made_on": now.date().isoformat(),
            "code_and_test_network": code_and_testnet(projects, now),
            "same_keys_on_the_main_network": same_keys(accounts_behind(accounts), testnet,
                                                       mainnet, progress),
            "makers_on_the_main_network": makers_after(makers)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    del argv
    settings = Settings()
    now = datetime.now(UTC)

    def progress(number: int) -> None:
        if number % 100 == 0:
            print(f"  {number} accounts read", flush=True)

    found = counts(settings.database_conninfo(), MirrorNode("testnet"), MirrorNode("mainnet"),
                   now, progress)  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-afterlife.json"
    path.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    code, keys = found["code_and_test_network"], found["same_keys_on_the_main_network"]
    print(f"30 days on: {code['30_days']['code_pushed_share']:.1%} of repositories pushed; a year "
          f"on: {code['365_days']['code_pushed_share']:.1%}. Keys also on the main network: "
          f"{keys['key_also_on_the_main_network']} of {keys['with_one_simple_key']}, built there "
          f"after the event: {keys['built_there_after_the_event']}. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
