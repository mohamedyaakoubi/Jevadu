"""The Hedera mirror node: a read-only copy of the ledger that anybody can ask for free.

Design 9.1 and 5.6: it is a public API made for programs, so it is not a "collector" and
needs no yes from the maintainer (design rule 17).

The addresses are the ones that hiero-sdk-python 0.2.10 uses (client/network.py). The shapes of
the answers were read from the real test network on 9 October 2026:

* topic:         {"topic_id", "admin_key": null | {"_type", "key"}, "submit_key": ..., "memo", ...}
* topic message: {"sequence_number", "message" (base64), "consensus_timestamp", "payer_account_id",
                  "running_hash", "topic_id", ...}
* account:       {"account", "key": {"_type": "ED25519" | "ECDSA_SECP256K1" | ..., "key": hex}, ...}
"""

from __future__ import annotations

import base64
import re
import time
from collections.abc import Callable

import requests

from hackathon_memory import __version__

MIRROR_URLS = {
    "testnet": "https://testnet.mirrornode.hedera.com",
    "previewnet": "https://previewnet.mirrornode.hedera.com",
    "mainnet": "https://mainnet-public.mirrornode.hedera.com",
}
_ENTITY_ID = re.compile(r"^\d{1,10}\.\d{1,10}\.\d{1,12}$")


class MirrorError(Exception):
    """The mirror node could not answer."""


def hashscan_topic(network: str, topic_id: str) -> str:
    return f"https://hashscan.io/{network}/topic/{topic_id}"


def hashscan_transaction(network: str, consensus_timestamp: str) -> str:
    return f"https://hashscan.io/{network}/transaction/{consensus_timestamp}"


def decode_message(message: dict) -> bytes:
    """The bytes that were posted. The mirror node gives them in base64."""
    return base64.b64decode(message["message"])


class MirrorNode:
    def __init__(
        self,
        network: str = "testnet",
        *,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if network not in MIRROR_URLS:
            raise MirrorError(f"Unknown network: {network}")
        self.network = network
        self.base = f"{MIRROR_URLS[network]}/api/v1"
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.clock = clock
        # No contact address is sent: the mirror node is a public API (design 5.6).
        self.headers = {"User-Agent": f"HackathonMemory-research/{__version__}"}

    def _get(self, path: str) -> dict | None:
        try:
            response = self.session.get(
                self.base + path, headers=self.headers, timeout=self.timeout
            )
        except requests.RequestException as error:
            raise MirrorError(f"mirror node unreachable ({type(error).__name__})") from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise MirrorError(f"mirror node answered {response.status_code} for {path}")
        return response.json()

    @staticmethod
    def _entity(entity_id: str) -> str:
        if not _ENTITY_ID.match(entity_id):
            raise MirrorError(f"not a Hedera id: {entity_id!r}")
        return entity_id

    def account(self, account_id: str) -> dict | None:
        return self._get(f"/accounts/{self._entity(account_id)}")

    def topic(self, topic_id: str) -> dict | None:
        return self._get(f"/topics/{self._entity(topic_id)}")

    def topic_message(self, topic_id: str, sequence_number: int) -> dict | None:
        return self._get(f"/topics/{self._entity(topic_id)}/messages/{int(sequence_number)}")

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
