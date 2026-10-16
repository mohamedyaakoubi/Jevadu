"""The public register (hedera/registry.py, design 9.2 to 9.5): the fixed record, its reading back,
"seen before" at any event, and the opening of the topic with its keys. No network: a stand-in
mirror node and stand-in writes. Every link, account and time is invented."""

from __future__ import annotations

import base64
import json
from datetime import date

import pytest
from hiero_sdk_python.crypto.private_key import PrivateKey
from pydantic import SecretStr

from hackathon_memory.hedera import registry
from hackathon_memory.hedera.keys import public_key_hex
from hackathon_memory.hedera.register import MessageSubmitted, RegisterError, TopicCreated
from hackathon_memory.settings import Settings

REPO = "https://github.com/sample-org/pebble-pay"
TOPIC = "0.0.7654321"
OPERATOR = "0.0.1234567"


class RegisterMirror:
    """Stands in for the mirror node of the register's topic."""

    network = "testnet"

    def __init__(self, key: PrivateKey | None = None, admin_key: object = None) -> None:
        self.messages: list[dict] = []
        self.key = key
        self.admin_key = admin_key
        self.asked: list[tuple] = []

    def add(self, payload: bytes, stamp: str = "1791585608.877804238") -> dict:
        message = {
            "sequence_number": len(self.messages) + 1,
            "consensus_timestamp": stamp,
            "message": base64.b64encode(payload).decode(),
            "payer_account_id": OPERATOR,
        }
        self.messages.append(message)
        return message

    def topic_messages_from(self, topic_id: str, first: int, *, limit: int = 100) -> list[dict]:
        self.asked.append(("from", topic_id, first, limit))
        return [m for m in self.messages if m["sequence_number"] >= first][:limit]

    def wait_for_message(self, topic_id: str, sequence_number: int, **_: object) -> dict:
        return self.messages[sequence_number - 1]

    def account(self, account: str) -> dict | None:
        if self.key is None or account != OPERATOR:
            return None
        return {
            "account": OPERATOR,
            "key": {"_type": "ECDSA_SECP256K1", "key": public_key_hex(self.key)},
        }

    def wait_for_topic(self, topic_id: str) -> dict:
        submit = {"_type": "ECDSA_SECP256K1", "key": public_key_hex(self.key)} if self.key else None
        return {"topic_id": topic_id, "admin_key": self.admin_key, "submit_key": submit}


def settings_with(key: PrivateKey, topic: str = "", network: str = "testnet") -> Settings:
    return Settings(
        _env_file=None,
        hedera_network=network,
        hedera_operator_id=OPERATOR,
        hedera_operator_key=SecretStr(key.to_string_der()),
        hedera_topic_id=topic,
    )


# ---------------------------------------------------------------------------- the record


def test_the_record_holds_the_event_and_fingerprints_only() -> None:
    code = registry.code_fingerprint(REPO)
    payload = registry.record("ethglobal.com/prague", code)
    assert json.loads(payload) == {"v": 1, "event": "ethglobal.com/prague", "code": code}
    assert b"github" not in payload and b"sample-org" not in payload  # no link in clear text
    assert len(payload) < registry.MAX_RECORD
    account = registry.account_fingerprint("0.0.4567890")
    days = registry.days_key(date(2026, 10, 1), date(2026, 10, 20))
    full = json.loads(registry.record(days, code, account))
    assert full == {"v": 1, "event": "days/2026-10-01/2026-10-20", "code": code, "account": account}


@pytest.mark.parametrize(
    ("event", "code"),
    [
        ("a free text event", "a" * 64),  # free text in the event
        ("ethglobal.com/prague", REPO),  # the link itself, not its fingerprint
        ("ethglobal.com/prague", "A" * 64),  # not the form of a fingerprint
    ],
)
def test_anything_but_the_fixed_form_is_refused(event: str, code: str) -> None:
    with pytest.raises(RegisterError):
        registry.record(event, code)


def test_a_typed_account_is_kept_only_in_its_form() -> None:
    assert registry.account_of(" 0.0.4567890 ") == "0.0.4567890"
    assert registry.account_of("my account") is None and registry.account_of("0.0.0") is None


# ---------------------------------------------------------------------------- reading back


def test_registrations_are_read_from_the_topic_page_by_page(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(registry, "PAGE", 2)
    mirror = RegisterMirror()
    code = registry.code_fingerprint(REPO)
    mirror.add(registry.record("ethglobal.com/prague", code))
    mirror.add(b'{"v":0,"event":"gate-a-proof","fp":"x"}')  # another form: not a registration
    mirror.add(b"not json")
    mirror.add(registry.record("days/2026-10-01/2026-10-20", code))
    found = registry.registrations(mirror, TOPIC)
    assert [(one.sequence_number, one.event) for one in found] == [
        (1, "ethglobal.com/prague"), (4, "days/2026-10-01/2026-10-20")]  # fmt: skip
    assert [asked[2] for asked in mirror.asked] == [1, 3, 5]  # from the first message on, by pages
    assert (
        found[0].link("testnet") == "https://hashscan.io/testnet/transaction/1791585608.877804238"
    )


def test_a_registration_is_written_once_and_read_back() -> None:
    mirror = RegisterMirror()
    payload = registry.record("ethglobal.com/prague", registry.code_fingerprint(REPO))
    written: list[bytes] = []

    def write(data: bytes) -> MessageSubmitted:
        written.append(data)
        message = mirror.add(data)
        return MessageSubmitted(TOPIC, message["sequence_number"], "0.0.1234567@1.2", "ab")

    found = registry.register_submission(write, mirror, TOPIC, payload)
    assert written == [payload] and found.sequence_number == 1
    assert found.registered_at.year == 2026


def test_another_record_read_back_is_a_failure() -> None:
    mirror = RegisterMirror()
    payload = registry.record("ethglobal.com/prague", registry.code_fingerprint(REPO))

    def write(data: bytes) -> MessageSubmitted:
        mirror.add(registry.record("ethglobal.com/other", registry.code_fingerprint(REPO)))
        return MessageSubmitted(TOPIC, 1, "0.0.1234567@1.2", "ab")

    with pytest.raises(RegisterError):
        registry.register_submission(write, mirror, TOPIC, payload)


# ---------------------------------------------------------------------------- the topic


def test_the_register_opens_with_no_admin_key_and_our_submit_key() -> None:
    key = PrivateKey.generate_ecdsa()  # made here, never saved, never printed
    mirror = RegisterMirror(key)
    made: list[dict] = []

    def create(client: object, submit_key: object, *, auto_renew: bool) -> TopicCreated:
        made.append({"submit_key": submit_key.to_string_raw(), "auto_renew": auto_renew})
        return TopicCreated(TOPIC, "0.0.1234567@1.2", auto_renew)

    topic = registry.open_register(settings_with(key), mirror, new_client=lambda *_: object(),
                                   create_topic=create)  # fmt: skip
    assert topic == TOPIC
    assert made == [{"submit_key": key.public_key().to_string_raw(), "auto_renew": True}]


def test_a_topic_with_an_admin_key_is_refused() -> None:
    key = PrivateKey.generate_ecdsa()
    mirror = RegisterMirror(key, admin_key={"_type": "ED25519", "key": "00" * 32})
    with pytest.raises(RegisterError, match="keys of design 9.5"):
        registry.open_register(
            settings_with(key), mirror, new_client=lambda *_: object(),
            create_topic=lambda *_, **__: TopicCreated(TOPIC, "t", True),
        )  # fmt: skip


def test_the_register_opens_once_on_the_test_network_only() -> None:
    key = PrivateKey.generate_ecdsa()
    with pytest.raises(RegisterError, match="open already"):
        registry.open_register(settings_with(key, topic=TOPIC), RegisterMirror(key))
    with pytest.raises(RegisterError, match="mainnet"):
        registry.open_register(settings_with(key, network="mainnet"), RegisterMirror(key))
    with pytest.raises(RegisterError, match="not the key"):
        registry.operator_key(settings_with(PrivateKey.generate_ecdsa()), RegisterMirror(key))


def test_a_writer_needs_an_open_register() -> None:
    key = PrivateKey.generate_ecdsa()
    with pytest.raises(RegisterError, match="HEDERA_TOPIC_ID is empty"):
        registry.writer(settings_with(key), RegisterMirror(key))
