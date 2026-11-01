"""Teams sign their own registration (hedera/signing.py, hedera/registry.py, design 9.6): the text,
the two ways of signing, and the signed record, with keys made by the Hedera SDK for the test.
Every account is invented."""

from __future__ import annotations

import base64

import pytest
from hiero_sdk_python.crypto.private_key import PrivateKey
from hiero_sdk_python.hapi.services.basic_types_pb2 import SignatureMap, SignaturePair
from hiero_sdk_python.utils.crypto_utils import keccak256

from hackathon_memory.hedera import registry
from hackathon_memory.hedera.register import RegisterError
from hackathon_memory.hedera.signing import (
    ECDSA,
    ED25519,
    ETHEREUM,
    HEDERA,
    AccountKey,
    SignatureError,
    check,
    ethereum_message,
    evm_address_of,
    hedera_message,
    raw_signature,
    signed_text,
    signer_address,
)

EVENT, CODE, COMMIT = "ethglobal.com/ethonline2026", "ab" * 32, "cd" * 20
TEXT = signed_text(EVENT, CODE, COMMIT, "0.0.7001")


def key_of(private: PrivateKey, account: str = "0.0.7001") -> AccountKey:
    """The account as the mirror node gives it: the raw public key in hex (compressed for ECDSA)."""
    kind = ED25519 if private.public_key().is_ed25519() else ECDSA
    return AccountKey(account, kind, private.public_key().to_bytes_raw().hex(), None)


def signature_map(signature: bytes, ecdsa: bool) -> str:
    """What a Hedera wallet answers through WalletConnect: a SignatureMap in base64."""
    pair = SignaturePair(ECDSA_secp256k1=signature) if ecdsa else SignaturePair(ed25519=signature)
    return base64.b64encode(SignatureMap(sigPair=[pair]).SerializeToString()).decode()


def test_the_signed_text_holds_every_part_of_the_record_and_its_prefixes() -> None:
    assert TEXT == (f"Jevadu register\nHackathon: {EVENT}\nRepository fingerprint: {CODE}\n"
                    f"Commit: {COMMIT}\nAccount: 0.0.7001")  # fmt: skip
    assert hedera_message("Hello") == b"\x19Hedera Signed Message:\n5Hello"
    assert ethereum_message("Hello") == b"\x19Ethereum Signed Message:\n5Hello"


@pytest.mark.parametrize("ecdsa", [False, True])
def test_a_hedera_wallet_signature_is_checked_for_both_kinds_of_key(ecdsa: bool) -> None:
    private = PrivateKey.generate_ecdsa() if ecdsa else PrivateKey.generate_ed25519()
    answer = signature_map(private.sign(hedera_message(TEXT)), ecdsa)
    signature = raw_signature(HEDERA, answer)
    check(HEDERA, TEXT, signature, key_of(private))  # no error: it is that account's signature
    with pytest.raises(SignatureError, match="not that of the key of 0.0.7001"):
        check(HEDERA, TEXT.replace(COMMIT, "ef" * 20), signature, key_of(private))
    with pytest.raises(SignatureError):
        check(HEDERA, TEXT, signature, key_of(PrivateKey.generate_ed25519()))


def test_a_metamask_signature_is_checked_for_an_ecdsa_account_only() -> None:
    """MetaMask signs the Keccak-256 of the EIP-191 message, as the SDK signs with an ECDSA key;
    it answers 65 bytes in hex, the last one v."""
    private = PrivateKey.generate_ecdsa()
    answer = "0x" + (private.sign(ethereum_message(TEXT)) + bytes([27])).hex()
    signature = raw_signature(ETHEREUM, answer)
    assert len(signature) == 65
    check(ETHEREUM, TEXT, signature, key_of(private))
    with pytest.raises(SignatureError, match="An EVM wallet can sign only for an account with an"):
        check(ETHEREUM, TEXT, signature, key_of(PrivateKey.generate_ed25519()))
    # its record keeps the 65 bytes, and reads back (base64 with one "=" at the end)
    payload = registry.signed_record(EVENT, CODE, COMMIT, "0.0.7001", ETHEREUM, signature)
    message = {"sequence_number": 5, "consensus_timestamp": "1792665702.157973275",
               "message": base64.b64encode(payload).decode()}  # fmt: skip
    found = registry.read_record(message)
    assert found is not None and found.scheme == ETHEREUM
    found.check_signature(key_of(private))
    with pytest.raises(SignatureError):  # the Hedera prefix is not MetaMask's
        check(HEDERA, TEXT, signature, key_of(private))


def test_a_signature_of_an_unknown_form_or_an_account_with_a_list_of_keys_is_refused() -> None:
    for scheme, answer in ((ETHEREUM, "0x1234"), (HEDERA, "not base64!"), ("bitcoin", "x")):
        with pytest.raises(SignatureError):
            raw_signature(scheme, answer)
    with pytest.raises(SignatureError, match="no signature"):
        raw_signature(HEDERA, base64.b64encode(SignatureMap().SerializeToString()).decode())
    listed = AccountKey("0.0.7002", "ProtobufEncoded", "0a2212", None)
    with pytest.raises(SignatureError, match="list of keys"):
        check(HEDERA, TEXT, bytes(64), listed)


def test_a_signed_record_is_version_3_and_can_be_checked_again_from_the_ledger() -> None:
    private = PrivateKey.generate_ed25519()
    signature = private.sign(hedera_message(TEXT))
    payload = registry.signed_record(EVENT, CODE, COMMIT, "0.0.7001", HEDERA, signature)
    assert len(payload) <= registry.MAX_RECORD
    message = {"sequence_number": 4, "consensus_timestamp": "1792665702.157973275",
               "message": base64.b64encode(payload).decode()}  # fmt: skip
    found = registry.read_record(message)
    assert found is not None and (found.signer, found.scheme) == ("0.0.7001", HEDERA)
    assert found.account is None and found.commit == COMMIT
    found.check_signature(key_of(private))  # anyone can do it again from the record
    with pytest.raises(SignatureError):
        found.check_signature(key_of(PrivateKey.generate_ed25519()))
    with pytest.raises(RegisterError):  # only the fixed form
        registry.signed_record(EVENT, CODE, COMMIT, "Alice", HEDERA, signature)
    unsigned = registry.read_record({**message, "message": base64.b64encode(
        registry.record(EVENT, CODE, COMMIT)).decode()})  # fmt: skip
    assert unsigned is not None and unsigned.signer is None
    with pytest.raises(RegisterError, match="not signed"):
        unsigned.check_signature(key_of(private))


def address_of(private: PrivateKey) -> str:
    return "0x" + keccak256(private.public_key().to_bytes_ecdsa(compressed=False)[1:])[-20:].hex()


def test_the_signer_of_an_evm_signature_is_found_as_ecrecover_finds_it() -> None:
    """The example of web3.js's documentation for accounts.sign("Some data"), whose key gives the
    documented address and whose hash is the documented one; then a key of the SDK, for which
    exactly one of the two values of v gives its address."""
    known = PrivateKey.from_bytes_ecdsa(
        bytes.fromhex("4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318")
    )
    assert address_of(known) == "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23"
    assert keccak256(ethereum_message("Some data")).hex() == (
        "1da44b586eb0729ff70a73c326926f6ed5a25f5b056e7f47fbc6e58d86871655")  # fmt: skip
    documented = bytes.fromhex(
        "b91467e570a6466aa9e9876cbcd013baba02900b8979d43fe208a4a4f339f5fd"
        "6007e74cd82e037b800186422fc2da167c747ef045e5d18a5f5d4300f8e1a0291c"
    )
    assert signer_address(ethereum_message("Some data"), documented) == address_of(known)
    private = PrivateKey.generate_ecdsa()
    raw = private.sign(ethereum_message(TEXT))
    found = [signer_address(ethereum_message(TEXT), raw + bytes([v])) for v in (27, 28)]
    assert found.count(address_of(private)) == 1
    assert signer_address(ethereum_message(TEXT), raw) is None  # no v
    assert signer_address(ethereum_message(TEXT), raw + bytes([29])) is None
    assert signer_address(ethereum_message(TEXT), bytes(64) + bytes([27])) is None  # r = s = 0


def test_an_account_known_by_its_address_only_is_checked_by_the_signer() -> None:
    """Test HBAR sent to a 0x address makes an account that the ledger knows by that address,
    with no key until it pays for a first transaction (30 October 2026: MetaMask could not sign
    for it). An EVM wallet's signature is then checked by the address that made it."""
    private = PrivateKey.generate_ecdsa()
    raw = private.sign(ethereum_message(TEXT))
    signature = next(raw + bytes([v]) for v in (27, 28)
                     if signer_address(ethereum_message(TEXT), raw + bytes([v]))
                     == address_of(private))  # fmt: skip
    hollow = AccountKey("0.0.7001", "", "", address_of(private))
    check(ETHEREUM, TEXT, signature, hollow)  # no error
    with pytest.raises(SignatureError, match="not that of the address of 0.0.7001"):
        check(ETHEREUM, signed_text(EVENT, CODE, "ef" * 20, "0.0.7001"), signature, hollow)
    other = PrivateKey.generate_ecdsa().sign(ethereum_message(TEXT))
    with pytest.raises(SignatureError, match="not that of the address of 0.0.7001"):
        check(ETHEREUM, TEXT, other + bytes([27]), hollow)
    with pytest.raises(SignatureError, match="no key yet"):  # a Hedera wallet needs the key
        check(HEDERA, TEXT, raw, hollow)


def test_the_evm_address_of_a_compressed_key() -> None:
    """The key of the private key 1 gives the well-known address 0x7E5F...5bdf; a key that is not
    a point of the curve, or not compressed, gives none."""
    assert evm_address_of("0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798") == (
        "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf")  # fmt: skip
    assert evm_address_of("04" + "11" * 32) is None
    assert evm_address_of("not hex") is None
    assert evm_address_of("02" + "ff" * 32) is None  # x past the field
