"""The first measure of the depth of use (evals/depth.py, design 13.9), on invented depths."""

from __future__ import annotations

from dataclasses import dataclass

from evals.depth import SIGNS, accounts_of, measure
from hackathon_memory.check.depth import Depth

# A transfer by the invented account 0.0.7001, taken by the node 0.0.3: HBAR to the node and to
# the network's account of fees, and a token from 0.0.7002 to 0.0.7003.
TRANSFER = {
    "transaction_id": "0.0.7001-1772884790-000000001",
    "consensus_timestamp": "1772884800.000000001",
    "nonce": 0,
    "node": "0.0.3",
    "transfers": [
        {"account": "0.0.3", "amount": 1},
        {"account": "0.0.98", "amount": 2},
        {"account": "0.0.7001", "amount": -3},
    ],
    "token_transfers": [
        {"account": "0.0.7002", "token_id": "0.0.5001", "amount": -10},
        {"account": "0.0.7003", "token_id": "0.0.5001", "amount": 10},
    ],
}


@dataclass(frozen=True)
class Card:
    depth: Depth


def depth(did: int, others: int | None, days: int, *signs: str) -> Depth:
    return Depth((("messages to a topic", did),) if did else (), 0, 0, others, None, days, days,
                 0, 0, tuple(signs), True, None, total=did)  # fmt: skip


def test_the_counts_follow_the_depth_of_each_card() -> None:
    found = [
        (1, "proof_found", Card(depth(4, 2, 3))),
        (2, "proof_found", Card(depth(9, 0, 1, "Its topic 0.0.6001 has no message."))),
        (
            3,
            "not_found",
            Card(
                depth(0, None, 0, "Its code names a Hedera package, and calls no Hedera service.")
            ),
        ),
    ]
    result = measure(found)
    every, proven = result["all"], result["proof_found"]
    assert (every["projects"], every["with_transactions_in_the_time"]) == (3, 2)
    assert every["others_took_part"]["count"] == 1 and every["others_took_part"]["of"] == 2
    assert every["active_on_3_days_or_more"]["count"] == 1
    assert every["signs_on_paper"]["topic_with_no_message"] == 1
    assert every["signs_on_paper"]["package_with_no_call"] == 1
    assert proven["projects"] == 2 and proven["signs_on_paper"]["package_with_no_call"] == 0
    assert result["per_project"][1]["signs"] == ["topic_with_no_message"]
    assert [one["transactions"] for one in result["per_project"]] == [4, 9, 0]
    assert set(SIGNS) == set(every["signs_on_paper"])


def test_the_accounts_of_a_transaction_are_its_payer_and_its_transfers() -> None:
    # the network's account of fees is left out later, with the other accounts of the network
    assert accounts_of(TRANSFER) == {"0.0.7001", "0.0.98", "0.0.7002", "0.0.7003"}
    sent = {"sender_account_id": "0.0.7005", "receiver_account_id": "0.0.7006"}
    nft = {"transaction_id": "0.0.7004-1772884790-000000002", "node": "0.0.4",
           "nft_transfers": [sent]}  # fmt: skip
    assert accounts_of(nft) == {"0.0.7004", "0.0.7005", "0.0.7006"}
