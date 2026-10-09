"""Gate A, proof 2: a topic is created on the test network with the keys of design 9.5, a small
message is posted, and the mirror node returns it.

    python -m proofs.hedera_write

It needs HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY in .env (design 15, step 1). It writes only
to the TEST network, and only a fixed record of version 0 (design rule 8: no free text).

What it checks, in order:

1. The account exists on the test network, and the private key in .env is the key of that account.
   (The public key on the ledger is compared with the public half of the private key. This catches
   a wrong id, a wrong key, and the Ed25519/ECDSA guess of the library, before anything is sent.)
2. A topic is created with NO admin key and ONE submit key (the operator's public key).
3. The mirror node confirms those keys: the admin key is null, the submit key is ours.
4. A record is posted. The mirror node returns the same bytes, from our account, with a time.
5. A negative control: a topic whose submit key belongs to someone else refuses our message.

The topic is a proof topic and not the register. The register is created in Phase F, so the
register holds no proof message. A message on a topic can never be deleted, which is why this
runs on the test network.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hiero_sdk_python.crypto.private_key import PrivateKey

from hackathon_memory.hedera import register
from hackathon_memory.hedera.keys import (
    OperatorKeyError,
    load_operator_key,
    matches_ledger_key,
    public_key_hex,
)
from hackathon_memory.hedera.mirror import (
    MirrorError,
    MirrorNode,
    decode_message,
    hashscan_topic,
    hashscan_transaction,
)
from hackathon_memory.hedera.register import RegisterError
from hackathon_memory.settings import Settings
from proofs.result import ProofResult

PROOF_TEXT = (
    "hackathon-memory gate-a proof 2026-10-09"  # fixed; the record holds only its fingerprint
)


def proof_record() -> bytes:
    """The fixed form of design 9.3: a version, an event and a fingerprint. Nothing else."""
    body = {"v": 0, "event": "gate-a-proof", "fp": hashlib.sha256(PROOF_TEXT.encode()).hexdigest()}
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


@dataclass
class Services:
    """What the proof talks to. The defaults are the real ones; the tests pass fakes."""

    mirror: MirrorNode
    new_client: Callable[..., object] = register.new_testnet_client
    create_topic: Callable[..., register.TopicCreated] = register.create_topic
    submit_message: Callable[..., register.MessageSubmitted] = register.submit_message
    stranger_key: Callable[[], PrivateKey] = field(
        default=lambda: PrivateKey.generate_ecdsa()  # made here, never saved, never printed
    )


def run(services: Services | None = None, settings: Settings | None = None) -> int:
    settings = settings or Settings()
    operator_id = settings.hedera_operator_id.strip()
    key_text = settings.hedera_operator_key.get_secret_value()
    if not operator_id or not key_text:
        print(
            "Blocked: HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY are empty in .env.\n"
            "Create a free test account at portal.hedera.com (design 15, step 1), then put the\n"
            "account id and the DER encoded private key in .env. Never paste them into a chat."
        )
        return 3

    result = ProofResult(proof="hedera-write")
    result.hide(key_text)
    result.does_not_prove = [
        "It writes to the test network only. The main network is not tested and costs real money.",
        "The record has the proof form (version 0). The real record of the register "
        "(design 9.3) comes with Phase F.",
        "The negative control shows that a submit key is enforced. It does not show that a "
        "stranger cannot find another way to post: that is the guarantee of the network itself.",
        "The test network can be reset. The ids in this file may stop existing.",
    ]
    try:
        register.require_testnet(settings.hedera_network)
    except RegisterError as error:
        result.check("the network is the test network", False, str(error))
        return result.finish()
    result.check("the network is the test network", True)

    services = services or Services(mirror=MirrorNode("testnet"))
    mirror = services.mirror

    # --- 1. the account and its key
    try:
        account = mirror.account(operator_id)
        result.check("the account exists on the test network", account is not None, operator_id)
        if account is None:
            return result.finish()
        balance = int((account.get("balance") or {}).get("balance", 0))
        result.measurements["balance_before_tinybar"] = balance
        result.check("the account has a balance to pay the fees", balance > 0, f"{balance} tinybar")

        ledger_key = account.get("key") or {}
        key = load_operator_key(key_text, ledger_key.get("_type"))
        # The library's repr() prints the raw key, the portal gives the DER form: hide both.
        result.hide(key_text, key.to_string_der(), key.to_string_raw())
    except (MirrorError, OperatorKeyError) as error:
        result.check("the account and its key can be read", False, str(error))
        return result.finish()
    belongs = matches_ledger_key(key, ledger_key)
    result.check(
        "the private key in .env is the key of this account",
        belongs,
        f"key type on the ledger: {ledger_key.get('_type')}",
    )
    if not belongs:
        return result.finish()
    result.measurements["key_type"] = ledger_key.get("_type")

    # --- 2. the topic
    client = None
    try:
        client = services.new_client(operator_id, key)
        try:
            created = services.create_topic(client, key.public_key(), auto_renew=True)
        except RegisterError as error:
            if error.status != register.AUTORENEW_NOT_ALLOWED:
                raise
            # The older rule of the network: no auto-renew account without an admin key.
            created = services.create_topic(client, key.public_key(), auto_renew=False)
        result.check(
            "a topic was created",
            True,
            f"{created.topic_id}; auto-renew account sent: {created.auto_renew_account_sent}",
        )
        result.measurements["topic_id"] = created.topic_id
        result.measurements["create_transaction_id"] = created.transaction_id
        result.measurements["auto_renew_account_sent"] = created.auto_renew_account_sent
        result.measurements["topic_link"] = hashscan_topic("testnet", created.topic_id)

        # --- 3. the keys, as the ledger shows them
        started = time.monotonic()
        topic = mirror.wait_for_topic(created.topic_id)
        result.measurements["seconds_until_the_mirror_node_had_the_topic"] = round(
            time.monotonic() - started, 1
        )
        result.check(
            "the ledger shows NO admin key (nobody can delete the topic or change its rules)",
            topic.get("admin_key") is None,
        )
        submit_key = topic.get("submit_key") or {}
        result.check(
            "the ledger shows our public key as the submit key",
            str(submit_key.get("key", "")).lower() == public_key_hex(key),
        )
        result.check("the topic is not deleted", topic.get("deleted") is False)

        # --- 4. the record
        payload = proof_record()
        result.check("the record fits in one message", len(payload) < 1024, f"{len(payload)} bytes")
        sent = services.submit_message(client, created.topic_id, payload)
        result.check(
            "the network accepted the message",
            sent.sequence_number == 1,
            f"sequence {sent.sequence_number}",
        )
        result.measurements["message_transaction_id"] = sent.transaction_id
        result.measurements["sequence_number"] = sent.sequence_number

        started = time.monotonic()
        message = mirror.wait_for_message(created.topic_id, sent.sequence_number)
        result.measurements["seconds_until_the_mirror_node_had_the_message"] = round(
            time.monotonic() - started, 1
        )
        result.check(
            "the mirror node returns the bytes that were posted",
            decode_message(message) == payload,
        )
        result.check(
            "the message was posted by our account",
            message.get("payer_account_id") == operator_id,
        )
        result.measurements["consensus_timestamp"] = message.get("consensus_timestamp")
        result.measurements["message_link"] = hashscan_transaction(
            "testnet", str(message.get("consensus_timestamp"))
        )

        # --- 5. the negative control
        stranger = services.stranger_key().public_key()
        guarded = services.create_topic(
            client, stranger, auto_renew=created.auto_renew_account_sent
        )
        refused, status = False, None
        try:
            services.submit_message(client, guarded.topic_id, payload)
        except RegisterError as error:
            refused, status = True, error.status
        result.check(
            "a topic whose submit key is someone else's refuses our message",
            refused,
            f"answer of the network: {status}",
        )
        result.measurements["control_topic_id"] = guarded.topic_id
        result.measurements["control_answer"] = status
    except (RegisterError, MirrorError) as error:
        result.check("the write to the test network worked", False, str(error))
    except Exception as error:  # noqa: BLE001  (an unexpected error is a result too)
        # The check scrubs the registered secrets from the message before it is saved.
        result.check(
            "the write to the test network worked", False, f"{type(error).__name__}: {error}"
        )
    finally:
        close = getattr(client, "close", None)
        if close:
            close()

    try:
        after = mirror.account(operator_id)
        if after:
            spent = balance - int((after.get("balance") or {}).get("balance", balance))
            result.measurements["balance_after_tinybar"] = balance - spent
            result.measurements["spent_tinybar_approximate"] = spent
    except MirrorError:
        pass
    return result.finish()


if __name__ == "__main__":
    sys.exit(run())
