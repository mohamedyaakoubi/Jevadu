"""The Hedera proof script, run against an in-memory stand-in for the ledger.

This tests the proof's own logic (its order, its checks, its result file, its handling of secrets).
It cannot show that the real network behaves the same: that is what the live run is for.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from hackathon_memory.hedera.keys import load_operator_key, public_key_hex
from hackathon_memory.hedera.register import MessageSubmitted, RegisterError, TopicCreated
from hackathon_memory.settings import Settings
from proofs import hedera_write
from proofs import result as result_module
from proofs.hedera_write import Services, proof_record

OPERATOR_ID = "0.0.1234"
ECDSA_DER = "3030020100300706052b8104000a04220420"


class Ledger:
    """Topics with keys, and messages with sequence numbers. In memory."""

    def __init__(self, operator_key_text: str, *, ledger_key_wrong: bool = False) -> None:
        key = load_operator_key(operator_key_text)
        self.operator_hex = public_key_hex(key)
        shown = (
            public_key_hex(load_operator_key(ECDSA_DER + os.urandom(32).hex()))
            if ledger_key_wrong
            else self.operator_hex
        )
        self.account_key = {"_type": "ECDSA_SECP256K1", "key": shown}
        self.topics: dict[str, dict] = {}
        self.messages: dict[tuple[str, int], bytes] = {}
        self.clients_made = 0
        self.refuse_auto_renew = False
        self.give_the_topic_an_admin_key = False
        self.accept_strangers = False
        self.alter_messages = False
        self.explode_on_submit: str | None = None
        self.auto_renew_calls: list[bool] = []

    # the mirror node
    def account(self, account_id: str) -> dict | None:
        if account_id != OPERATOR_ID:
            return None
        return {"account": account_id, "balance": {"balance": 500_000_000}, "key": self.account_key}

    def wait_for_topic(self, topic_id: str, **_: object) -> dict:
        topic = self.topics[topic_id]
        return {
            "topic_id": topic_id,
            "admin_key": {"_type": "ED25519", "key": "ab" * 32}
            if self.give_the_topic_an_admin_key
            else None,
            "submit_key": {"_type": "ECDSA_SECP256K1", "key": topic["submit_key"]},
            "deleted": False,
        }

    def wait_for_message(self, topic_id: str, sequence_number: int, **_: object) -> dict:
        payload = self.messages[(topic_id, sequence_number)]
        if self.alter_messages:
            payload = payload + b" "
        return {
            "message": base64.b64encode(payload).decode(),
            "payer_account_id": OPERATOR_ID,
            "consensus_timestamp": "1791566671.807617381",
        }

    # the library
    def new_client(self, account_id: str, key: object) -> object:
        self.clients_made += 1
        return type("Client", (), {"close": lambda self: None})()

    def create_topic(
        self, client: object, submit_key: object, *, auto_renew: bool = True
    ) -> TopicCreated:
        self.auto_renew_calls.append(auto_renew)
        if auto_renew and self.refuse_auto_renew:
            raise RegisterError("refused", "AUTORENEW_ACCOUNT_NOT_ALLOWED")
        topic_id = f"0.0.{5000 + len(self.topics)}"
        self.topics[topic_id] = {"submit_key": submit_key.to_string_raw().lower()}
        return TopicCreated(topic_id, f"{OPERATOR_ID}@1791566670.1", auto_renew)

    def submit_message(self, client: object, topic_id: str, payload: bytes) -> MessageSubmitted:
        if self.explode_on_submit:
            raise RuntimeError(self.explode_on_submit)
        if self.topics[topic_id]["submit_key"] != self.operator_hex and not self.accept_strangers:
            raise RegisterError("refused", "INVALID_SIGNATURE")
        sequence = 1 + sum(1 for (t, _) in self.messages if t == topic_id)
        self.messages[(topic_id, sequence)] = payload
        return MessageSubmitted(topic_id, sequence, f"{OPERATOR_ID}@1791566671.2", "0a0b")


@pytest.fixture
def results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "proofs" / "results"
    monkeypatch.setattr(result_module, "RESULTS_DIR", folder)
    return folder


def setup(**options: bool):
    key_text = ECDSA_DER + os.urandom(32).hex()
    ledger = Ledger(key_text, ledger_key_wrong=options.pop("ledger_key_wrong", False))
    for name, value in options.items():
        setattr(ledger, name, value)
    services = Services(
        mirror=ledger,  # type: ignore[arg-type]
        new_client=ledger.new_client,
        create_topic=ledger.create_topic,
        submit_message=ledger.submit_message,
    )
    settings = Settings(
        _env_file=None,
        hedera_network="testnet",
        hedera_operator_id=OPERATOR_ID,
        hedera_operator_key=key_text,
    )
    return ledger, services, settings, key_text


def saved(results_dir: Path) -> dict:
    files = list(results_dir.glob("*-hedera-write.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def failed_names(body: dict) -> list[str]:
    return [c["name"] for c in body["checks"] if not c["passed"]]


def test_the_record_has_the_fixed_form_and_is_small() -> None:
    record = json.loads(proof_record())
    assert set(record) == {"v", "event", "fp"}  # a version, an event, a fingerprint: nothing else
    assert record["v"] == 0
    assert len(record["fp"]) == 64
    assert len(proof_record()) < 200


def test_everything_works(results_dir: Path) -> None:
    ledger, services, settings, _ = setup()
    assert hedera_write.run(services, settings) == 0
    body = saved(results_dir)
    assert body["passed"] is True
    assert failed_names(body) == []
    measured = body["measurements"]
    assert measured["sequence_number"] == 1
    assert measured["topic_link"].startswith("https://hashscan.io/testnet/topic/0.0.")
    assert (
        measured["message_link"] == "https://hashscan.io/testnet/transaction/1791566671.807617381"
    )
    assert measured["control_answer"] == "INVALID_SIGNATURE"
    assert measured["auto_renew_account_sent"] is True
    assert len(ledger.topics) == 2  # the proof topic and the control topic
    assert ledger.clients_made == 1


def test_the_result_file_holds_no_key(results_dir: Path) -> None:
    ledger, services, settings, key_text = setup(explode_on_submit="boom")
    ledger.explode_on_submit = f"the library repeated {key_text} in its error"
    hedera_write.run(services, settings)
    text = next(results_dir.glob("*-hedera-write.json")).read_text(encoding="utf-8")
    assert key_text not in text
    assert key_text[-64:] not in text  # the raw 32 bytes of the key
    assert "RuntimeError" in text  # the failure itself is recorded


def test_the_older_rule_about_auto_renew_is_handled(results_dir: Path) -> None:
    ledger, services, settings, _ = setup(refuse_auto_renew=True)
    assert hedera_write.run(services, settings) == 0
    assert ledger.auto_renew_calls[:2] == [True, False]  # tried once with, then without
    assert saved(results_dir)["measurements"]["auto_renew_account_sent"] is False


def test_a_key_that_is_not_the_key_of_the_account_stops_everything(results_dir: Path) -> None:
    ledger, services, settings, _ = setup(ledger_key_wrong=True)
    assert hedera_write.run(services, settings) == 1
    assert "the private key in .env is the key of this account" in failed_names(saved(results_dir))
    assert ledger.clients_made == 0  # nothing was sent
    assert ledger.topics == {}


def test_an_admin_key_on_the_ledger_fails_the_proof(results_dir: Path) -> None:
    _, services, settings, _ = setup(give_the_topic_an_admin_key=True)
    assert hedera_write.run(services, settings) == 1
    names = failed_names(saved(results_dir))
    assert any("NO admin key" in n for n in names)


def test_a_message_that_comes_back_different_fails_the_proof(results_dir: Path) -> None:
    _, services, settings, _ = setup(alter_messages=True)
    assert hedera_write.run(services, settings) == 1
    assert "the mirror node returns the bytes that were posted" in failed_names(saved(results_dir))


def test_a_stranger_who_can_post_fails_the_proof(results_dir: Path) -> None:
    _, services, settings, _ = setup(accept_strangers=True)
    assert hedera_write.run(services, settings) == 1
    names = failed_names(saved(results_dir))
    assert "a topic whose submit key is someone else's refuses our message" in names


def test_missing_setup_blocks_the_proof_and_writes_no_file(
    results_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, hedera_operator_id="", hedera_operator_key="")
    assert hedera_write.run(settings=settings) == 3
    assert "Blocked" in capsys.readouterr().out
    assert not results_dir.exists() or not list(results_dir.glob("*"))


def test_the_main_network_is_refused(results_dir: Path) -> None:
    ledger, services, settings, key_text = setup()
    settings = Settings(
        _env_file=None,
        hedera_network="mainnet",
        hedera_operator_id=OPERATOR_ID,
        hedera_operator_key=key_text,
    )
    assert hedera_write.run(services, settings) == 1
    assert ledger.clients_made == 0
    assert "the network is the test network" in failed_names(saved(results_dir))


def test_an_account_that_does_not_exist_is_reported(results_dir: Path) -> None:
    ledger, services, settings, key_text = setup()
    settings = Settings(
        _env_file=None,
        hedera_operator_id="0.0.999",
        hedera_operator_key=key_text,
    )
    assert hedera_write.run(services, settings) == 1
    assert "the account exists on the test network" in failed_names(saved(results_dir))
    assert ledger.clients_made == 0


def test_a_key_in_the_middle_of_a_long_error_is_still_removed(results_dir: Path) -> None:
    ledger, services, settings, key_text = setup()
    # The key stands where a cut at 500 characters would split it in two.
    ledger.explode_on_submit = "x" * 480 + key_text + "y" * 100
    hedera_write.run(services, settings)
    text = next(results_dir.glob("*-hedera-write.json")).read_text(encoding="utf-8")
    assert key_text not in text
    assert key_text[:30] not in text  # no half of it either


def test_the_raw_key_that_the_library_prints_in_its_repr_is_removed(results_dir: Path) -> None:
    ledger, services, settings, key_text = setup()
    raw = key_text[-64:]
    ledger.explode_on_submit = f"failed for <PrivateKey (ECDSA) hex={raw}>"
    hedera_write.run(services, settings)
    text = next(results_dir.glob("*-hedera-write.json")).read_text(encoding="utf-8")
    assert raw not in text
