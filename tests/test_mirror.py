"""The mirror node client, against a fake. The shapes in the fake are the real ones."""

from __future__ import annotations

import base64
import json

import pytest

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.hedera.mirror import (
    MIRROR_URLS,
    MirrorError,
    MirrorNode,
    decode_message,
    hashscan_topic,
    hashscan_transaction,
)

BASE = "https://testnet.mirrornode.hedera.com/api/v1"
KEY = {"_type": "ECDSA_SECP256K1", "key": "02" + "ab" * 32}


def reply(body: dict, status: int = 200) -> Reply:
    return Reply(status, json.dumps(body).encode(), {"Content-Type": "application/json"})


def node(pages: dict[str, Reply]):
    site = FakeSite(pages)
    fake_time = FakeTime()
    mirror = MirrorNode(
        "testnet", session=session_for(site), sleep=fake_time.sleep, clock=fake_time.clock
    )
    return mirror, site, fake_time


TOPIC = {
    "topic_id": "0.0.5555",
    "admin_key": None,
    "submit_key": KEY,
    "memo": "Hackathon Memory register",
    "deleted": False,
    "created_timestamp": "1791566670.607615026",
}
MESSAGE = {
    "topic_id": "0.0.5555",
    "sequence_number": 1,
    "message": base64.b64encode(b'{"v":0}').decode(),
    "consensus_timestamp": "1791566671.807617381",
    "payer_account_id": "0.0.1234",
    "running_hash": "aa",
}


def test_the_addresses_are_the_ones_of_the_library() -> None:
    assert MIRROR_URLS["testnet"] == "https://testnet.mirrornode.hedera.com"
    assert MIRROR_URLS["mainnet"] == "https://mainnet-public.mirrornode.hedera.com"


def test_an_account_a_topic_and_a_message_are_read() -> None:
    mirror, site, _ = node(
        {
            f"{BASE}/accounts/0.0.1234": reply({"account": "0.0.1234", "key": KEY}),
            f"{BASE}/topics/0.0.5555": reply(TOPIC),
            f"{BASE}/topics/0.0.5555/messages/1": reply(MESSAGE),
        }
    )
    assert mirror.account("0.0.1234")["key"] == KEY
    topic = mirror.topic("0.0.5555")
    assert topic["admin_key"] is None
    assert topic["submit_key"] == KEY
    assert decode_message(mirror.topic_message("0.0.5555", 1)) == b'{"v":0}'
    assert len(site.seen) == 3


def test_a_missing_thing_is_none_and_not_an_error() -> None:
    mirror, _, _ = node({})
    assert mirror.account("0.0.9") is None
    assert mirror.topic("0.0.9") is None
    assert mirror.topic_message("0.0.9", 1) is None


def test_a_server_error_is_a_mirror_error() -> None:
    mirror, _, _ = node({f"{BASE}/topics/0.0.5555": Reply(500, b"oops")})
    with pytest.raises(MirrorError, match="500"):
        mirror.topic("0.0.5555")


@pytest.mark.parametrize("bad", ["", "0.0", "abc", "0.0.1/../../x", "0.0.1?x=1", "../0.0.1"])
def test_an_id_that_is_not_an_id_is_never_sent(bad: str) -> None:
    mirror, site, _ = node({})
    with pytest.raises(MirrorError, match="not a Hedera id"):
        mirror.topic(bad)
    assert site.seen == []


def test_it_waits_for_the_mirror_node_to_catch_up() -> None:
    # The mirror node is a few seconds behind the network: the first answers are 404.
    mirror, site, fake_time = node({})
    calls = {"n": 0}

    def find() -> dict | None:
        calls["n"] += 1
        return MESSAGE if calls["n"] >= 3 else None

    assert mirror._wait(find, timeout=60, interval=2) == MESSAGE
    assert fake_time.sleeps == [2, 2]
    assert site.seen == []


def test_it_gives_up_after_the_timeout() -> None:
    mirror, _, fake_time = node({})
    with pytest.raises(MirrorError, match="after 10 seconds"):
        mirror.wait_for_message("0.0.5555", 1, timeout=10, interval=2)
    assert sum(fake_time.sleeps) >= 10


def test_wait_for_topic_returns_when_it_exists() -> None:
    mirror, _, _ = node({f"{BASE}/topics/0.0.5555": reply(TOPIC)})
    assert mirror.wait_for_topic("0.0.5555")["topic_id"] == "0.0.5555"


def test_no_contact_address_is_sent_to_the_mirror_node() -> None:
    mirror, site, _ = node({f"{BASE}/topics/0.0.5555": reply(TOPIC)})
    mirror.topic("0.0.5555")
    agent = site.seen[0].headers["User-Agent"]
    assert agent.startswith("HackathonMemory-research/")
    assert "@" not in agent
    assert "From" not in site.seen[0].headers


def test_hashscan_links() -> None:
    assert hashscan_topic("testnet", "0.0.5555") == "https://hashscan.io/testnet/topic/0.0.5555"
    assert (
        hashscan_transaction("testnet", "1791566671.807617381")
        == "https://hashscan.io/testnet/transaction/1791566671.807617381"
    )


def test_an_unknown_network_is_refused() -> None:
    with pytest.raises(MirrorError, match="Unknown network"):
        MirrorNode("somewhere")
