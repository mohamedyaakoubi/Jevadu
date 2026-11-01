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

It writes evals/results/<UTC time>-mainnet.json, in numbers and the IDs of the ledger only: a
project is named by its site and its key there, its event by its site and its short name in the
address, never by a text of a page. The counts are those of the day the file was made.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.search import filters, mainnet
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


def counts(conninfo: str, *, models: Sequence[str], version: str, now: datetime) -> dict:
    """The main network in the whole collection, in numbers and the IDs of the ledger."""
    found = mainnet.summary(conninfo, filters.facts(conninfo, models=models, version=version,
                                                    now=now))  # fmt: skip
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
