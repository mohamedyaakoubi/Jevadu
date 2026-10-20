"""What the mirror node answers for one id of each kind. Shapes only: key names and kinds.

The mirror node is a public API made for programs, so it needs no yes (design rule 17). The
ids come from the local database. For each id the script asks the places where it could live and
prints the answer's status, its key names and the kinds of their values. Times, yes/no values and
type words are printed as they are: they are facts of the public ledger. A name, a memo or a key
is printed by its length only.

    .venv/Scripts/python.exe backlog/tools/mirror/probe_shapes.py
"""

from __future__ import annotations

import sys
import time

import psycopg
import requests

from hackathon_memory import __version__
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://testnet.mirrornode.hedera.com/api/v1"
HEADERS = {"User-Agent": f"HackathonMemory-research/{__version__}"}
SHOWN = {
    "created_timestamp", "deleted", "type", "total_supply", "consensus_timestamp",
    "sequence_number", "timestamp", "modified_timestamp", "expiry_timestamp", "decimals",
    "initial_supply", "max_supply", "supply_type", "result", "name_of_kind",
}  # fmt: skip
PLACES = (
    "/accounts/{id}?limit=1",
    "/accounts/{id}?transactions=false",
    "/tokens/{id}",
    "/tokens/{id}/nfts?limit=1",
    "/topics/{id}",
    "/topics/{id}/messages?limit=1&order=desc",
    "/topics/{id}/messages?limit=1&order=asc",
    "/contracts/{id}",
    "/contracts/{id}/results?limit=1&order=desc",
    "/contracts/{id}/results?limit=1&order=asc",
    "/transactions?account.id={id}&limit=1&order=desc",
    "/transactions?account.id={id}&limit=1&order=asc",
)


def shape(value: object, depth: int = 0) -> object:
    if isinstance(value, dict):
        if depth >= 2:
            return f"<object with {len(value)} keys>"
        return {
            key: (item if key in SHOWN and not isinstance(item, dict | list) else shape(item, depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [f"list of {len(value)}"] + ([shape(value[0], depth + 1)] if value else [])
    if isinstance(value, str):
        return f"<text {len(value)}>"
    return value if isinstance(value, bool) or value is None else f"<{type(value).__name__}>"


with psycopg.connect(Settings().database_conninfo()) as conn:
    rows = conn.execute(
        "SELECT DISTINCT ON (said_kind) said_kind, entity_id FROM hedera_ids "
        "WHERE network = 'testnet' AND said_kind IS NOT NULL AND in_hashscan_link "
        "ORDER BY said_kind, id"
    ).fetchall()
    rows += conn.execute(
        "SELECT DISTINCT ON (said_kind) said_kind, entity_id FROM hedera_ids "
        "WHERE network = 'testnet' AND said_kind = 'token' ORDER BY said_kind, id"
    ).fetchall()

session = requests.Session()
for said_kind, entity in rows:
    print(f"===== an id that its page calls: {said_kind}")
    for place in PLACES:
        time.sleep(0.3)
        answer = session.get(BASE + place.format(id=entity), headers=HEADERS, timeout=20)
        line = f"{answer.status_code}  {place}"
        if answer.status_code == 200:
            line += f"\n      {shape(answer.json())}"
        elif answer.headers.get("content-type", "").startswith("application/json"):
            line += f"  {shape(answer.json())}"
        print("  " + line[:1500])
