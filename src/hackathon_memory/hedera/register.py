"""Writing to Hedera: create the topic of the register, and post a record to it (design 9).

Design rule 8: only the fixed fingerprint record goes to the topic. A message can never be
deleted. So this module posts the bytes it is given and does nothing else with them, and it
refuses a record that does not fit in one message.

The topic has NO admin key and ONE submit key (design 9.5). Without an admin key nobody can
delete the register or change its rules, not even the maintainer. The submit key is the public key
of the tool's account, so only that account can post.

Two facts from hiero-sdk-python 0.2.10 and from docs.hedera.com:

* `TopicCreateTransaction` has no admin key unless `set_admin_key` is called. The tutorial of
  Hedera sets one. Ours must not.
* `freeze_with(client)` sets the auto-renew account to the payer when none is given. Hedera's
  create-topic page says that since network version 0.60 an auto-renew account needs no admin
  key, and that rent is not enforced for topics yet. Older protocol notes say the opposite
  (AUTORENEW_ACCOUNT_NOT_ALLOWED). So `create_topic` has a fallback that sends no auto-renew
  account, and the proof records which one the network accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from hiero_sdk_python.account.account_id import AccountId
from hiero_sdk_python.client.client import Client
from hiero_sdk_python.consensus.topic_create_transaction import TopicCreateTransaction
from hiero_sdk_python.consensus.topic_id import TopicId
from hiero_sdk_python.consensus.topic_message_submit_transaction import (
    TopicMessageSubmitTransaction,
)
from hiero_sdk_python.crypto.private_key import PrivateKey
from hiero_sdk_python.crypto.public_key import PublicKey
from hiero_sdk_python.exceptions import MaxAttemptsError, PrecheckError, ReceiptStatusError
from hiero_sdk_python.response_code import ResponseCode

REGISTER_MEMO = "Hackathon Memory register"  # a topic memo holds 100 bytes at most
MAX_RECORD_BYTES = 1024  # one message; a longer one is cut into pieces (design 9.3)

AUTORENEW_NOT_ALLOWED = "AUTORENEW_ACCOUNT_NOT_ALLOWED"


class RegisterError(Exception):
    """A write to the ledger was refused or failed. `status` is the network's code, if any."""

    def __init__(self, message: str, status: str | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class TopicCreated:
    topic_id: str
    transaction_id: str
    auto_renew_account_sent: bool


@dataclass(frozen=True)
class MessageSubmitted:
    topic_id: str
    sequence_number: int
    transaction_id: str
    running_hash: str


def require_testnet(network: str) -> None:
    """The register is on the test network in the first version (design 3.2).

    A write on the main network costs real money and can never be undone. It is not in the
    first version, and the maintainer decides first.
    """
    if network != "testnet":
        raise RegisterError(
            f"Writing on the {network} network is not allowed in the first version. "
            "Ask the maintainer."
        )


def new_testnet_client(account_id: str, key: PrivateKey) -> Client:
    client = Client.for_testnet()
    client.set_operator(AccountId.from_string(account_id), key)
    return client


def topic_create_transaction(
    submit_key: PublicKey, memo: str = REGISTER_MEMO
) -> TopicCreateTransaction:
    """The transaction of design 9.5: no admin key, one submit key."""
    if len(memo.encode("utf-8")) > 100:
        raise RegisterError("A topic memo holds 100 bytes at most.")
    return TopicCreateTransaction(memo=memo, submit_key=submit_key)


def message_transaction(topic_id: str, payload: bytes) -> TopicMessageSubmitTransaction:
    """A message of one piece. A record that needs more is a design error, not a case to handle."""
    if not payload:
        raise RegisterError("The record is empty.")
    if len(payload) > MAX_RECORD_BYTES:
        raise RegisterError(
            f"The record is {len(payload)} bytes. One message holds {MAX_RECORD_BYTES}. "
            "The register record must stay far below that (design 9.3)."
        )
    transaction = TopicMessageSubmitTransaction(
        topic_id=TopicId.from_string(topic_id), message=payload
    )
    if transaction.get_required_chunks() != 1:
        raise RegisterError("The record would be cut into several messages.")
    return transaction


def _freeze_without_auto_renew(transaction: TopicCreateTransaction, client: Client) -> None:
    """Freeze the way that does not give the payer as auto-renew account.

    `freeze_with(client)` would set the auto-renew account. `freeze()` is `freeze_with(None)`,
    so the transaction id and the nodes are set by hand first.
    """
    transaction.set_transaction_id(client.generate_transaction_id())
    transaction.set_node_account_ids(client.get_node_account_ids())
    transaction.freeze()


def _status_name(error: Exception) -> str | None:
    status = getattr(error, "status", None)
    try:
        return ResponseCode(status).name if status is not None else None
    except ValueError:
        return None


def create_topic(
    client: Client,
    submit_key: PublicKey,
    *,
    memo: str = REGISTER_MEMO,
    auto_renew: bool = True,
) -> TopicCreated:
    transaction = topic_create_transaction(submit_key, memo)
    if not auto_renew:
        _freeze_without_auto_renew(transaction, client)
    try:
        response = transaction.execute(client, wait_for_receipt=False)
        receipt = response.get_receipt(client, validate_status=True)
    except (PrecheckError, ReceiptStatusError, MaxAttemptsError) as error:
        name = _status_name(error)
        raise RegisterError(
            f"The network refused the new topic: {name or type(error).__name__}", name
        ) from None
    if receipt.topic_id is None:
        raise RegisterError("The network accepted the transaction but returned no topic id.")
    return TopicCreated(
        topic_id=str(receipt.topic_id),
        transaction_id=response.transaction_id.to_string(),
        auto_renew_account_sent=auto_renew,
    )


def _running_hash(receipt: object) -> bytes:
    """The running hash of the topic after this message.

    `receipt.topic_running_hash` is broken in hiero-sdk-python 0.2.10: it asks the protobuf
    whether a bytes field is "present", and a bytes field has no presence, so it raises
    ValueError every time. The first live run found this on 9 October 2026:
    the message was on the ledger, and the library failed when the receipt was read. So the
    protobuf is read directly.
    """
    proto = getattr(receipt, "_receipt_proto", None)
    if proto is not None:
        return bytes(proto.topicRunningHash)
    try:
        return receipt.topic_running_hash or b""  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        return b""


def submit_message(client: Client, topic_id: str, payload: bytes) -> MessageSubmitted:
    transaction = message_transaction(topic_id, payload)
    try:
        response = transaction.execute(client, wait_for_receipt=False)
        receipt = response.get_receipt(client, validate_status=True)
    except (PrecheckError, ReceiptStatusError, MaxAttemptsError) as error:
        name = _status_name(error)
        raise RegisterError(
            f"The network refused the message: {name or type(error).__name__}", name
        ) from None
    return MessageSubmitted(
        topic_id=topic_id,
        sequence_number=int(receipt.topic_sequence_number),
        transaction_id=response.transaction_id.to_string(),
        running_hash=_running_hash(receipt).hex(),
    )
