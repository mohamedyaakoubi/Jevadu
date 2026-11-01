"""What a transaction on Hedera's main network did (design 7.6, 1 November 2026): in the words of
the ledger, of the messages that a project wrote there, and of the project's own code, never of a
model (design rule 2). The step `mainnet_what` asks the mirror node and GitHub; this module only
reads their answers.

- A message of a topic is often a JSON object. The value of its first key among ACTION_KEYS says
  what it records ("event": "AttackBlocked"), and its keys among NETWORK_KEYS the networks that it
  names (CAIP-2, "eip155:8453"). A value is kept only when it is one word that looks like a kind,
  so that free text and the names of people are never kept (design 5.4).
- A call of a contract starts with a selector, the first 4 bytes of the keccak hash of the
  function's signature. The signatures come from the Solidity files of the project's repository,
  and from LIBRARY, functions that a contract takes from a common library. Read on 1 November 2026:
  MemeWarp's createMeme((string,string,string,string,address,uint256)), a struct, and RampNet's
  setPeer(uint32,bytes32) of LayerZero's OApp, which is not in its repository. The hash is
  hiero-sdk-python 0.2.10's keccak256 (utils/crypto_utils.py), as in hedera/signing.py.
- A scheduled transaction holds its body as protobuf (`transaction_body`, base64), read with the
  classes of hiero-sdk-python 0.2.10 (SchedulableTransactionBody, its oneof "data").
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from google.protobuf.message import DecodeError
from hiero_sdk_python.hapi.services.schedulable_transaction_body_pb2 import (
    SchedulableTransactionBody,
)
from hiero_sdk_python.utils.crypto_utils import keccak256

from hackathon_memory.check.mainnet import TINYBARS

DEPLOYED = "deployed the contract"
SCHEDULE_RAN = "the scheduled transaction ran"
ACTION_KEYS = ("event", "type", "action", "kind", "op", "operation", "method", "status",
               "category", "command")  # fmt: skip
NETWORK_KEYS = ("network", "chain", "chainId", "chain_id", "chainID")
MAX_FIELDS = 12
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:+-]{0,39}$")  # one word: a kind, never a name
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
_CAIP2 = re.compile(r"^[a-z0-9-]{3,8}:[A-Za-z0-9_-]{1,32}$")  # namespace:reference
_SELECTOR = re.compile(r"^0x[0-9a-f]{8}")

# Functions that a contract often takes from a common library rather than from its project's own
# files: OpenZeppelin's tokens and ownership, and LayerZero's OApp (setPeer links a contract to its
# twin on another chain, setDelegate names who may set it up).
LIBRARY = (
    "transfer(address,uint256)", "approve(address,uint256)",
    "transferFrom(address,address,uint256)", "safeTransferFrom(address,address,uint256)",
    "safeTransferFrom(address,address,uint256,bytes)", "setApprovalForAll(address,bool)",
    "mint(address,uint256)", "burn(uint256)", "transferOwnership(address)", "renounceOwnership()",
    "setPeer(uint32,bytes32)", "setDelegate(address)",
)  # fmt: skip
LIBRARY_SOURCE = "a common library"
_SCHEDULED_WORDS = {"tokenMint": "a token mint", "consensusSubmitMessage": "a message to a topic",
                    "contractCall": "a call of a contract", "tokenBurn": "a token burn",
                    "cryptoApproveAllowance": "an allowance"}  # fmt: skip


@dataclass(frozen=True)
class Message:
    """What a message of a topic says about itself."""

    what: str | None  # the value of its first key among ACTION_KEYS
    fields: tuple[str, ...]  # its keys, when it is a JSON object
    networks: tuple[str, ...]  # the networks that it names, as CAIP-2


@dataclass(frozen=True)
class Thing:
    """A thing on the main network: an own ID of a project, or a thing that the account which
    made one also made there (migration 0029)."""

    entity_id: str  # as the ledger names it, 0.0.X
    kind: str
    made_at: datetime | None
    made_by: str | None
    name: str | None = None  # a token's name and symbol, or a memo
    fields: tuple[str, ...] = ()  # a topic: the keys of its JSON messages
    names_from: str | None = None  # a contract: where the names of its functions come from
    scheduled: str | None = None  # a schedule: what it holds, in words
    executed: str | None = None  # a schedule: the moment it ran
    held_by_others: int | None = None  # a token: the accounts that hold it, its treasury apart
    messages: int | None = None  # a topic: its messages so far


@dataclass(frozen=True)
class Scheduled:
    """What a scheduled transaction holds, and when it ran."""

    memo: str | None
    what: str  # its body in words: "a transfer of 4 HBAR"
    executed: str | None  # the moment it ran, seconds.nanoseconds


def network_of(value: object) -> str | None:
    """A network that a message names, as CAIP-2: a number is a chain of EIP-155."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        number = int(value)
        return f"eip155:{number}" if 0 < number < 10**12 else None
    if isinstance(value, str) and _CAIP2.match(value.strip()):
        namespace, _, reference = value.strip().partition(":")
        return f"{namespace}:{reference}"
    return None


def message_of(raw: bytes) -> Message:
    """What a message says about itself; nothing when it is not a JSON object."""
    try:
        content = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Message(None, (), ())
    if not isinstance(content, dict):
        return Message(None, (), ())
    fields = tuple(sorted(key for key in content if _KEY.match(key)))[:MAX_FIELDS]
    named = [content.get(key) for key in ACTION_KEYS]
    what = next((one for one in named if isinstance(one, str) and _NAME.match(one)), None)
    networks = {network_of(content.get(key)) for key in NETWORK_KEYS}
    return Message(what, fields, tuple(sorted(one for one in networks if one)))


# ------------------------------------------------------------------- the code of a contract

_FUNCTION = re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.S)
_STRUCT = re.compile(r"\bstruct\s+([A-Za-z_]\w*)\s*\{([^}]*)\}", re.S)
_ENUM = re.compile(r"\benum\s+([A-Za-z_]\w*)\s*\{")
_NAMED = re.compile(r"\b(?:contract|interface|library)\s+([A-Za-z_]\w*)")
_DROP = {"memory", "calldata", "storage", "indexed", "payable"}


def selector(signature: str) -> str:
    """The first 4 bytes of the keccak hash of a function's signature, as the EVM calls it."""
    return "0x" + keccak256(signature.encode())[:4].hex()


def _no_comments(source: str) -> str:
    return re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", source, flags=re.S))


class _Types:
    """The types of a set of Solidity files, as the ABI writes them: a struct is the tuple of its
    members, an enum is uint8, a contract or an interface is an address."""

    def __init__(self, sources: Iterable[str]) -> None:
        self.structs: dict[str, list[str]] = {}
        self.enums: set[str] = set()
        self.named: set[str] = set()
        for source in sources:
            for name, body in _STRUCT.findall(source):
                members = [one.split() for one in body.split(";") if one.strip()]
                self.structs[name] = [one[0] for one in members if not one[0].startswith("mapping")]
            self.enums.update(_ENUM.findall(source))
            self.named.update(_NAMED.findall(source))

    def abi(self, word: str, depth: int = 0) -> str:
        match = re.match(r"^([A-Za-z_][\w.]*)(.*)$", word)
        if not match:
            return word
        base, suffix = match.group(1).split(".")[-1], match.group(2).replace(" ", "")
        if base in ("uint", "int"):
            base += "256"
        elif base == "byte":
            base = "bytes1"
        elif base in self.enums:
            base = "uint8"
        elif base in self.structs and depth < 4:
            base = "(" + ",".join(self.abi(one, depth + 1) for one in self.structs[base]) + ")"
        elif base in self.named:
            base = "address"
        return base + suffix

    def parameters(self, raw: str) -> list[str]:
        found = []
        for part in raw.split(","):
            words = [word for word in part.split() if word not in _DROP]
            if words:
                found.append(self.abi(words[0]))
        return found


def functions_of(sources: Iterable[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """The functions of a set of Solidity files, by selector: the name and the file that declares
    it; then those of LIBRARY that no file declares, with LIBRARY_SOURCE."""
    files = [(path, _no_comments(source)) for path, source in sources]
    types = _Types(source for _, source in files)
    found: dict[str, tuple[str, str]] = {}
    for path, source in files:
        for name, raw in _FUNCTION.findall(source):
            signature = f"{name}({','.join(types.parameters(raw))})"
            found.setdefault(selector(signature), (name, path))
    for signature in LIBRARY:
        found.setdefault(selector(signature), (signature.split("(", 1)[0], LIBRARY_SOURCE))
    return found


def call_of(
    result: Mapping, contract_ids: Iterable[str], functions: Mapping[str, tuple[str, str]]
) -> str:
    """What one call of a contract did, from the mirror node's result of it: DEPLOYED for its
    creation, the name of its function, or "call 0x..." when the function's name is not known.
    Who sent it is the payer of its event in the history (check/history.py)."""
    if set(result.get("created_contract_ids") or ()) & set(contract_ids):
        return DEPLOYED
    data = str(result.get("function_parameters") or "").lower()
    if not _SELECTOR.match(data):
        return "a call with no data"
    known = functions.get(data[:10])
    return known[0] if known else f"call {data[:10]}"


def names_from(functions: Mapping[str, tuple[str, str]], used: Iterable[str]) -> str | None:
    """Where the names of the functions that were called come from, in words."""
    files = sorted({functions[one][1] for one in used if one in functions})
    own = [one for one in files if one != LIBRARY_SOURCE]
    parts = ([f"its own code ({', '.join(own[:3])}{', ...' if len(own) > 3 else ''})"] if own
             else []) + ([LIBRARY_SOURCE] if LIBRARY_SOURCE in files else [])  # fmt: skip
    return " and ".join(parts) or None


# ------------------------------------------------------------------- the other transactions


def long_zero(account: str) -> str | None:
    """The EVM address that the ledger gives an account with no alias: its number in 20 bytes.
    The mirror node names the sender of a contract's creation so (read on 1 November 2026:
    0.0.9224969 made MemeWarp's contract as 0x00...008cc309)."""
    shard, realm, number = (account.split(".") + ["", "", ""])[:3]
    if shard != "0" or realm != "0" or not number.isdigit():
        return None
    return "0x" + format(int(number), "040x")


def hbar_words(tinybars: int) -> str:
    """An amount of HBAR with no needless zeros: 400,000,000 tinybars are "4 HBAR"."""
    return f"{tinybars / TINYBARS:,.8f}".rstrip("0").rstrip(".") + " HBAR"


def scheduled_of(schedule: Mapping) -> Scheduled:
    """What the mirror node's answer about a scheduled transaction holds."""
    memo = str(schedule.get("memo") or "").strip()[:120] or None
    executed = schedule.get("executed_timestamp") or None
    try:
        body = SchedulableTransactionBody.FromString(
            base64.b64decode(schedule.get("transaction_body") or "")
        )
    except (binascii.Error, DecodeError, ValueError):
        return Scheduled(memo, "a transaction that the tool cannot read", executed)
    kind = body.WhichOneof("data")
    if kind == "cryptoTransfer":
        credited = sum(one.amount for one in body.cryptoTransfer.transfers.accountAmounts
                       if one.amount > 0)  # fmt: skip
        tokens = len(body.cryptoTransfer.tokenTransfers)
        words = f"a transfer of {hbar_words(credited)}" if credited else "a transfer"
        return Scheduled(memo, words + (f" and {tokens} token transfer{'s' * (tokens != 1)}"
                                        if tokens else ""), executed)  # fmt: skip
    return Scheduled(memo, _SCHEDULED_WORDS.get(kind or "", kind or "an empty transaction"),
                     executed)  # fmt: skip


def token_words(token: Mapping) -> str | None:
    """A token in words, as its maker named it: "Lynxify Index Token (LXY)"."""
    name = str(token.get("name") or "").strip()[:100]
    symbol = str(token.get("symbol") or "").strip()[:30]
    if name and symbol and symbol != name:
        return f"{name} ({symbol})"
    return name or symbol or None


def transfer_what(transaction: Mapping, symbols: Mapping[str, str]) -> str | None:
    """What a transaction with tokens moved, by the symbols of its tokens: "moved SAUCE"; None for
    any other transaction, whose kind says it all."""
    tokens = [str(one.get("token_id")) for one in transaction.get("token_transfers") or ()
              if int(one.get("amount") or 0) > 0]  # fmt: skip
    tokens += [str(one.get("token_id")) for one in transaction.get("nft_transfers") or ()]
    names = sorted({symbols.get(one, one) for one in tokens if one})
    return f"moved {', '.join(names[:3])}" if names else None
