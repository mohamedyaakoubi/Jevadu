"""The main network in the whole collection (design 7.6, screen S10): facts read by programs, never
by a model.

    python -m evals.mainnet

How many projects named a Hedera ID, have a Hedera proof, used an own ID on the test network, and
put an own ID on Hedera's main network; and what the own IDs of the last did there: their
transactions, the days with one, the fees that the network charged, in HBAR and in US dollars at
the network's own exchange rate of each hour, the HBAR that changed hands besides the fees, and the
accounts that paid. The view "Mainnet" counts in the same way, for the list on the screen
(search/mainnet.py). The transactions are those of the histories of the own IDs, with what the step
`mainnet` read about each; the file says how many have no detail yet.

It also counts what those transactions did (design 7.6, the step `mainnet_what`), in the words of
the ledger and of the projects' own code: the kind that a message gives itself, the function of a
call, the words of the tool for a deployment or a schedule that ran, else the kind of the
transaction; the networks that the messages name (CAIP-2); and the things that the accounts which
made the own IDs also made on the main network, by kind, with how many of those accounts were
followed and how many are services. These totals are summed over the projects.

It writes evals/results/<UTC time>-mainnet.json, in numbers, the IDs of the ledger and those words
only: a project is named by its site and its key there, its event by its site and its short name
in the address, never by a text of a page. The counts are those of the day the file was made.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.search import filters, mainnet, mainnet_path
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"


def _used(used: mainnet.Used) -> dict:
    return {
        "transactions": used.transactions,
        "failed": used.failed,
        "first": used.first.isoformat() if used.first else None,
        "last": used.last.isoformat() if used.last else None,
        "days": used.days,
        "with_detail": used.detailed,
        "fee_tinybars": used.fee,
        "fee_dollars": round(used.fee_dollars, 4),
        "moved_tinybars": used.moved,
        "moved_dollars": round(used.moved_dollars, 4),
        "without_rate": used.without_rate,
        "accounts_that_paid": len(used.payers),
    }


def _did(conninfo: str, project_id: int) -> dict:
    """What the transactions of a project's own IDs did, and what the accounts that made them
    also made, from the path of the window (search/mainnet_path.py)."""
    path = mainnet_path.path_of(conninfo, project_id)
    what: Counter[str] = Counter()
    made: Counter[str] = Counter()
    makers: Counter[str] = Counter()
    for step in path.steps if path else ():
        what[step.what or step.name or "unknown"] += step.count
    for one in path.made if path else ():
        makers[one.followed or "not read"] += 1
        made.update(dict(one.counts))
    return {"what": dict(what.most_common()),
            "networks_named": dict(path.networks) if path else {},
            "messages": path.messages if path else 0,
            "made_by_the_same_accounts": dict(sorted(made.items())),
            "accounts_that_made_its_ids": dict(sorted(makers.items()))}  # fmt: skip


def counts(conninfo: str, *, models: Sequence[str], version: str, now: datetime) -> dict:
    """The main network in the whole collection, in numbers and the IDs of the ledger."""
    found = mainnet.summary(conninfo, filters.facts(conninfo, models=models, version=version,
                                                    now=now))  # fmt: skip
    did = {one.project_id: _did(conninfo, one.project_id) for one in found.projects}
    keys = ("what", "networks_named", "made_by_the_same_accounts", "accounts_that_made_its_ids")
    totals: dict[str, Counter[str]] = {key: Counter() for key in keys}
    for one in did.values():
        for key, counter in totals.items():
            counter.update(one[key])
    return {
        "test": "mainnet",
        "made_on": now.date().isoformat(),
        "projects": found.total,
        "named_a_hedera_id": found.named,
        "hedera_proof": found.proven,
        "own_id_used_on_the_test_network": found.on_testnet,
        "transactions_on_the_test_network": found.testnet_transactions,
        "own_id_on_the_main_network": len(found.projects),
        "used_on_the_main_network_after_their_event": found.used_after,
        "on_the_main_network": _used(found.used),
        "what_they_did": {key: dict(counter.most_common()) for key, counter in totals.items()},
        "messages": sum(one["messages"] for one in did.values()),
        "projects_on_the_main_network": [
            {
                "site": one.page[0],
                "key": one.page[1],
                "event": {"site": one.event_page[0], "slug": one.event_page[1]},
                "hedera_prize": one.prize == "hedera_prize",
                "ids": [
                    {"id": own.ledger_id or own.entity_id, "kind": own.kind} for own in one.ids
                ],  # fmt: skip
                "services": list(one.services),
                "after_their_event": one.after,
                **_used(one.used),
                **did[one.project_id],
            }
            for one in found.projects
        ],
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    settings = Settings()
    now = datetime.now(UTC)
    found = counts(settings.database_conninfo(), models=settings.card_models(),
                   version=INSTRUCTIONS_VERSION, now=now)  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-mainnet.json"
    path.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    used = found["on_the_main_network"]
    print(f"{found['own_id_on_the_main_network']} of {found['projects']} projects put an own ID on "
          f"the main network: {used['transactions']:,} transactions, fees of "
          f"{used['fee_tinybars'] / 100_000_000:,.2f} HBAR (${used['fee_dollars']:,.2f}). "
          f"Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
