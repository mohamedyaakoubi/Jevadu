"""How the mirror node pages the transactions of an account. Prints links and counts only.

The first look showed an empty list with a "next" link. This script follows the links a few steps
and prints each link without the id of the account, and how many transactions each answer holds.
It also tries a question with a time range, which is what the proof rule needs.

    .venv/Scripts/python.exe backlog/tools/mirror/probe_account_activity.py
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime

import psycopg
import requests

from hackathon_memory import __version__
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST = "https://testnet.mirrornode.hedera.com"
HEADERS = {"User-Agent": f"HackathonMemory-research/{__version__}"}

with psycopg.connect(Settings().database_conninfo()) as conn:
    (entity,) = conn.execute(
        "SELECT entity_id FROM hedera_ids WHERE network = 'testnet' AND said_kind = 'account' "
        "AND in_hashscan_link ORDER BY id LIMIT 1"
    ).fetchone()


def day(stamp: str) -> str:
    return datetime.fromtimestamp(float(stamp), UTC).strftime("%Y-%m-%d %H:%M")


def ask(path: str) -> dict:
    time.sleep(0.3)
    answer = requests.get(HOST + path, headers=HEADERS, timeout=20)
    body = answer.json()
    found = body.get("transactions", [])
    when = f", the first one at {day(found[0]['consensus_timestamp'])}" if found else ""
    print(f"  {answer.status_code}  {path.replace(entity, '<id>')}\n      -> {len(found)} "
          f"transaction(s){when}; next: {str((body.get('links') or {}).get('next')).replace(entity, '<id>')}")
    return body


info = requests.get(f"{HOST}/api/v1/accounts/{entity}?transactions=false", headers=HEADERS, timeout=20).json()
created = info["created_timestamp"]
print(f"the account was created at {day(created)}; now is {datetime.now(UTC):%Y-%m-%d %H:%M}")

print("newest first, following the links:")
path = f"/api/v1/transactions?account.id={entity}&limit=1&order=desc"
for _ in range(6):
    body = ask(path)
    path = (body.get("links") or {}).get("next")
    if body.get("transactions") or not path:
        break

print("oldest first, following the links:")
path = f"/api/v1/transactions?account.id={entity}&limit=1&order=asc"
for _ in range(4):
    body = ask(path)
    path = (body.get("links") or {}).get("next")
    if body.get("transactions") or not path:
        break

print("with a time range that starts at the creation:")
start = float(created)
for days in (1, 7, 30, 59, 61, 120):
    ask(
        f"/api/v1/transactions?account.id={entity}&limit=1&order=asc"
        f"&timestamp=gte:{start:.9f}&timestamp=lt:{start + days * 86400:.9f}"
    )
