"""The sheet of Test 3 (evals/test3/sheet.py): the net that helps the eye. Invented texts."""

from __future__ import annotations

from evals.test3.sheet import caught


def test_the_net_catches_ids_transactions_addresses_and_links() -> None:
    address = "0x" + "a" * 40
    text = (f"Topic 0.0.12345 and the transfer 0.0.6000-1700000000-123, see "
            f"https://hashscan.io/testnet/topic/0.0.12345 and the contract {address}.")  # fmt: skip
    strings = [one["string"] for one in caught(text)]
    assert "0.0.12345" in strings and "0.0.6000-1700000000-123" in strings
    assert "https://hashscan.io/testnet/topic/0.0.12345" in strings and address in strings
    assert all("Topic" in one["around"] for one in caught(text)[:1])  # with the words around


def test_the_net_leaves_out_internet_addresses_and_versions_after_a_letter() -> None:
    strings = [one["string"] for one in caught("the node at 10.0.0.1 runs v1.2.3 of the tool")]
    assert strings == []


def test_an_id_has_one_spelling_and_the_best_status_counts() -> None:
    from evals.test3.run import best, key

    assert key(" 0.0.6000@1700000000.123 ") == "0.0.6000-1700000000-123000000"
    assert key("0xAbC") == "0xabc" and key("0.0.12345") == "0.0.12345"
    assert best(["not_found", "proof_found", None]) == "proof_found"
    assert best([None]) == "not checked"


def test_a_page_counts_what_was_found_invented_and_judged_the_same() -> None:
    from evals.test3.run import page_counts

    hand = {("page", "0.0.1001"): "proof_found", ("readme", "0.0.2002"): "not_found"}
    tool = {("page", "0.0.1001"): "dates_do_not_fit", ("readme", "0.0.3003"): "proof_found"}
    counts = page_counts(hand, tool)
    assert counts == {"found": (1, 2), "invented": (1, 2), "status": (0, 1)}


def test_three_checked_pages_get_a_planted_id_the_same_each_time() -> None:
    from evals.test3.run import planted_pages

    pages = [f"https://example.test/{n}" for n in range(10)]
    assert planted_pages(pages) == planted_pages(list(reversed(pages)))
    assert len(planted_pages(pages)) == 3 and planted_pages(pages[:2]) == sorted(pages[:2])


def stamp(year: int, month: int, day: int) -> str:
    from datetime import UTC, datetime

    return f"{datetime(year, month, day, 12, tzinfo=UTC).timestamp():.9f}"


def test_the_facts_of_a_topic_come_from_its_first_and_last_message() -> None:
    from evals.test3.facts import ask_one

    answers = {
        "topics/0.0.5005": {"created_timestamp": stamp(2026, 3, 6)},
        "topics/0.0.5005/messages?limit=1&order=asc": {
            "messages": [{"consensus_timestamp": stamp(2026, 3, 7)}]},
        "topics/0.0.5005/messages?limit=1&order=desc": {
            "messages": [{"consensus_timestamp": stamp(2026, 3, 8)}]},
    }  # fmt: skip
    found = ask_one(answers.get, "0.0.5005")
    assert found["kind"] == "topic" and found["made"] == "2026-03-06" and not found["empty"]
    assert (found["first_activity"], found["last_activity"]) == ("2026-03-07", "2026-03-08")
    assert ask_one({}.get, "0.0.5005") is None  # the network does not know it


def test_a_failed_transaction_is_empty() -> None:
    from evals.test3.facts import ask_one

    entity = "0.0.6000-1772798400-000000000"
    answers = {f"transactions/{entity}": {"transactions": [
        {"consensus_timestamp": stamp(2026, 3, 6), "result": "INVALID_SIGNATURE",
         "name": "TOKENMINT", "nonce": 0}]}}  # fmt: skip
    found = ask_one(answers.get, entity)
    assert found["kind"] == "transaction" and found["empty"] and found["action"] == "TOKENMINT"
