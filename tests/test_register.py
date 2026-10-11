"""The topic of the register has no admin key and one submit key (design 9.5).

These tests build the real transactions of the library and look at the bytes that would be sent.
The network is replaced by stand-ins. The live write is the Gate A proof (proofs/hedera_write.py).
"""

from __future__ import annotations

import os

import pytest
from hiero_sdk_python.account.account_id import AccountId
from hiero_sdk_python.consensus.topic_create_transaction import TopicCreateTransaction
from hiero_sdk_python.consensus.topic_id import TopicId
from hiero_sdk_python.consensus.topic_message_submit_transaction import (
    TopicMessageSubmitTransaction,
)
from hiero_sdk_python.exceptions import MaxAttemptsError, PrecheckError, ReceiptStatusError
from hiero_sdk_python.hapi.services import basic_types_pb2, transaction_receipt_pb2
from hiero_sdk_python.response_code import ResponseCode
from hiero_sdk_python.transaction.transaction_id import TransactionId
from hiero_sdk_python.transaction.transaction_receipt import TransactionReceipt

from hackathon_memory.hedera import register
from hackathon_memory.hedera.keys import load_operator_key, public_key_hex
from hackathon_memory.hedera.register import (
    MAX_RECORD_BYTES,
    RegisterError,
    create_topic,
    message_transaction,
    require_testnet,
    submit_message,
    topic_create_transaction,
)

ECDSA_DER = "3030020100300706052b8104000a04220420"
OPERATOR = AccountId(0, 0, 1234)
NODE = AccountId(0, 0, 3)
TX_ID = "0.0.1234@1791566670.123456789"


def a_key():
    return load_operator_key(ECDSA_DER + os.urandom(32).hex())


class StubClient:
    """Just enough of a Client to freeze a transaction. It never touches a network."""

    operator_account_id = OPERATOR

    def generate_transaction_id(self) -> TransactionId:
        return TransactionId.generate(OPERATOR)

    def get_node_account_ids(self) -> list[AccountId]:
        return [NODE, AccountId(0, 0, 4)]


def body_of(transaction) -> object:
    """The protobuf body that would be signed and sent."""
    transaction.set_transaction_id(TransactionId.generate(OPERATOR))
    transaction.set_node_account_id(NODE)
    return transaction.build_transaction_body().consensusCreateTopic


# ------------------------------------------------------------------ the keys of the topic


def test_the_topic_has_no_admin_key_and_one_submit_key() -> None:
    key = a_key()
    transaction = topic_create_transaction(key.public_key())
    assert transaction.admin_key is None
    assert public_key_hex(key) == transaction.submit_key.to_string_raw().lower()

    body = body_of(transaction)
    assert not body.HasField("adminKey")  # nobody can delete the register or change its rules
    assert body.HasField("submitKey")  # only the tool's account can post
    assert body.memo == "Hackathon Memory register"


def test_no_other_key_is_set() -> None:
    body = body_of(topic_create_transaction(a_key().public_key()))
    assert not body.HasField("fee_schedule_key")
    assert len(body.fee_exempt_key_list) == 0
    assert len(body.custom_fees) == 0  # no fee for posting


def test_a_topic_memo_holds_100_bytes_at_most() -> None:
    topic_create_transaction(a_key().public_key(), "x" * 100)
    with pytest.raises(RegisterError, match="100 bytes"):
        topic_create_transaction(a_key().public_key(), "x" * 101)
    with pytest.raises(RegisterError):
        topic_create_transaction(a_key().public_key(), "é" * 51)  # 102 bytes


def test_the_library_gives_the_payer_as_auto_renew_account_unless_we_stop_it() -> None:
    """A trap of the library. If this test fails, the library changed: read its source again."""
    stub = StubClient()
    key = a_key().public_key()

    default = topic_create_transaction(key)
    default.set_node_account_ids(stub.get_node_account_ids())
    default.freeze_with(stub)
    assert default.build_transaction_body().consensusCreateTopic.HasField("autoRenewAccount")

    careful = topic_create_transaction(key)
    register._freeze_without_auto_renew(careful, stub)
    assert careful.auto_renew_account is None
    assert not careful.build_transaction_body().consensusCreateTopic.HasField("autoRenewAccount")
    assert not careful.build_transaction_body().consensusCreateTopic.HasField("adminKey")


# ------------------------------------------------------------------ the message


def test_a_message_of_one_piece_is_accepted() -> None:
    transaction = message_transaction("0.0.5555", b"x" * MAX_RECORD_BYTES)
    assert transaction.get_required_chunks() == 1
    assert str(transaction.topic_id) == "0.0.5555"


def test_a_message_that_needs_two_pieces_is_refused() -> None:
    with pytest.raises(RegisterError, match="1025 bytes"):
        message_transaction("0.0.5555", b"x" * (MAX_RECORD_BYTES + 1))


def test_an_empty_message_is_refused() -> None:
    with pytest.raises(RegisterError, match="empty"):
        message_transaction("0.0.5555", b"")


def test_the_library_cuts_a_long_message_at_1024_bytes() -> None:
    """The reason for the rule above: the library would split it into pieces."""
    long = TopicMessageSubmitTransaction(
        topic_id=TopicId.from_string("0.0.5555"), message=b"x" * 2000
    )
    assert long.get_required_chunks() == 2


def test_the_testnet_is_the_only_network_for_writing() -> None:
    require_testnet("testnet")
    for other in ("mainnet", "previewnet", "somewhere"):
        with pytest.raises(RegisterError, match="not allowed in the first version"):
            require_testnet(other)


# ------------------------------------------------------------------ the answers of the network


def real_receipt() -> TransactionReceipt:
    """The library's own receipt object, built from protobuf as the network would send it.

    A hand-made stand-in hid a bug of the library until the first live run.
    """
    proto = transaction_receipt_pb2.TransactionReceipt(
        topicSequenceNumber=7, topicRunningHash=bytes.fromhex("0a0b")
    )
    proto.topicID.CopyFrom(basic_types_pb2.TopicID(topicNum=5555))
    return TransactionReceipt(proto)


class FakeReceipt:
    """Kept as a name for the tests below: it now gives the real receipt."""

    def __new__(cls) -> TransactionReceipt:  # type: ignore[misc]
        return real_receipt()


class FakeResponse:
    transaction_id = TransactionId.from_string(TX_ID)

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.validated: bool | None = None

    def get_receipt(self, client: object, validate_status: bool = False) -> object:
        self.validated = validate_status
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def patch_execute(monkeypatch: pytest.MonkeyPatch, cls: type, outcome: object) -> list[dict]:
    calls: list[dict] = []

    def execute(self, client, timeout=None, wait_for_receipt=True, validate_status=False):  # noqa: ANN001, ARG001
        calls.append({"wait_for_receipt": wait_for_receipt})
        return FakeResponse(outcome)

    monkeypatch.setattr(cls, "execute", execute)
    return calls


def test_create_topic_returns_the_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_execute(monkeypatch, TopicCreateTransaction, FakeReceipt())
    created = create_topic(StubClient(), a_key().public_key())  # type: ignore[arg-type]
    assert created.topic_id == "0.0.5555"
    assert created.transaction_id == TX_ID
    assert created.auto_renew_account_sent is True
    assert calls == [{"wait_for_receipt": False}]  # the response is kept, for its transaction id


def test_create_topic_without_auto_renew_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_execute(monkeypatch, TopicCreateTransaction, FakeReceipt())
    created = create_topic(StubClient(), a_key().public_key(), auto_renew=False)  # type: ignore[arg-type]
    assert created.auto_renew_account_sent is False


def test_the_refusal_code_of_the_network_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = ReceiptStatusError(ResponseCode.AUTORENEW_ACCOUNT_NOT_ALLOWED, None, None)  # type: ignore[arg-type]
    patch_execute(monkeypatch, TopicCreateTransaction, refusal)
    with pytest.raises(RegisterError) as failure:
        create_topic(StubClient(), a_key().public_key())  # type: ignore[arg-type]
    assert failure.value.status == "AUTORENEW_ACCOUNT_NOT_ALLOWED"
    assert failure.value.status == register.AUTORENEW_NOT_ALLOWED


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PrecheckError(ResponseCode.INSUFFICIENT_PAYER_BALANCE), "INSUFFICIENT_PAYER_BALANCE"),
        (ReceiptStatusError(ResponseCode.INVALID_SIGNATURE, None, None), "INVALID_SIGNATURE"),  # type: ignore[arg-type]
        (MaxAttemptsError("gave up", "0.0.3"), None),
    ],
)
def test_every_failure_becomes_a_register_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: str | None
) -> None:
    patch_execute(monkeypatch, TopicMessageSubmitTransaction, error)
    with pytest.raises(RegisterError) as failure:
        submit_message(StubClient(), "0.0.5555", b'{"v":0}')  # type: ignore[arg-type]
    assert failure.value.status == status


def test_submit_message_returns_the_sequence_number_and_the_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_execute(monkeypatch, TopicMessageSubmitTransaction, FakeReceipt())
    sent = submit_message(StubClient(), "0.0.5555", b'{"v":0}')  # type: ignore[arg-type]
    assert sent.sequence_number == 7
    assert sent.running_hash == "0a0b"
    assert sent.transaction_id == TX_ID


def test_a_message_that_is_too_long_never_reaches_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = patch_execute(monkeypatch, TopicMessageSubmitTransaction, FakeReceipt())
    with pytest.raises(RegisterError):
        submit_message(StubClient(), "0.0.5555", b"x" * 5000)  # type: ignore[arg-type]
    assert calls == []


def test_the_library_cannot_read_the_running_hash_of_a_receipt() -> None:
    """The bug found by the first live run. If this test fails, the library was fixed: simplify
    `_running_hash` in register.py."""
    receipt = real_receipt()
    with pytest.raises(ValueError, match="presence"):
        receipt.topic_running_hash  # noqa: B018
    assert receipt.topic_sequence_number == 7  # the neighbouring property works


def test_our_code_reads_the_running_hash_from_the_protobuf() -> None:
    assert register._running_hash(real_receipt()) == bytes.fromhex("0a0b")
    assert register._running_hash(object()) == b""  # a receipt of another shape does not crash
