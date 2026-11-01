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
from hiero_sdk_python.utils.crypto_utils import keccak256

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


# The curve secp256k1 (SEC 2, section 2.4.1), for the address that made a signature of an EVM
# wallet: the ledger knows the 0x address of an account made by sending HBAR to it, but not its key
# until the account pays for a first transaction (docs.hedera.com, the testnet faucet: "Auto
# Account Creation"), so such a signature is checked by the address that it comes from.
_P = 2**256 - 2**32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)  # fmt: skip
_Point = tuple[int, int] | None  # None is the point at infinity


def _add(a: _Point, b: _Point) -> _Point:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        slope = 3 * a[0] * a[0] * pow(2 * a[1], -1, _P) % _P
    else:
        slope = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (slope * slope - a[0] - b[0]) % _P
    return x, (slope * (a[0] - x) - a[1]) % _P


def _times(k: int, point: _Point) -> _Point:
    total = None
    while k:
        if k & 1:
            total = _add(total, point)
        point = _add(point, point)
        k >>= 1
    return total


def signer_address(message: bytes, signature: bytes) -> str | None:
    """The 0x address whose key made `signature` (r, s and v, 65 bytes) of the Keccak-256 hash of
    `message`, as ecrecover finds it; None for a signature of no point of the curve."""
    if len(signature) != 65:
        return None
    r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:64], "big")
    parity = signature[64] - 27 if signature[64] >= 27 else signature[64]
    if not (0 < r < _N and 0 < s < _N) or parity not in (0, 1):
        return None
    square = (pow(r, 3, _P) + 7) % _P
    y = pow(square, (_P + 1) // 4, _P)
    if y * y % _P != square:
        return None
    if y % 2 != parity:
        y = _P - y
    hashed = int.from_bytes(keccak256(message), "big")
    key = _times(pow(r, -1, _N), _add(_times(s, (r, y)), _times(-hashed % _N, _G)))
    if key is None:
        return None
    return "0x" + keccak256(key[0].to_bytes(32, "big") + key[1].to_bytes(32, "big"))[-20:].hex()


def evm_address_of(key: str) -> str | None:
    """The EVM address of a compressed secp256k1 public key (33 bytes in hex, 02 or 03 first), as a
    wallet such as MetaMask names it on every network: the last 20 bytes of the Keccak-256 hash of
    its point. None for a key that is not one."""
    try:
        raw = bytes.fromhex(key.removeprefix("0x"))
    except ValueError:
        return None
    if len(raw) != 33 or raw[0] not in (2, 3):
        return None
    x = int.from_bytes(raw[1:], "big")
    square = (pow(x, 3, _P) + 7) % _P
    y = pow(square, (_P + 1) // 4, _P)
    if x >= _P or y * y % _P != square:
        return None
    if y % 2 != raw[0] - 2:
        y = _P - y
    return "0x" + keccak256(x.to_bytes(32, "big") + y.to_bytes(32, "big"))[-20:].hex()


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
    if scheme == ETHEREUM and not key.key_hex and key.evm_address:
        # an account that the ledger knows by its 0x address only: the one that signed must be it
        if signer_address(ethereum_message(text), signature) != key.evm_address.lower():
            raise SignatureError(f"The signature is not that of the address of {key.account} on "
                                 "the ledger. Sign again with that account.")  # fmt: skip
        return
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
