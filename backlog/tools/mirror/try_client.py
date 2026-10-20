"""The mirror node client on the real test network. Prints times, counts and kinds only.

    .venv/Scripts/python.exe backlog/tools/mirror/try_client.py
"""

from __future__ import annotations

import sys

import psycopg

from hackathon_memory.hedera.mirror import MirrorNode, when
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
with psycopg.connect(Settings().database_conninfo()) as conn:
    ids = dict(
        conn.execute(
            "SELECT DISTINCT ON (said_kind) said_kind, entity_id FROM hedera_ids "
            "WHERE network = 'testnet' AND said_kind IS NOT NULL ORDER BY said_kind, in_hashscan_link DESC, id"
        ).fetchall()
    )

mirror = MirrorNode("testnet")


def day(stamp: str | None) -> str:
    return when(stamp).strftime("%Y-%m-%d %H:%M") if stamp else "none"


account = mirror.account(ids["account"])
print("account: created", day(account["created_timestamp"]), "deleted", account["deleted"])
last = mirror.account_transactions(ids["account"], newest_first=True)
print("  last transaction:", day(last[0]["consensus_timestamp"]) if last else "none",
      "| requests so far:", mirror.requests_made)
first = mirror.account_transactions(
    ids["account"], newest_first=False, since=when(account["created_timestamp"])
)
print("  first transaction:", day(first[0]["consensus_timestamp"]) if first else "none",
      "| keys of a transaction:", sorted(first[0]) if first else [])

topic = mirror.topic(ids["topic"])
print("topic: created", day(topic["created_timestamp"]), "deleted", topic["deleted"])
newest = mirror.topic_messages(ids["topic"], newest_first=True)
oldest = mirror.topic_messages(ids["topic"], newest_first=False)
print("  messages:", newest[0]["sequence_number"] if newest else 0,
      "| first", day(oldest[0]["consensus_timestamp"]) if oldest else "none",
      "| last", day(newest[0]["consensus_timestamp"]) if newest else "none",
      "| keys of a message:", sorted(newest[0]) if newest else [])

contract = mirror.contract(ids["contract"])
print("contract:", "found" if contract else "not found as a contract")
if contract:
    print("  created", day(contract["created_timestamp"]), "deleted", contract["deleted"])
    calls_new = mirror.contract_results(ids["contract"], newest_first=True)
    calls_old = mirror.contract_results(ids["contract"], newest_first=False)
    print("  first call", day(calls_old[0]["timestamp"]) if calls_old else "none",
          "| last call", day(calls_new[0]["timestamp"]) if calls_new else "none",
          "| keys of a call:", sorted(calls_new[0]) if calls_new else [])

token = mirror.token(ids["token"])
print("token:", "found" if token else "not found as a token")
if token:
    print("  created", day(token["created_timestamp"]), "| changed", day(token["modified_timestamp"]),
          "| type", token["type"], "| supply is zero:", token["total_supply"] == "0",
          "| deleted", token["deleted"])
print("requests in all:", mirror.requests_made)
