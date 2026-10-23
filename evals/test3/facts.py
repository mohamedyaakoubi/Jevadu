"""Test 3: what the mirror node says about each ID of the hand check, asked with plain HTTP.

    python -m evals.test3.facts

For each ID of data/evals/test3/answers.json, it asks the public mirror node of the ID's network,
or of the test network and the main network when the network is open, and keeps every answer in
data/evals/test3/mirror. It does not use the tool's code, so that the hand check does not lean on
what it checks. It prints, for each ID, what a person needs to judge its status (guideline.md):
the kind of thing, the day it was made, the first and the last activity, and whether it is empty.
The person writes the status into answers.json.

The mirror node is a public API made for programs (design rule 17). One request at a time, with a
pause; an answer kept from an earlier run is not asked again.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests

from hackathon_memory.settings import Settings

NODES = {
    "testnet": "https://testnet.mirrornode.hedera.com/api/v1",
    "mainnet": "https://mainnet-public.mirrornode.hedera.com/api/v1",
}
PAUSE = 0.3  # seconds between two requests
# A contract has an account: asked first. Schedules were added on 22 October 2026 (guideline.md).
KINDS = ("topics", "tokens", "contracts", "accounts", "schedules")


def moment(value: object) -> str | None:
    """A time of the mirror node (seconds.nanoseconds) as a day."""
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromtimestamp(float(value), tz=UTC).date().isoformat()


def summary(kind: str, thing: dict, first: dict | None, last: dict | None) -> dict:
    """What a person needs to judge an ID, from the answers about it."""
    made = moment(thing.get("created_timestamp") or thing.get("consensus_timestamp"))
    # A message or a transaction carries "consensus_timestamp"; a contract's call carries
    # "timestamp" (the mirror node's answers, read on 18 October 2026).
    times = [moment(one.get("consensus_timestamp") or one.get("timestamp"))
             for one in (first, last) if one]  # fmt: skip
    if kind == "schedules":  # a schedule acts once: when it runs ("executed_timestamp")
        times = [moment(thing.get("executed_timestamp"))] if thing.get("executed_timestamp") else []
    empty = {
        "topics": first is None,
        "tokens": str(thing.get("total_supply", "1")) == "0",
        "contracts": bool(thing.get("deleted")),
        "accounts": bool(thing.get("deleted")),
        "transactions": thing.get("result") != "SUCCESS",
        "schedules": bool(thing.get("deleted")) and not thing.get("executed_timestamp"),
    }[kind]
    return {"kind": kind.rstrip("s"), "made": made, "first_activity": times[0] if times else made,
            "last_activity": times[-1] if times else made, "empty": empty,
            "action": thing.get("name")}  # fmt: skip


def activity(kind: str, entity: str) -> list[str]:
    """The two paths that give the first and the last activity of a thing."""
    path = {"topics": f"topics/{entity}/messages", "contracts": f"contracts/{entity}/results",
            "accounts": f"transactions?account.id={entity}"}.get(kind)  # fmt: skip
    if path is None:
        return []
    join = "&" if "?" in path else "?"
    return [f"{path}{join}limit=1&order=asc", f"{path}{join}limit=1&order=desc"]


def ask_one(get: Callable[[str], dict | None], entity: str) -> dict | None:
    """The summary of one ID on one network, or None when the network does not know it."""
    if "-" in entity:  # a transaction
        found = get(f"transactions/{entity}")
        items = (found or {}).get("transactions") or []
        parent = next((one for one in items if not one.get("nonce")), items[0] if items else None)
        return summary("transactions", parent, None, None) if parent else None
    for kind in KINDS:
        thing = get(f"{kind}/{entity}")
        if thing is None:
            continue
        ends = []
        for path in activity(kind, entity):
            answer = get(path) or {}
            rows = answer.get("messages") or answer.get("results") or answer.get("transactions")
            ends.append(rows[0] if rows else None)
        first, last = (ends + [None, None])[:2]
        return summary(kind, thing, first, last)
    return None


def getter(network: str, folder: Path) -> Callable[[str], dict | None]:
    """A GET on the mirror node of a network that keeps every answer, and asks each path once."""
    session = requests.Session()
    session.headers["User-Agent"] = "hackathon-memory-test3/1.0"

    def get(path: str) -> dict | None:
        name = (
            folder / f"{network}_{path.replace('/', '_').replace('?', '_').replace('&', '_')}.json"
        )
        if name.exists():
            kept = json.loads(name.read_text(encoding="utf-8"))
            return kept.get("body")
        time.sleep(PAUSE)
        answer = session.get(f"{NODES[network]}/{path}", timeout=30)
        body = answer.json() if answer.status_code == 200 else None
        name.write_text(json.dumps({"status": answer.status_code, "body": body}) + "\n",
                        encoding="utf-8")  # fmt: skip
        return body

    return get


def main(argv: Sequence[str]) -> int:
    del argv
    folder = Path(Settings().data_dir) / "evals" / "test3"
    answers = json.loads((folder / "answers.json").read_text(encoding="utf-8"))
    mirror = folder / "mirror"
    mirror.mkdir(exist_ok=True)
    gets = {network: getter(network, mirror) for network in NODES}
    for page in answers:
        for one in page["ids"]:
            networks = [one["network"]] if one.get("network") in NODES else list(NODES)
            for network in networks:
                found = ask_one(gets[network], one["id"].lower())
                print(f"{page['project']} {one['where']} {one['id']} {network}: "
                      f"{json.dumps(found) if found else 'not found'}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
