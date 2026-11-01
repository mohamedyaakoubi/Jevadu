"""What a transaction on the main network did (check/mainnet_what.py): a message, a call of a
contract, a scheduled transaction, a transfer of tokens. Everything is invented."""

from __future__ import annotations

import base64
import json

from hiero_sdk_python.hapi.services.basic_types_pb2 import AccountAmount, AccountID
from hiero_sdk_python.hapi.services.schedulable_transaction_body_pb2 import (
    SchedulableTransactionBody,
)

from hackathon_memory.check.mainnet_what import (
    DEPLOYED,
    LIBRARY_SOURCE,
    call_of,
    functions_of,
    hbar_words,
    long_zero,
    message_of,
    names_from,
    network_of,
    scheduled_of,
    selector,
    token_words,
    transfer_what,
)

SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import {IERC20} from "./IERC20.sol";
enum Side { Buy, Sell }
struct Coin { string name; string symbol; address owner; uint supply; }
interface IPool { function swap(uint amount) external; }
contract Shop {
    /* function hidden(uint a) is in a comment */
    function launch(Coin memory coin, IPool pool) external returns (address) {}
    function trade(Side side, uint256[] calldata amounts, address payable to) public payable {}
}
"""


def message(content: object) -> bytes:
    return json.dumps(content).encode()


def test_a_message_says_what_it_records_and_which_networks_it_names() -> None:
    said = message_of(message({"event": "OrderFilled", "kind": "paid", "chainId": 8453,
                               "network": "hedera:mainnet", "amount": "5"}))  # fmt: skip
    assert said.what == "OrderFilled"  # the first key of ACTION_KEYS wins
    assert said.networks == ("eip155:8453", "hedera:mainnet")
    assert said.fields == ("amount", "chainId", "event", "kind", "network")
    assert message_of(message({"kind": "sold"})).what == "sold"
    assert message_of(b"plain words, not JSON") == message_of(message([1, 2]))
    assert message_of(b"\xff\xfe").what is None


def test_a_message_keeps_no_free_text_and_no_personal_data() -> None:
    said = message_of(message({"event": "Ana Silva paid ana@example.com for the third time",
                               "type": "x" * 60, "action": "Refund"}))  # fmt: skip
    assert said.what == "Refund"  # the free text and the long value are passed over
    assert message_of(message({"event": "a@b.c"})).what is None
    assert message_of(message({"event": "Ana Silva"})).what is None  # two words: maybe a name
    assert network_of(True) is None and network_of(0) is None and network_of("base") is None
    assert network_of("296") == "eip155:296" and network_of("eip155:84532") == "eip155:84532"


def test_the_functions_of_a_contract_come_from_its_own_code_then_from_a_library() -> None:
    functions = functions_of([("contracts/Shop.sol", SOURCE)])
    launch = selector("launch((string,string,address,uint256),address)")  # struct, interface
    trade = selector("trade(uint8,uint256[],address)")  # enum, array, address payable
    assert functions[launch] == ("launch", "contracts/Shop.sol")
    assert functions[trade] == ("trade", "contracts/Shop.sol")
    assert selector("hidden(uint256)") not in functions  # a comment declares nothing
    assert functions["0x3400288b"] == ("setPeer", LIBRARY_SOURCE)  # LayerZero's OApp
    assert selector("transfer(address,uint256)") == "0xa9059cbb"  # the known selector of ERC-20
    assert names_from(functions, [launch, "0x3400288b"]) == (
        "its own code (contracts/Shop.sol) and a common library")  # fmt: skip
    assert names_from(functions, ["0x12345678"]) is None


def test_a_call_is_named_by_its_function_or_by_its_selector() -> None:
    functions = functions_of([("contracts/Shop.sol", SOURCE)])
    data = selector("launch((string,string,address,uint256),address)") + "00" * 64
    made = {"created_contract_ids": ["0.0.9001"], "function_parameters": "0x6080"}
    assert call_of(made, {"0.0.9001"}, functions) == DEPLOYED
    assert call_of({"function_parameters": data}, {"0.0.9001"}, functions) == "launch"
    assert call_of({"function_parameters": "0xdeadbeef00"}, (), functions) == "call 0xdeadbeef"
    assert call_of({"function_parameters": "0x"}, (), functions) == "a call with no data"


def scheduled(memo: str, executed: str | None, *amounts: int) -> dict:
    body = SchedulableTransactionBody(memo="")
    for number, amount in enumerate(amounts, start=7001):
        body.cryptoTransfer.transfers.accountAmounts.append(
            AccountAmount(accountID=AccountID(accountNum=number), amount=amount))  # fmt: skip
    return {"memo": memo, "executed_timestamp": executed,
            "transaction_body": base64.b64encode(body.SerializeToString()).decode()}  # fmt: skip


def test_a_scheduled_transaction_is_read_with_what_it_holds_and_when_it_ran() -> None:
    ran = scheduled_of(scheduled("payout after the storm", "1780000000.000000001",
                                 -400_000_000, 400_000_000))  # fmt: skip
    assert (ran.memo, ran.what, ran.executed) == (
        "payout after the storm", "a transfer of 4 HBAR", "1780000000.000000001")  # fmt: skip
    waiting = scheduled_of(scheduled("", None, -150_000_000, 150_000_000))
    assert (waiting.memo, waiting.what, waiting.executed) == (None, "a transfer of 1.5 HBAR", None)
    assert scheduled_of({"transaction_body": "not base64!"}).what.startswith("a transaction that")


def test_tokens_and_accounts_in_few_words() -> None:
    assert token_words({"name": "Invented Index", "symbol": "INX"}) == "Invented Index (INX)"
    assert token_words({"name": "SAME", "symbol": "SAME"}) == "SAME"
    moved = {"token_transfers": [{"token_id": "0.0.731", "amount": 100},
                                 {"token_id": "0.0.731", "amount": -100}]}  # fmt: skip
    assert transfer_what(moved, {"0.0.731": "SAUCE"}) == "moved SAUCE"
    assert transfer_what({"transfers": []}, {}) is None
    assert hbar_words(400_000_000) == "4 HBAR" and hbar_words(12_345_678) == "0.12345678 HBAR"
    assert long_zero("0.0.9224969") == "0x00000000000000000000000000000000008cc309"
    assert long_zero("1.0.5") is None and long_zero("0.0.x") is None
