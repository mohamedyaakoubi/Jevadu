"""The Hedera mirror node: a read-only copy of the ledger that anybody can ask for free.

Design 9.1 and 5.6: it is a public API made for programs, so it is not a "collector" and
needs no yes from the maintainer (design rule 17).

The addresses are the ones that hiero-sdk-python 0.2.10 uses (client/network.py). The shapes of
the answers were read from the real test network, on 9 October 2026 and again on 11 October:

* topic:         {"topic_id", "admin_key": null | {"_type", "key"}, "submit_key": ..., "memo",
                  "created_timestamp", "deleted", ...}
* topic message: {"sequence_number", "message" (base64), "consensus_timestamp", "payer_account_id",
                  "running_hash", "topic_id", ...}
* account:       {"account", "key": {"_type": "ED25519" | "ECDSA_SECP256K1" | ..., "key": hex},
                  "created_timestamp", "deleted", "evm_address", ...}. A contract answers here too.
* token:         {"token_id", "type": "FUNGIBLE_COMMON" | "NON_FUNGIBLE_UNIQUE", "total_supply",
                  "created_timestamp", "modified_timestamp", "deleted", "name", "symbol", ...}
* contract:      {"contract_id", "created_timestamp", "deleted", "evm_address", "bytecode", ...}
* schedule:      {"schedule_id", "consensus_timestamp" (made), "executed_timestamp" (null until
                  it runs), "creator_account_id", "payer_account_id", "deleted", ...}. Read on
                  22 October 2026.

A time is a text of seconds and nanoseconds: "1791566671.807617381".

Two things that only a real answer showed (11 October 2026):

* A list of another kind of thing is empty and not missing: the messages of an id that is not a
  topic come back as an empty list with the answer 200. So the thing itself is asked first.
* The transactions of an account are searched 60 days at a time. An answer with no transaction
  can still carry a link to the 60 days before. "Nothing here" is only known at the last link.

Hedera's own page says that the public node allows 50 requests a second for one address. This
client asks one thing at a time and at most five times a second.

A question is asked again after a pause (5, 15, then 45 seconds) when the network went away (a
change of Wi-Fi broke a run on 12 October 2026), when the node says "too many requests" (429),
or when one of its servers fails (500, 502, 503, 504). A longer pause that the node asks for
("Retry-After") is kept, up to five minutes. Only then does the question fail.
"""

from __future__ import annotations

import base64
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import requests

from hackathon_memory import __version__

MIRROR_URLS = {
    "testnet": "https://testnet.mirrornode.hedera.com",
    "previewnet": "https://previewnet.mirrornode.hedera.com",
    "mainnet": "https://mainnet-public.mirrornode.hedera.com",
}
# The shortest time between two requests of one client, in seconds.
MIN_GAP_SECONDS = 0.2
# The answers that are asked again after a pause, and the pauses, in seconds.
TRY_AGAIN_CODES = frozenset({429, 500, 502, 503, 504})
PAUSES_SECONDS = (5.0, 15.0, 45.0)
# A "Retry-After" that asks for more than this is not waited for: the question fails.
MAX_ASKED_PAUSE = 300.0
# How many links "to the 60 days before" are followed for the transactions of an account: 24
# links are about four years.
MAX_LINKS = 24

_ENTITY_ID = re.compile(r"^\d{1,10}\.\d{1,10}\.\d{1,12}$")
_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRANSACTION_ID = re.compile(r"^\d{1,10}\.\d{1,10}\.\d{1,12}-\d{1,11}-\d{1,9}$")
_BEFORE = re.compile(r"timestamp=lte?:(\d+\.\d+)")
_AFTER = re.compile(r"timestamp=gte?:(\d+\.\d+)")


class MirrorError(Exception):
    """The mirror node could not answer."""


def _asked_seconds(value: str | None) -> float:
    """The pause that a "Retry-After" asks for, in seconds. A date or nothing counts as 0."""
    try:
        return max(0.0, float(value)) if value else 0.0
    except ValueError:
        return 0.0


def hashscan_topic(network: str, topic_id: str) -> str:
    return f"https://hashscan.io/{network}/topic/{topic_id}"


def hashscan_transaction(network: str, consensus_timestamp: str) -> str:
    return f"https://hashscan.io/{network}/transaction/{consensus_timestamp}"


def decode_message(message: dict) -> bytes:
    """The bytes that were posted. The mirror node gives them in base64."""
    return base64.b64decode(message["message"])


def when(stamp: str) -> datetime:
    """A time of the mirror node ("seconds.nanoseconds") as a time with its zone."""
    return datetime.fromtimestamp(float(stamp), UTC)


def stamp_of(moment: datetime) -> str:
    """A time as the mirror node writes it. The moment must say its time zone."""
    if moment.tzinfo is None:
        raise MirrorError("a time for the mirror node must say its time zone")
    return f"{moment.timestamp():.9f}"


class MirrorNode:
    def __init__(
        self,
        network: str = "testnet",
        *,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_gap: float = MIN_GAP_SECONDS,
        pauses: Sequence[float] = PAUSES_SECONDS,
    ) -> None:
        if network not in MIRROR_URLS:
            raise MirrorError(f"Unknown network: {network}")
        self.network = network
        self.base = f"{MIRROR_URLS[network]}/api/v1"
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.clock = clock
        self.min_gap = min_gap
        self.pauses = tuple(pauses)
        self.requests_made = 0
        self._last_answer: float | None = None
        # No contact address is sent: the mirror node is a public API (design 5.6).
        self.headers = {"User-Agent": f"HackathonMemory-research/{__version__}"}

    def _get(self, path: str) -> dict | None:
        """The answer of the node, or None when it has no such thing. A broken connection, a 429
        and an error of a server are asked again after the pauses, then fail as a MirrorError."""
        for pause in (*self.pauses, None):
            if self._last_answer is not None:
                wait = self.min_gap - (self.clock() - self._last_answer)
                if wait > 0:
                    self.sleep(wait)
            asked = 0.0
            try:
                response = self.session.get(
                    self.base + path, headers=self.headers, timeout=self.timeout
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                problem = f"mirror node unreachable ({type(error).__name__})"
            except requests.RequestException as error:
                raise MirrorError(f"mirror node unreachable ({type(error).__name__})") from None
            else:
                if response.status_code == 404:
                    return None
                if response.status_code == 200:
                    return response.json()
                problem = f"mirror node answered {response.status_code} for {path}"
                if response.status_code not in TRY_AGAIN_CODES:
                    raise MirrorError(problem)
                asked = _asked_seconds(response.headers.get("Retry-After"))
            finally:
                self.requests_made += 1
                self._last_answer = self.clock()
            if pause is None:
                raise MirrorError(problem)
            if asked > MAX_ASKED_PAUSE:
                raise MirrorError(f"{problem}, with a pause of {asked:.0f} seconds asked")
            self.sleep(max(pause, asked))
        raise AssertionError("not reached: the last turn of the loop returns or raises")

    @staticmethod
    def _entity(entity_id: str) -> str:
        if not _ENTITY_ID.match(entity_id):
            raise MirrorError(f"not a Hedera id: {entity_id!r}")
        return entity_id

    @classmethod
    def _entity_or_address(cls, entity: str) -> str:
        return entity if _EVM_ADDRESS.match(entity) else cls._entity(entity)

    # ----------------------------------------------------------------- one thing

    def account(self, account: str) -> dict | None:
        """An account, by its id or by its EVM address. A contract answers here too."""
        return self._get(f"/accounts/{self._entity_or_address(account)}")

    def topic(self, topic_id: str) -> dict | None:
        return self._get(f"/topics/{self._entity(topic_id)}")

    def token(self, token_id: str) -> dict | None:
        return self._get(f"/tokens/{self._entity(token_id)}")

    def contract(self, contract: str) -> dict | None:
        """A contract, by its id or by its EVM address."""
        return self._get(f"/contracts/{self._entity_or_address(contract)}")

    def schedule(self, schedule_id: str) -> dict | None:
        """A scheduled transaction: a transaction that runs later, once enough keys signed it."""
        return self._get(f"/schedules/{self._entity(schedule_id)}")

    def transaction(self, transaction_id: str) -> dict | None:
        """One transaction, by its ID "0.0.12345-1700000000-123456789": the list "transactions",
        the parent first. Read on 18 October 2026: each item has "name" (the kind of action, such
        as CRYPTOTRANSFER), "result" (SUCCESS or the reason it failed) and "consensus_timestamp".
        The form with "@" is refused by the node with a 400."""
        if not _TRANSACTION_ID.match(transaction_id):
            raise MirrorError(f"not a transaction id: {transaction_id!r}")
        return self._get(f"/transactions/{transaction_id}")

    def topic_message(self, topic_id: str, sequence_number: int) -> dict | None:
        return self._get(f"/topics/{self._entity(topic_id)}/messages/{int(sequence_number)}")

    def topic_messages_from(self, topic_id: str, first: int, *, limit: int = 100) -> list[dict]:
        """The messages of a topic from the number `first` on, oldest first, at most `limit`.

        The filter is "gte": on 16 October 2026 the test network's node answered
        "sequencenumber=gt:0" with no message, and "sequencenumber=gte:1" with the first one.
        """
        path = (
            f"/topics/{self._entity(topic_id)}/messages?sequencenumber=gte:{int(first)}"
            f"&limit={int(limit)}&order=asc"
        )
        return (self._get(path) or {}).get("messages") or []

    # ----------------------------------------------------------------- what happened on it

    @staticmethod
    def _range(since: datetime | None, until: datetime | None) -> str:
        """The part of a question that says "from this moment on" and "before that moment"."""
        parts = []
        if since is not None:
            parts.append(f"&timestamp=gte:{stamp_of(since)}")
        if until is not None:
            parts.append(f"&timestamp=lt:{stamp_of(until)}")
        return "".join(parts)

    def topic_messages(
        self,
        topic_id: str,
        *,
        newest_first: bool,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1,
    ) -> list[dict]:
        """Messages of a topic, from one end. An id that is not a topic gives an empty list."""
        order = "desc" if newest_first else "asc"
        path = f"/topics/{self._entity(topic_id)}/messages?limit={int(limit)}&order={order}"
        return (self._get(path + self._range(since, until)) or {}).get("messages") or []

    def contract_results(
        self,
        contract: str,
        *,
        newest_first: bool,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1,
    ) -> list[dict]:
        """Calls of a contract, from one end. An id that is not a contract gives an empty list."""
        order = "desc" if newest_first else "asc"
        path = (
            f"/contracts/{self._entity_or_address(contract)}/results"
            f"?limit={int(limit)}&order={order}"
        )
        return (self._get(path + self._range(since, until)) or {}).get("results") or []

    def account_transactions(
        self,
        account_id: str,
        *,
        newest_first: bool,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1,
        max_links: int = MAX_LINKS,
    ) -> list[dict]:
        """Transactions of an account, from one end.

        The node searches 60 days at a time and gives a link to the next 60 days. The links are
        followed while an answer is empty, until one holds a transaction, until there is no link
        left, until a link leaves the time asked for, or until `max_links` links were followed.
        """
        order = "desc" if newest_first else "asc"
        path = (
            f"/transactions?account.id={self._entity(account_id)}&limit={int(limit)}"
            f"&order={order}" + self._range(since, until)
        )
        for _ in range(max_links + 1):
            body = self._get(path) or {}
            found = body.get("transactions") or []
            following = (body.get("links") or {}).get("next")
            if found or not following:
                return found
            if _leaves_the_range(following, newest_first, since, until):
                return []
            path = following.removeprefix("/api/v1")
        return []

    # ----------------------------------------------------------------- a whole history

    def _all(self, path: str, key: str, max_rows: int) -> tuple[list[dict], bool]:
        """Every row of a list that comes in pages, oldest first, at most `max_rows`. Returns the
        rows, and True when the list was cut: by `max_rows`, or by more than MAX_LINKS empty
        pages in a row (an account is searched 60 days at a time, see account_transactions)."""
        rows: list[dict] = []
        empty_in_a_row = 0
        while True:
            body = self._get(path) or {}
            found = body.get(key) or []
            rows += found
            if len(rows) >= max_rows:
                return rows[:max_rows], True
            empty_in_a_row = 0 if found else empty_in_a_row + 1
            following = (body.get("links") or {}).get("next")
            if not following:
                return rows, False
            if empty_in_a_row > MAX_LINKS:
                return rows, True
            path = following.removeprefix("/api/v1")

    def account_history(
        self, account_id: str, *, max_rows: int, since: datetime | None = None
    ) -> tuple[list[dict], bool]:
        """Every transaction of an account, oldest first (see _all). Give `since`, the moment the
        account was made: with no start, the node searches 60 days at a time from the start of
        its network (2019 on the main network), and the empty pages before the account reach the
        limit of _all first (measured on 23 October 2026)."""
        path = (
            f"/transactions?account.id={self._entity(account_id)}&limit=100&order=asc"
            + self._range(since, None)
        )
        return self._all(path, "transactions", max_rows)

    def topic_history(
        self, topic_id: str, *, max_rows: int, since: datetime | None = None
    ) -> tuple[list[dict], bool]:
        """Every message of a topic, oldest first, from `since` on when it is given (see _all)."""
        path = f"/topics/{self._entity(topic_id)}/messages?limit=100&order=asc"
        return self._all(path + self._range(since, None), "messages", max_rows)

    def contract_history(
        self, contract: str, *, max_rows: int, since: datetime | None = None
    ) -> tuple[list[dict], bool]:
        """Every call of a contract, oldest first, from `since` on when it is given (see _all).
        Read on 25 October 2026: the first result of a contract is its creation, whose
        "created_contract_ids" names the contract itself."""
        path = f"/contracts/{self._entity_or_address(contract)}/results?limit=100&order=asc"
        return self._all(path + self._range(since, None), "results", max_rows)

    def token_holders(self, token_id: str, *, max_rows: int) -> tuple[list[str], bool]:
        """The accounts that hold a token now, with a balance above zero, at most `max_rows`,
        and True when there are more. Read on 25 October 2026: /tokens/{id}/balances takes the
        filter account.balance=gt:0, and each row names its "account"."""
        path = f"/tokens/{self._entity(token_id)}/balances?account.balance=gt:0&limit=100"
        rows, cut = self._all(path, "balances", max_rows)
        return [str(row["account"]) for row in rows if row.get("account")], cut

    def nft_history(self, token_id: str, *, max_rows: int) -> tuple[list[dict], bool]:
        """Every NFT of a token, the first minted first (see _all). A fungible token has none."""
        return self._all(f"/tokens/{self._entity(token_id)}/nfts?limit=100&order=asc",
                         "nfts", max_rows)  # fmt: skip

    # ----------------------------------------------------------------- waiting

    def _wait(self, find: Callable[[], dict | None], timeout: float, interval: float) -> dict:
        """The mirror node is a few seconds behind the network. Ask until the answer exists."""
        started = self.clock()
        while True:
            found = find()
            if found is not None:
                return found
            if self.clock() - started >= timeout:
                raise MirrorError(f"nothing found on the mirror node after {timeout:.0f} seconds")
            self.sleep(interval)

    def wait_for_topic(self, topic_id: str, timeout: float = 60, interval: float = 2) -> dict:
        return self._wait(lambda: self.topic(topic_id), timeout, interval)

    def wait_for_message(
        self, topic_id: str, sequence_number: int, timeout: float = 60, interval: float = 2
    ) -> dict:
        return self._wait(lambda: self.topic_message(topic_id, sequence_number), timeout, interval)


def _leaves_the_range(
    link: str, newest_first: bool, since: datetime | None, until: datetime | None
) -> bool:
    """True if the link to the next 60 days starts outside the time that was asked for.

    Going back in time, the link says "before this moment". Going forward, it says "after this
    moment". A question with its own range carries that range in the link too, so the moment
    that moves is the lowest "before", or the highest "after".
    """
    before = [float(v) for v in _BEFORE.findall(link)]
    after = [float(v) for v in _AFTER.findall(link)]
    if newest_first:
        return bool(before) and since is not None and min(before) <= since.timestamp()
    return bool(after) and until is not None and max(after) >= until.timestamp()
