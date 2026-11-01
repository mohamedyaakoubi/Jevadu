"""What a transaction of the main network cost and moved (check/mainnet.py). The shapes of the
answers are the mirror node's (read on 1 November 2026); every value is invented."""

from __future__ import annotations

from hackathon_memory.check.mainnet import TINYBARS, Detail, Rate, detail_of, hour_of, rate_of

STAMP = "1780000000.000000001"


def test_a_message_costs_its_fee_and_moves_nothing() -> None:
    message = {"consensus_timestamp": STAMP, "name": "CONSENSUSSUBMITMESSAGE", "result": "SUCCESS",
               "charged_tx_fee": 865_000, "transaction_id": "0.0.7001-1780000000-000000000",
               "node": "0.0.35",
               "transfers": [{"account": "0.0.802", "amount": 865_000},
                             {"account": "0.0.7001", "amount": -865_000}]}  # fmt: skip
    assert detail_of(message) == Detail(
        STAMP, "CONSENSUSSUBMITMESSAGE", True, 865_000, 0, ("0.0.7001",), 0
    )


def test_hbar_sent_to_another_account_is_moved_and_the_fee_is_not() -> None:
    sent = {"consensus_timestamp": STAMP, "name": "CRYPTOTRANSFER", "result": "SUCCESS",
            "charged_tx_fee": 100_000, "node": "0.0.3",
            "transfers": [{"account": "0.0.7001", "amount": -200_100_000},
                          {"account": "0.0.7002", "amount": 200_000_000},
                          {"account": "0.0.3", "amount": 10_000},
                          {"account": "0.0.98", "amount": 90_000}]}  # fmt: skip
    found = detail_of(sent)
    assert (found.fee, found.moved, found.paid_by) == (100_000, 2 * TINYBARS, ("0.0.7001",))


def test_a_reward_of_staking_is_not_moved_and_does_not_hide_who_paid() -> None:
    # 0.0.7001 got a reward of 600 tinybars and paid a fee of 100 in the same transaction
    rewarded = {"consensus_timestamp": STAMP, "name": "CRYPTOTRANSFER", "result": "SUCCESS",
                "charged_tx_fee": 100, "node": "0.0.3",
                "transfers": [{"account": "0.0.7001", "amount": 500},
                              {"account": "0.0.800", "amount": -600},
                              {"account": "0.0.98", "amount": 100}],
                "staking_reward_transfers": [{"account": "0.0.7001", "amount": 600}]}  # fmt: skip
    found = detail_of(rewarded)
    assert (found.moved, found.paid_by) == (0, ("0.0.7001",))


def test_a_call_through_an_evm_relay_is_paid_by_its_sender_not_by_the_relay() -> None:
    call = {"consensus_timestamp": STAMP, "name": "ETHEREUMTRANSACTION", "result": "SUCCESS",
            "charged_tx_fee": 59_000_000, "transaction_id": "0.0.9001-1780000000-000000001",
            "node": "0.0.4",
            "transfers": [{"account": "0.0.801", "amount": 59_000_000},
                          {"account": "0.0.7003", "amount": -59_000_000}]}  # fmt: skip
    assert detail_of(call).paid_by == ("0.0.7003",)


def test_tokens_and_nfts_are_counted_and_a_failure_is_kept() -> None:
    failed = {"consensus_timestamp": STAMP, "name": "CRYPTOTRANSFER",
              "result": "INSUFFICIENT_PAYER_BALANCE", "charged_tx_fee": 300,
              "token_transfers": [{"token_id": "0.0.8001", "account": "0.0.7001", "amount": -5},
                                  {"token_id": "0.0.8001", "account": "0.0.7002", "amount": 5}],
              "nft_transfers": [{"token_id": "0.0.8002", "serial_number": 1,
                                 "sender_account_id": "0.0.7001",
                                 "receiver_account_id": "0.0.7002"}]}  # fmt: skip
    found = detail_of(failed)
    assert (found.ok, found.tokens, found.fee) == (False, 2, 300)
    assert detail_of({"consensus_timestamp": STAMP}).ok is None  # the node did not say


def test_the_rate_of_the_network_turns_tinybars_into_dollars() -> None:
    answer = {"current_rate": {"cent_equivalent": 292_291, "hbar_equivalent": 30_000,
                               "expiration_time": 1_780_002_000}}  # fmt: skip
    rate = rate_of(answer)
    assert rate == Rate(292_291, 30_000)
    assert round(rate.dollars(865_932), 6) == 0.000844  # 0.00865932 HBAR at 9.74 cents
    assert rate.dollars(30_000 * TINYBARS) == 2_922.91
    assert rate_of({}) is None and rate_of(None) is None
    assert rate_of({"current_rate": {"cent_equivalent": 0, "hbar_equivalent": 30_000}}) is None


def test_one_rate_holds_for_each_hour() -> None:
    assert hour_of("1771517394.976887000") == hour_of("1771516800.000000000") == 1771516800 // 3600
    assert hour_of("1771520400.000000000") == hour_of("1771517394.976887000") + 1
