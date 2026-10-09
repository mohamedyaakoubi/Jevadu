"""Loading the operator's private key without letting it reach a log (design rule 9).

Two traps were found in hiero-sdk-python 0.2.10:

1. `PrivateKey.__repr__` prints the whole key, and `PrivateKey.from_string` puts the text it was
   given into its error message. So a print, a log line, a failed assertion or a traceback could
   leak the key. Here the key is loaded in one place, any error is raised AFTER the library's
   error has been left behind, and the messages hold no part of the text.
2. A key of 64 hex letters is read as Ed25519 first, even when it is an ECDSA key. The
   signature is then wrong and the network refuses the transaction. The DER form of the key says
   its own type, so it is the one asked for. A raw 64-letter key is accepted only when the
   ledger says which type the account has.

The public key of the account is public on the ledger, so a key can be checked against its account
before anything is sent. That is `matches_ledger_key`.
"""

from __future__ import annotations

import re
import warnings

from hiero_sdk_python.crypto.private_key import PrivateKey

_HEX = re.compile(r"^[0-9a-fA-F]+$")
_RAW_LENGTH = 64  # 32 bytes in hex


class OperatorKeyError(Exception):
    """The key cannot be used. The message never holds any part of the key."""


def load_operator_key(text: str, ledger_key_type: str | None = None) -> PrivateKey:
    """Read a private key from hex. `ledger_key_type` is "ED25519" or "ECDSA_SECP256K1"."""
    cleaned = text.strip()
    cleaned = cleaned[2:] if cleaned.lower().startswith("0x") else cleaned
    if not cleaned or len(cleaned) % 2 or not _HEX.match(cleaned):
        raise OperatorKeyError("HEDERA_OPERATOR_KEY is not hex text.")

    problem = ""
    key: PrivateKey | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # the library warns about 32-byte keys
            if len(cleaned) == _RAW_LENGTH:
                if ledger_key_type == "ED25519":
                    key = PrivateKey.from_string_ed25519(cleaned)
                elif ledger_key_type == "ECDSA_SECP256K1":
                    key = PrivateKey.from_string_ecdsa(cleaned)
                else:
                    problem = (
                        "A key of 64 letters does not say whether it is ED25519 or ECDSA. "
                        "Use the DER encoded private key of the portal (it starts with 30)."
                    )
            else:
                key = PrivateKey.from_string_der(cleaned)
    except Exception:  # noqa: BLE001  (the library's message may hold the key text: drop it)
        problem = "HEDERA_OPERATOR_KEY could not be read as a private key."
    # The error is raised here, outside the except block, so no chained error carries the text.
    if key is None:
        raise OperatorKeyError(problem or "HEDERA_OPERATOR_KEY could not be read.")
    return key


def public_key_hex(key: PrivateKey) -> str:
    """The public half in the form that the mirror node shows: 64 letters for ED25519,
    66 for ECDSA (the compressed form)."""
    return key.public_key().to_string_raw().lower()


def matches_ledger_key(key: PrivateKey, ledger_key: dict | None) -> bool:
    """True if `key` is the key that the ledger shows for an account: {"_type", "key"}."""
    if not ledger_key or "key" not in ledger_key:
        return False
    kind = ledger_key.get("_type")
    if kind == "ED25519" and not key.is_ed25519():
        return False
    if kind == "ECDSA_SECP256K1" and not key.is_ecdsa():
        return False
    if kind not in ("ED25519", "ECDSA_SECP256K1"):
        return False  # a list of keys or a threshold key: not supported
    return public_key_hex(key) == str(ledger_key["key"]).lower()
