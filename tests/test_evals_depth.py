"""The first measure of the depth of use (evals/depth.py, design 13.9), on invented depths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

import evals.depth
from evals.depth import SIGNS, accounts_of, measure, recount
from hackathon_memory.check.depth import Depth
from hackathon_memory.parse.hedera_ids import TRANSACTION

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


def depth(did: int, others: int | None, days: int, *signs: str,
          setup: tuple[str, ...] = ()) -> Depth:  # fmt: skip
    return Depth((("messages to a topic", did),) if did else (), 0, 0, others, None, days, days,
                 0, 0, tuple(signs), True, None, total=did, setup=setup)  # fmt: skip


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


class Answers:
    """A stand-in for the requests session of the second counting: one answer of the mirror node."""

    def __init__(self, body: dict) -> None:
        self.status_code, self._body = 200, body

    def get(self, url: str, timeout: int) -> Answers:
        return self

    def json(self) -> dict:
        return self._body


def test_the_second_counting_takes_the_accounts_of_a_single_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An own ID that is one transaction: its payer and the accounts of its transfers took part,
    # as the card counts them (found by the run of 28 October 2026, 19 of 20).
    monkeypatch.setattr(evals.depth, "PAUSE", 0)
    read = datetime(2026, 10, 25, tzinfo=UTC)
    own = SimpleNamespace(entity_id=TRANSFER["transaction_id"], network="testnet",
                          kind=TRANSACTION, asked_at=read)  # fmt: skip
    card = SimpleNamespace(
        story=SimpleNamespace(ids=[own]),
        facts=SimpleNamespace(event_starts_at=datetime(2026, 3, 6, tzinfo=UTC),
                              event_ends_on=date(2026, 3, 8)),
    )  # fmt: skip
    session = Answers({"transactions": [TRANSFER]})
    took_part = {"0.0.7001", "0.0.7002", "0.0.7003"}  # not the node, not the account of fees
    assert recount(session, card, {}) == (1, took_part)  # type: ignore[arg-type]


def test_what_the_page_alone_does_not_say_is_counted() -> None:
    """For how many projects the ledger or the code shows something that the page alone does not
    say, in all and for each reason (29 October 2026)."""
    from hackathon_memory.check.history import CONSENSUS, TOKENS

    def story(seen: tuple = (), named: tuple = ()) -> SimpleNamespace:
        return SimpleNamespace(seen_not_named=seen, named_not_seen=named, lines=(),
                               contract_others=())  # fmt: skip

    def facts(code_only: bool = False) -> SimpleNamespace:
        return SimpleNamespace(proven_by_code_only=code_only, mainnet=False)

    quiet = SimpleNamespace(depth=depth(1, 0, 1), story=story(), facts=facts())
    said, both = (
        depth(4, 2, 3, "Its topic 0.0.6001 has no message."),
        story(((TOKENS, 5),), (CONSENSUS,)),
    )
    tells = SimpleNamespace(depth=said, story=both, facts=facts(True))
    late = SimpleNamespace(depth=depth(0, None, 0), story=None, facts=facts())
    found = [(1, "proof_found", quiet), (2, "proof_found", tells), (3, "dates_do_not_fit", late)]
    assert measure(found)["all"]["the_page_alone_misses"] == {
        "any": 2,
        "used_a_service_the_page_does_not_name": 1,
        "named_a_service_with_no_transaction": 1,
        "proof_only_in_the_code": 1,
        "a_sign_on_paper": 1,
        "the_page_id_does_not_fit": 1,
    }
    assert measure(found)["proof_found"]["the_page_alone_misses"]["any"] == 1


def test_the_three_reads_of_the_cards_are_counted() -> None:
    """The setup, the calls of the contracts and the main network (28 October 2026)."""
    from hackathon_memory.check.history import TOKENS
    from hackathon_memory.check.story import ServiceLine

    said = ("Its token 0.0.7001: an NFT collection with no supply limit; a royalty of 10% on each "
            "sale; keys for admin and supply.", "Its account 0.0.7201: an ECDSA key, the kind that "
            "EVM wallets use.")  # fmt: skip
    story = SimpleNamespace(lines=(ServiceLine(TOKENS, (), False, 0, from_contracts=34),),
                            contract_others=("random numbers in 2 calls",))  # fmt: skip
    first = SimpleNamespace(depth=depth(4, 2, 3, setup=said), story=story,
                            facts=SimpleNamespace(mainnet=True))  # fmt: skip
    second = SimpleNamespace(depth=depth(1, 0, 1), story=None, facts=SimpleNamespace(mainnet=False))
    every = measure([(1, "proof_found", first), (2, "proof_found", second)])["all"]
    assert (every["with_a_setup_said"], every["mainnet"]) == (1, 1)
    assert every["setup"]["token_with_custom_fees"] == 1 and every["setup"]["topic_with_a_fee"] == 0
    assert every["setup"]["account_with_an_ecdsa_key"] == 1
    assert every["contracts_reached_a_system_contract"] == 1
    assert every["reached"] == {TOKENS: 1, "random numbers": 1}
