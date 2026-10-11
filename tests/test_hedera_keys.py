"""The operator key is loaded without ever leaking, and is checked against the ledger.

Every key here is made by the test. No real key is used.
"""

from __future__ import annotations

import os
import warnings

import pytest
from hiero_sdk_python.crypto.private_key import PrivateKey

from hackathon_memory.hedera.keys import (
    OperatorKeyError,
    load_operator_key,
    matches_ledger_key,
    public_key_hex,
)

# The wrappers that Hedera's portal and tools print around a raw 32-byte key.
ED25519_DER = "302e020100300506032b657004220420"
ECDSA_DER = "3030020100300706052b8104000a04220420"
CANARY = "CANARYTEXT"


def raw_key() -> str:
    return os.urandom(32).hex()


def test_a_der_key_says_its_own_type() -> None:
    raw = raw_key()
    ed = load_operator_key(ED25519_DER + raw)
    ec = load_operator_key(ECDSA_DER + raw)
    assert ed.is_ed25519()
    assert ec.is_ecdsa()
    assert public_key_hex(ed) != public_key_hex(ec)


def test_the_two_public_key_forms_match_what_the_mirror_node_shows() -> None:
    raw = raw_key()
    assert len(public_key_hex(load_operator_key(ED25519_DER + raw))) == 64
    assert len(public_key_hex(load_operator_key(ECDSA_DER + raw))) == 66  # the compressed form


def test_a_raw_key_needs_the_type_from_the_ledger() -> None:
    raw = raw_key()
    with pytest.raises(OperatorKeyError, match="does not say"):
        load_operator_key(raw)
    assert load_operator_key(raw, "ED25519").is_ed25519()
    assert load_operator_key(raw, "ECDSA_SECP256K1").is_ecdsa()


def test_the_zero_x_prefix_and_spaces_are_accepted() -> None:
    raw = raw_key()
    assert load_operator_key("  0x" + ECDSA_DER + raw + "\n").is_ecdsa()


def test_the_library_trap_is_still_there() -> None:
    """If this test fails, hiero-sdk-python changed: read its source again and relax the guard."""
    raw = raw_key()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        guessed = PrivateKey.from_string(raw)
    assert guessed.is_ed25519()  # a raw ECDSA key would be read as Ed25519 by the library
    assert "hex=" in repr(guessed)  # repr() prints the whole key
    with pytest.raises(ValueError, match=CANARY):
        PrivateKey.from_string(f"zz-{CANARY}")  # the error repeats the text it was given


@pytest.mark.parametrize(
    "bad",
    [
        f"zz-not-hex-{CANARY}",
        "abc",  # odd length
        "",
        "   ",
        "ab" * 50,  # hex, but not a key
        ED25519_DER + "ab" * 10,  # a DER header with a short body
    ],
)
def test_a_bad_key_raises_an_error_that_holds_none_of_the_text(bad: str) -> None:
    with pytest.raises(OperatorKeyError) as failure:
        load_operator_key(bad)
    assert CANARY not in str(failure.value)
    assert bad.strip() not in str(failure.value) or not bad.strip()
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None  # no chained error that carries the text


def test_the_error_holds_none_of_a_valid_looking_key_either() -> None:
    almost = "30" + "ab" * 40
    with pytest.raises(OperatorKeyError) as failure:
        load_operator_key(almost)
    assert almost not in str(failure.value)
    assert failure.value.__context__ is None


# ----------------------------------------------------------------- the key and the ledger


def ledger_form(key: PrivateKey) -> dict:
    kind = "ED25519" if key.is_ed25519() else "ECDSA_SECP256K1"
    return {"_type": kind, "key": public_key_hex(key)}


def test_a_key_matches_its_own_account() -> None:
    for der in (ED25519_DER, ECDSA_DER):
        key = load_operator_key(der + raw_key())
        assert matches_ledger_key(key, ledger_form(key)) is True


def test_a_key_does_not_match_another_account() -> None:
    key = load_operator_key(ECDSA_DER + raw_key())
    other = load_operator_key(ECDSA_DER + raw_key())
    assert matches_ledger_key(key, ledger_form(other)) is False


def test_the_same_bytes_read_with_the_wrong_type_do_not_match() -> None:
    raw = raw_key()
    as_ed = load_operator_key(raw, "ED25519")
    as_ec = load_operator_key(raw, "ECDSA_SECP256K1")
    ledger = ledger_form(as_ec)  # the account is ECDSA
    assert matches_ledger_key(as_ec, ledger) is True
    assert matches_ledger_key(as_ed, ledger) is False  # the guess the library would make


def test_an_unknown_or_missing_ledger_key_never_matches() -> None:
    key = load_operator_key(ECDSA_DER + raw_key())
    assert matches_ledger_key(key, None) is False
    assert matches_ledger_key(key, {}) is False
    assert matches_ledger_key(key, {"_type": "ProtobufEncoded", "key": "0a00"}) is False
    assert matches_ledger_key(key, {"_type": "ECDSA_SECP256K1"}) is False


def test_the_ledger_key_may_be_in_upper_case() -> None:
    key = load_operator_key(ED25519_DER + raw_key())
    ledger = ledger_form(key)
    ledger["key"] = ledger["key"].upper()
    assert matches_ledger_key(key, ledger) is True
