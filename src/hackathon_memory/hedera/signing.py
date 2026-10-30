"""Teams sign their own registration (design 9.6, 29 October 2026).

Before, the tool's account wrote every record, so a record proved that a registration went through
Jevadu, not which account agreed to it. Now a team can sign the text of its record with its own
Hedera wallet, and the record keeps its account and the signature: anyone can check it against the
key that the ledger shows for that account. The tool still writes the record and pays for it: the
topic keeps its one submit key (design 9.5).

Two wallets, two ways of signing (each read on 29 October 2026):

* A Hedera wallet such as HashPack, through Hedera's WalletConnect library
  (@hashgraph/hedera-wallet-connect 2.1.3, method hedera_signMessage). It signs
  "\\x19Hedera Signed Message:\\n" + the length of the text + the text (prefixMessageToSign in
  dist/lib/shared/utils.js; the length is that of the JavaScript string, the number of bytes for
  this ASCII text), and answers a SignatureMap encoded in base64, whose first pair holds the
  signature (verifyMessageSignature). It signs for both kinds of Hedera key.
* MetaMask, an Ethereum wallet (personal_sign): it signs "\\x19Ethereum Signed Message:\\n" + the
  length of the text in bytes + the text, hashed with Keccak-256 (MetaMask's page "Sign data"),
  and answers 65 bytes in hex, r, s and v. It can sign only for an account whose key is an ECDSA
  secp256k1 key, the kind that also has a 0x address.

Both are checked with the Hedera SDK (hiero-sdk-python 0.2.10, crypto/public_key.py): verify()
checks an Ed25519 signature of the bytes, and an ECDSA signature of their Keccak-256 hash, which
is what both wallets sign with such a key.
"""

from __future__ import annotations

import base64
import binascii
import re
import warnings
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from hiero_sdk_python.crypto.public_key import PublicKey
from hiero_sdk_python.hapi.services.basic_types_pb2 import SignatureMap

from hackathon_memory.hedera.mirror import MirrorNode

HEDERA = "hedera"  # hedera_signMessage of a Hedera wallet, through WalletConnect
ETHEREUM = "eip191"  # personal_sign of MetaMask (EIP-191), for an account with an ECDSA key
SCHEMES = (HEDERA, ETHEREUM)
ED25519, ECDSA = "ED25519", "ECDSA_SECP256K1"  # the kinds of key, as the mirror node names them
_ACCOUNT = re.compile(r"^0\.0\.[1-9]\d{0,11}$")
_HEX_SIGNATURE = re.compile(r"^0x[0-9a-fA-F]{130}$")


class SignatureError(Exception):
    """A signature that cannot be accepted, with what to do in plain words."""


@dataclass(frozen=True)
class AccountKey:
    """An account as the mirror node gives it: its key, and its 0x address when it has one."""

    account: str
    key_type: str  # ED25519, ECDSA_SECP256K1, or another kind (a list of keys)
    key_hex: str
    evm_address: str | None


def signed_text(event: str, code: str, commit: str, account: str) -> str:
    """The text that a team signs, which its wallet shows, and which anyone can write again from
    the record: every part of it is in the record."""
    return (
        "Jevadu register\n"
        f"Hackathon: {event}\n"
        f"Repository fingerprint: {code}\n"
        f"Commit: {commit}\n"
        f"Account: {account}"
    )


def hedera_message(text: str) -> bytes:
    return f"\x19Hedera Signed Message:\n{len(text)}{text}".encode()


def ethereum_message(text: str) -> bytes:
    data = text.encode()
    return b"\x19Ethereum Signed Message:\n" + str(len(data)).encode() + data


def account_key(mirror: MirrorNode, account: str) -> AccountKey | None:
    """The key of an account, or of the account of a 0x address, from the mirror node; None when
    the network has no such account."""
    found = mirror.account(account)
    if found is None or found.get("deleted"):
        return None
    key = found.get("key") or {}
    return AccountKey(str(found.get("account")), str(key.get("_type") or ""),
                      str(key.get("key") or ""), found.get("evm_address"))  # fmt: skip


def raw_signature(scheme: str, signature: str) -> bytes:
    """The signature as bytes: the first pair of a Hedera wallet's SignatureMap, or MetaMask's
    65 bytes."""
    if scheme == ETHEREUM:
        if not _HEX_SIGNATURE.match(signature):
            raise SignatureError("The EVM wallet gave a signature of an unknown form. Sign again.")
        return bytes.fromhex(signature[2:])
    if scheme != HEDERA:
        raise SignatureError("This way of signing is not known.")
    try:
        pairs = SignatureMap.FromString(base64.b64decode(signature, validate=True)).sigPair
    except (binascii.Error, ValueError):
        unknown = "The wallet gave a signature of an unknown form. Sign again."
        raise SignatureError(unknown) from None
    found = (pairs[0].ed25519 or pairs[0].ECDSA_secp256k1) if pairs else b""
    if not found:
        raise SignatureError("The wallet gave no signature. Sign again.")
    return found


def check(scheme: str, text: str, signature: bytes, key: AccountKey) -> None:
    """Raise a SignatureError unless `signature` is that of `key` for `text`, made by a wallet of
    the kind `scheme`."""
    if key.key_type not in (ED25519, ECDSA) or not key.key_hex:
        raise SignatureError(f"The account {key.account} has a list of keys, or no key yet: only "
                             "an account with one key can sign here.")  # fmt: skip
    if scheme == ETHEREUM and key.key_type != ECDSA:
        raise SignatureError(f"An EVM wallet can sign only for an account with an ECDSA key, and "
                             f"{key.account} has an Ed25519 key: sign with a Hedera "
                             "wallet.")  # fmt: skip
    # The SDK warns that 32 bytes may be a private seed (0.2.10); the mirror node gives only
    # public keys, so the warning says nothing here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        public = (PublicKey.from_bytes_ed25519(bytes.fromhex(key.key_hex))
                  if key.key_type == ED25519
                  else PublicKey.from_bytes_ecdsa(bytes.fromhex(key.key_hex)))  # fmt: skip
    message = hedera_message(text) if scheme == HEDERA else ethereum_message(text)
    try:
        public.verify(signature[:64], message)  # MetaMask's 65th byte, v, is not needed here
    except (InvalidSignature, ValueError):
        raise SignatureError(f"The signature is not that of the key of {key.account} on the "
                             "ledger. Sign again with that account.") from None  # fmt: skip


def account_of(text: str) -> str | None:
    text = text.strip()
    return text if _ACCOUNT.match(text) else None
