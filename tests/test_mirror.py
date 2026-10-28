"""The mirror node client, against a fake. The shapes in the fake are the real ones."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
import requests

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.hedera.mirror import (
    MAX_LINKS,
    MIN_GAP_SECONDS,
    MIRROR_URLS,
    PAUSES_SECONDS,
    MirrorError,
    MirrorNode,
    decode_message,
    hashscan_topic,
    hashscan_transaction,
    stamp_of,
    when,
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
    "payer_account_id": "0.0.1235",
    "running_hash": "aa",
}


def test_the_addresses_are_the_ones_of_the_library() -> None:
    assert MIRROR_URLS["testnet"] == "https://testnet.mirrornode.hedera.com"
    assert MIRROR_URLS["mainnet"] == "https://mainnet-public.mirrornode.hedera.com"


def test_an_account_a_topic_and_a_message_are_read() -> None:
    mirror, site, _ = node(
        {
            f"{BASE}/accounts/0.0.1235": reply({"account": "0.0.1235", "key": KEY}),
            f"{BASE}/topics/0.0.5555": reply(TOPIC),
            f"{BASE}/topics/0.0.5555/messages/1": reply(MESSAGE),
        }
    )
    assert mirror.account("0.0.1235")["key"] == KEY
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


def test_a_server_error_is_a_mirror_error_after_the_pauses() -> None:
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": Reply(500, b"oops")})
    with pytest.raises(MirrorError, match="500"):
        mirror.topic("0.0.5555")
    assert fake_time.sleeps == list(PAUSES_SECONDS)
    assert mirror.requests_made == len(PAUSES_SECONDS) + 1


# --------------------------------------------------------------------- when the network fails


def test_a_broken_connection_is_asked_again_after_a_pause() -> None:
    dropped = requests.ConnectionError("the network went away")
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": [dropped, reply(TOPIC)]})
    assert mirror.topic("0.0.5555")["topic_id"] == "0.0.5555"
    assert fake_time.sleeps == [PAUSES_SECONDS[0]]
    assert mirror.requests_made == 2


def test_too_many_requests_and_a_busy_server_are_asked_again() -> None:
    answers = [Reply(429, b"slow down"), Reply(503, b"busy"), reply(TOPIC)]
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": answers})
    assert mirror.topic("0.0.5555")["topic_id"] == "0.0.5555"
    assert fake_time.sleeps == list(PAUSES_SECONDS[:2])


def test_a_longer_pause_that_the_node_asks_for_is_kept() -> None:
    answers = [Reply(429, b"", {"Retry-After": "30"}), reply(TOPIC)]
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": answers})
    mirror.topic("0.0.5555")
    assert fake_time.sleeps == [30.0]


def test_a_pause_of_more_than_five_minutes_is_not_waited_for() -> None:
    too_long = Reply(429, b"", {"Retry-After": "3600"})
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": too_long})
    with pytest.raises(MirrorError, match="3600 seconds"):
        mirror.topic("0.0.5555")
    assert fake_time.sleeps == []


def test_a_network_that_stays_away_fails_after_the_pauses() -> None:
    gone = requests.ConnectionError("no network")
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": [gone]})
    with pytest.raises(MirrorError, match=r"unreachable \(ConnectionError\)"):
        mirror.topic("0.0.5555")
    assert fake_time.sleeps == list(PAUSES_SECONDS)


def test_an_answer_that_will_not_change_is_not_asked_again() -> None:
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": Reply(400, b"bad request")})
    with pytest.raises(MirrorError, match="400"):
        mirror.topic("0.0.5555")
    assert (fake_time.sleeps, mirror.requests_made) == ([], 1)


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


# --------------------------------------------------------------------- the other kinds of thing

ADDRESS = "0x00000000000000000000000000000000002345ab"
TOKEN = {
    "token_id": "0.0.7777",
    "type": "FUNGIBLE_COMMON",
    "total_supply": "1000000",
    "created_timestamp": "1785016492.973922171",
    "modified_timestamp": "1785016492.973922171",
    "deleted": False,
}
CONTRACT = {
    "contract_id": "0.0.8888",
    "created_timestamp": "1724791853.156338494",
    "deleted": False,
    "evm_address": ADDRESS,
    "bytecode": "0x" + "60" * 40,
}


def test_a_token_and_a_contract_are_read_and_an_address_serves_as_an_id() -> None:
    mirror, site, _ = node(
        {
            f"{BASE}/tokens/0.0.7777": reply(TOKEN),
            f"{BASE}/contracts/0.0.8888": reply(CONTRACT),
            f"{BASE}/contracts/{ADDRESS}": reply(CONTRACT),
            f"{BASE}/accounts/{ADDRESS}": reply({"account": "0.0.8888"}),
        }
    )
    assert mirror.token("0.0.7777")["type"] == "FUNGIBLE_COMMON"
    assert mirror.contract("0.0.8888")["contract_id"] == "0.0.8888"
    assert mirror.contract(ADDRESS)["contract_id"] == "0.0.8888"
    assert mirror.account(ADDRESS)["account"] == "0.0.8888"
    assert mirror.token("0.0.9") is None
    assert mirror.requests_made == len(site.seen) == 5


def test_a_scheduled_transaction_is_read() -> None:
    answer = {"schedule_id": "0.0.7777", "consensus_timestamp": "1785016492.973922171",
              "executed_timestamp": None, "deleted": False}  # fmt: skip
    mirror, site, _ = node({f"{BASE}/schedules/0.0.7777": reply(answer)})
    assert mirror.schedule("0.0.7777")["schedule_id"] == "0.0.7777"
    assert mirror.schedule("0.0.9") is None
    assert len(site.seen) == 2


def test_an_address_is_not_an_id_of_a_token_or_a_topic() -> None:
    mirror, site, _ = node({})
    for ask in (mirror.token, mirror.topic):
        with pytest.raises(MirrorError, match="not a Hedera id"):
            ask(ADDRESS)
    with pytest.raises(MirrorError, match="not a Hedera id"):
        mirror.contract("0x1234")
    assert site.seen == []


# --------------------------------------------------------------------- what happened on a thing

SINCE = datetime(2026, 3, 1, tzinfo=UTC)
UNTIL = datetime(2026, 3, 21, tzinfo=UTC)
RANGE = "&timestamp=gte:1772323200.000000000&timestamp=lt:1774051200.000000000"


def test_a_time_of_the_mirror_node_is_read_and_written() -> None:
    assert when("1772323200.500000000") == datetime(2026, 3, 1, 0, 0, 0, 500000, tzinfo=UTC)
    assert stamp_of(SINCE) == "1772323200.000000000"
    with pytest.raises(MirrorError, match="time zone"):
        stamp_of(datetime(2026, 3, 1))  # noqa: DTZ001


def test_the_messages_of_a_topic_are_asked_from_one_end_and_inside_a_time() -> None:
    newest = f"{BASE}/topics/0.0.5555/messages?limit=1&order=desc"
    oldest = f"{BASE}/topics/0.0.5555/messages?limit=1&order=asc{RANGE}"
    mirror, site, _ = node(
        {
            newest: reply({"messages": [MESSAGE | {"sequence_number": 42}], "links": {}}),
            oldest: reply({"messages": [MESSAGE], "links": {"next": None}}),
        }
    )
    assert mirror.topic_messages("0.0.5555", newest_first=True)[0]["sequence_number"] == 42
    inside = mirror.topic_messages("0.0.5555", newest_first=False, since=SINCE, until=UNTIL)
    assert inside == [MESSAGE]
    assert site.urls == [newest, oldest]


def test_a_thing_of_another_kind_has_an_empty_list_and_not_an_error() -> None:
    # The real node answers 200 with an empty list for the messages of an account.
    empty = f"{BASE}/topics/0.0.1235/messages?limit=1&order=desc"
    mirror, _, _ = node({empty: reply({"messages": [], "links": {"next": None}})})
    assert mirror.topic_messages("0.0.1235", newest_first=True) == []
    assert mirror.topic_messages("0.0.9", newest_first=True) == []  # a 404
    assert mirror.contract_results("0.0.9", newest_first=False) == []


def test_the_calls_of_a_contract_are_asked_from_one_end() -> None:
    first = f"{BASE}/contracts/0.0.8888/results?limit=1&order=asc"
    last = f"{BASE}/contracts/{ADDRESS}/results?limit=2&order=desc{RANGE}"
    call = {"timestamp": "1724791900.000000001", "result": "SUCCESS"}
    mirror, site, _ = node(
        {first: reply({"results": [call]}), last: reply({"results": [call, call]})}
    )
    assert mirror.contract_results("0.0.8888", newest_first=False) == [call]
    in_range = mirror.contract_results(
        ADDRESS, newest_first=True, since=SINCE, until=UNTIL, limit=2
    )
    assert in_range == [call, call]
    assert site.urls == [first, last]


def transactions_page(found: list[dict], following: str | None) -> Reply:
    return reply({"transactions": found, "links": {"next": following}})


PAID = {"consensus_timestamp": "1775400511.765025000", "name": "CRYPTOTRANSFER"}
START = "/transactions?account.id=0.0.1235&limit=1&order=desc"
HOP_1 = f"{START}&timestamp=lt:1786499436.730000001"
HOP_2 = f"{START}&timestamp=lt:1781315436.730000001"
HOP_3 = f"{START}&timestamp=lt:1776131436.730000001"


def test_the_transactions_of_an_account_are_followed_through_the_empty_answers() -> None:
    # The real node searches 60 days at a time. An empty answer links to the 60 days before.
    mirror, site, _ = node(
        {
            BASE + START: transactions_page([], "/api/v1" + HOP_1),
            BASE + HOP_1: transactions_page([], "/api/v1" + HOP_2),
            BASE + HOP_2: transactions_page([], "/api/v1" + HOP_3),
            BASE + HOP_3: transactions_page([PAID], "/api/v1" + START + "&timestamp=lt:1.0"),
        }
    )
    assert mirror.account_transactions("0.0.1235", newest_first=True) == [PAID]
    assert site.urls == [BASE + START, BASE + HOP_1, BASE + HOP_2, BASE + HOP_3]


def test_the_links_are_not_followed_past_the_time_that_was_asked_for() -> None:
    since = datetime.fromtimestamp(1783000000, UTC)  # between the first and the second link
    ranged = f"{START}&timestamp=gte:1783000000.000000000"
    first_link = ranged + "&timestamp=lt:1786499436.700000000"
    second_link = ranged + "&timestamp=lt:1781315436.700000000"
    mirror, site, _ = node(
        {
            BASE + ranged: transactions_page([], "/api/v1" + first_link),
            BASE + first_link: transactions_page([], "/api/v1" + second_link),
        }
    )
    assert mirror.account_transactions("0.0.1235", newest_first=True, since=since) == []
    assert len(site.seen) == 2  # the link that starts before `since` was not asked


def test_an_account_with_nothing_at_all_ends_at_the_last_link() -> None:
    mirror, site, _ = node({BASE + START: transactions_page([], None)})
    assert mirror.account_transactions("0.0.1235", newest_first=True) == []
    assert len(site.seen) == 1


def test_only_a_fixed_number_of_links_is_followed() -> None:
    forever = transactions_page([], "/api/v1" + START)  # a node that always links to itself
    mirror, site, _ = node({BASE + START: forever})
    assert mirror.account_transactions("0.0.1235", newest_first=True, max_links=3) == []
    assert len(site.seen) == 4  # the first question and three links


def test_going_forward_in_time_the_links_stop_at_the_end_that_was_asked_for() -> None:
    until = datetime.fromtimestamp(1720000000, UTC)
    asc = "/transactions?account.id=0.0.1235&limit=1&order=asc&timestamp=lt:1720000000.000000000"
    first_link = asc + "&timestamp=gt:1717180520.600000000"
    second_link = asc + "&timestamp=gt:1722364520.600000000"
    mirror, site, _ = node(
        {
            BASE + asc: transactions_page([], "/api/v1" + first_link),
            BASE + first_link: transactions_page([], "/api/v1" + second_link),
        }
    )
    assert mirror.account_transactions("0.0.1235", newest_first=False, until=until) == []
    assert len(site.seen) == 2


# --------------------------------------------------------------------- the pace


def test_two_requests_in_a_row_keep_a_gap() -> None:
    mirror, _, fake_time = node({f"{BASE}/topics/0.0.5555": reply(TOPIC)})
    mirror.topic("0.0.5555")
    mirror.topic("0.0.5555")
    assert fake_time.sleeps == [MIN_GAP_SECONDS]
    fake_time.sleep(5)  # time passes by itself
    mirror.topic("0.0.5555")
    assert fake_time.sleeps == [MIN_GAP_SECONDS, 5]  # no wait was added


# --------------------------------------------------------------------- a whole history

HISTORY = "/transactions?account.id=0.0.1235&limit=100&order=asc"


def history_row(stamp: str) -> dict:
    return {"consensus_timestamp": stamp, "name": "CRYPTOTRANSFER"}


def test_a_whole_history_follows_its_links_through_the_empty_pages() -> None:
    first, second = history_row("1775400511.000000001"), history_row("1781400511.000000001")
    hop_1 = HISTORY + "&timestamp=gt:1775400511.000000001"
    hop_2 = HISTORY + "&timestamp=gt:1780584511.000000001"
    mirror, site, _ = node(
        {
            BASE + HISTORY: transactions_page([first], "/api/v1" + hop_1),
            BASE + hop_1: transactions_page([], "/api/v1" + hop_2),
            BASE + hop_2: transactions_page([second], None),
        }
    )
    assert mirror.account_history("0.0.1235", max_rows=2000) == ([first, second], False)
    assert site.urls == [BASE + HISTORY, BASE + hop_1, BASE + hop_2]


def test_a_whole_history_stops_at_the_limit_and_says_that_it_was_cut() -> None:
    rows = [history_row(f"17754005{n:02d}.000000001") for n in range(3)]
    mirror, site, _ = node({BASE + HISTORY: transactions_page(rows, "/api/v1" + HISTORY + "&x")})
    assert mirror.account_history("0.0.1235", max_rows=2) == (rows[:2], True)
    assert len(site.seen) == 1  # the link after the limit is not followed


def test_a_history_of_empty_pages_that_never_ends_is_cut() -> None:
    mirror, site, _ = node({BASE + HISTORY: transactions_page([], "/api/v1" + HISTORY)})
    assert mirror.account_history("0.0.1235", max_rows=10) == ([], True)
    assert len(site.seen) == MAX_LINKS + 1


def test_the_histories_of_a_topic_a_contract_and_nfts_are_asked_from_the_start() -> None:
    message, call, minted = (
        {"consensus_timestamp": "1.1"},
        {"timestamp": "2.2"},
        {"created_timestamp": "3.3"},
    )
    topic = f"{BASE}/topics/0.0.5555/messages?limit=100&order=asc"
    contract = f"{BASE}/contracts/{ADDRESS}/results?limit=100&order=asc"
    nfts = f"{BASE}/tokens/0.0.7777/nfts?limit=100&order=asc"
    mirror, site, _ = node(
        {
            topic: reply({"messages": [message], "links": {"next": None}}),
            contract: reply({"results": [call], "links": {"next": None}}),
            nfts: reply({"nfts": [minted], "links": {"next": None}}),
        }
    )
    assert mirror.topic_history("0.0.5555", max_rows=10) == ([message], False)
    assert mirror.contract_history(ADDRESS, max_rows=10) == ([call], False)
    assert mirror.nft_history("0.0.7777", max_rows=10) == ([minted], False)
    assert site.urls == [topic, contract, nfts]


def test_an_account_history_starts_at_the_moment_the_account_was_made() -> None:
    # With no start, the node searches the main network 60 days at a time from 2019, and the
    # empty pages before the account would reach the limit (measured on 23 October 2026).
    made = datetime.fromtimestamp(1762451892, UTC)
    path = BASE + HISTORY + "&timestamp=gte:1762451892.000000000"
    row = history_row("1762451900.000000001")
    mirror, site, _ = node({path: transactions_page([row], None)})
    assert mirror.account_history("0.0.1235", max_rows=10, since=made) == ([row], False)
    assert site.urls == [path]


def test_the_actions_of_a_contract_call_are_read_by_its_hash() -> None:
    # read on 28 October 2026: the actions of one call, a call to a system contract among them
    hashed = "0x" + "ab" * 32
    actions = {"actions": [{"call_type": "CALL", "recipient": "0.0.6092626"},
                           {"call_type": "SYSTEM", "recipient": "0.0.359"}]}  # fmt: skip
    mirror, site, _ = node({f"{BASE}/contracts/results/{hashed}/actions?limit=100": reply(actions)})
    recipients = [one["recipient"] for one in mirror.contract_actions(hashed)]
    assert recipients == ["0.0.6092626", "0.0.359"]
    with pytest.raises(MirrorError):
        mirror.contract_actions("0.0.6092626")  # not a hash: never sent
    assert len(site.seen) == 1
