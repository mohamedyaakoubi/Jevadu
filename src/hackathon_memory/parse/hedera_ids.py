"""Find Hedera ids in a text, with the words around each one (design 6.1 and 7.1).

An id of Hedera looks like 0.0.12345. A pattern alone is not enough, for three reasons.

* A version number has the same shape ("0.0.3", "v0.0.12"). The numbers up to 1000 belong to the
  network itself, so no project owns one of them. Such a number is never given as an id.
* The same number is a different thing on each network, so an id is kept with its network. A
  link to HashScan names the network exactly. Words do it less surely, and a wrong network is
  worse than none: the ledger would be asked about another thing. So the network is taken from
  words only when the words near the id name one network and no other. When they name none, or
  two, the network stays open and both are asked later.
* The words near an id often say what it is: an account, a token, a topic or a contract. The
  word just before the id on its line counts ("Topic ID: 0.0.12345"). If there is none, the word
  just after it counts ("0.0.12345 (topic)"). A word on the far side of another id does not.

An address of the EVM kind (0x and 40 letters) is kept only when a HashScan link names it. The
same address can live on any other chain, so a bare one is not taken for Hedera.

A transaction is one action on the ledger: a transfer, the creation of a token, a message to a
topic, a call of a contract. Its ID is the account that paid for it and the moment it was sent:
"0.0.12345@1700000000.123456789" or "0.0.12345-1700000000-123456789". Both give two IDs: the
transaction itself, which says exactly what happened and when, and the account that paid. The
mirror node asks for the second form only (measured on 18 October 2026), so every transaction is
kept in it. A link to a transaction that gives only a time names no ID.

Sources, read on 11 October 2026. The shape of an id with its check word of five letters is the
one of hiero-sdk-python 0.2.10 (utils/entity_id_helper.py, ID_REGEX). The first number that a
user can own is 1001: the default of `firstUserEntity` in the code of the network's nodes
(hiero-ledger/hiero-consensus-node, HederaConfig.java).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NETWORKS = ("mainnet", "testnet", "previewnet")
ACCOUNT, TOKEN, TOPIC, CONTRACT = "account", "token", "topic", "contract"
TRANSACTION = "transaction"
FIRST_USER_NUMBER = 1001

# How far from an id the name of a network is looked for, in characters: on its own line, and
# in the text before that line.
_NETWORK_ON_THE_LINE = 300
_NETWORK_BEFORE_THE_LINE = 200
# How far from an id the word for its kind is looked for.
_KIND_REACH = 60
# How many characters around an id are kept as "the words around it".
_KEPT_BEFORE = 80
_KEPT_AFTER = 60

# Not after a letter, a digit, a dot or an @: "v0.0.3", "1.0.0.3" and "sdk@0.0.5" are versions.
# Not before a letter, a digit or one more dotted number. The check word is optional.
_ID = re.compile(r"(?<![\w.@])0\.0\.(0|[1-9]\d{0,11})(?:-[a-z]{5})?(?!\w|\.\d)")
_NETWORK = re.compile(r"(?<![a-z])(main|test|preview)[ -]?net(?:work)?s?(?![a-z])", re.IGNORECASE)
_KIND_WORDS = {
    ACCOUNT: r"(?<![a-z])(?:account|wallet|operator|treasury)",
    TOKEN: r"(?<![a-z])(?:token|nfts?(?![a-z])|hts(?![a-z]))",
    TOPIC: r"(?<![a-z])(?:topic|hcs(?![a-z]))",
    CONTRACT: r"(?<![a-z])contract",
}
_KIND = re.compile(
    "|".join(f"(?P<{kind}>{words})" for kind, words in _KIND_WORDS.items()), re.IGNORECASE
)
# A link to HashScan: the network, what the thing is, and its id or address.
_HASHSCAN = re.compile(
    r"hashscan\.io/(mainnet|testnet|previewnet)/"
    r"(account|token|topic|contract|transaction|address)/"
    r"([0-9A-Za-z.@_-]+)",
    re.IGNORECASE,
)
_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
# A transaction: the account that paid, then the seconds and the nanoseconds of the moment it was
# sent, joined by "@" and "." or by two "-".
_TRANSACTION = re.compile(
    r"(?<![\w.@])0\.0\.([1-9]\d{0,11})(?:@(\d{1,11})\.(\d{1,9})|-(\d{1,11})-(\d{1,9}))(?!\w|\.\d)"
)
# What a HashScan link says the thing is. The payer of a transaction is an account. "address"
# is an address of the EVM kind, which can be an account or a contract.
_HASHSCAN_KINDS = {
    "account": ACCOUNT,
    "token": TOKEN,
    "topic": TOPIC,
    "contract": CONTRACT,
    "transaction": ACCOUNT,
    "address": None,
}


@dataclass(frozen=True)
class FoundId:
    """One id that a text gives, with what the text says about it."""

    entity_id: str  # 0.0.12345, or an EVM address that a HashScan link names
    network: str | None  # mainnet, testnet or previewnet. None when the text leaves it open.
    said_kind: str | None  # account, token, topic or contract. None when nothing near it says so.
    words_around: str  # the words around it, as they stand in the text
    in_hashscan_link: bool = False


def find_ids(*texts: str) -> list[FoundId]:
    """The ids that the texts give, in the order of their first place.

    One id is given once for each network that the texts name for it, or once with no network.
    """
    mentions: list[FoundId] = []
    for text in texts:
        mentions.extend(_mentions(text))
    return _merge(mentions)


def transaction_id(match: re.Match[str]) -> str | None:
    """A transaction as the mirror node asks for it, from a match of _TRANSACTION. In the form
    with a dot, the digits after the dot are the start of the nanoseconds."""
    account = int(match.group(1))
    if account < FIRST_USER_NUMBER:
        return None
    if match.group(2) is not None:
        seconds, nanos = match.group(2), match.group(3).ljust(9, "0")
    else:
        seconds, nanos = match.group(4), match.group(5)
    return f"0.0.{account}-{int(seconds)}-{int(nanos)}"


def _mentions(text: str) -> list[FoundId]:
    found: list[tuple[int, FoundId]] = []
    links: list[tuple[int, int]] = []
    for link in _HASHSCAN.finditer(text):
        network = link.group(1).lower()
        kind = _HASHSCAN_KINDS[link.group(2).lower()]
        target = link.group(3).rstrip(".-_")  # a full stop after a link is not part of it
        links.append(link.span())
        inner = _ID.match(target)
        if _EVM_ADDRESS.match(target):
            entity = target.lower()
        elif inner and int(inner.group(1)) >= FIRST_USER_NUMBER:
            entity = f"0.0.{inner.group(1)}"
        else:
            continue
        words = _kept(text, *link.span())
        found.append((link.start(3), FoundId(entity, network, kind, words, True)))
        transaction = (
            _TRANSACTION.fullmatch(target) if link.group(2).lower() == "transaction" else None
        )
        if transaction and (exact := transaction_id(transaction)):
            found.append((link.start(3), FoundId(exact, network, TRANSACTION, words, True)))
    payers: set[int] = set()  # where a transaction starts: the account there paid for it
    for match in _TRANSACTION.finditer(text):
        start, end = match.span()
        payers.add(start)
        exact = transaction_id(match)
        if exact is None or any(left <= start < right for left, right in links):
            continue  # a link has already said it
        mention = FoundId(
            exact, _said_network(text, start, end), TRANSACTION, _kept(text, start, end)
        )
        found.append((start, mention))
    ids = [match for match in _ID.finditer(text)]
    spans = [match.span() for match in ids]
    for match in ids:
        start, end = match.span()
        if int(match.group(1)) < FIRST_USER_NUMBER:
            continue  # a number of the network itself, or a version number
        if any(left <= start < right for left, right in links):
            continue  # the link has already said it, and said it exactly
        others = [span for span in spans if span != (start, end)]
        mention = FoundId(
            f"0.0.{match.group(1)}",
            _said_network(text, start, end),
            ACCOUNT if start in payers else _said_kind(text, start, end, others),
            _kept(text, start, end),
        )
        found.append((start, mention))
    return [mention for _, mention in sorted(found, key=lambda item: item[0])]


def _line(text: str, start: int, end: int) -> tuple[int, int]:
    """Where the line of text[start:end] starts and ends."""
    line_end = text.find("\n", end)
    return text.rfind("\n", 0, start) + 1, len(text) if line_end == -1 else line_end


def _said_network(text: str, start: int, end: int) -> str | None:
    """The one network that the words near the id name. None when they name none, or two."""
    line_start, line_end = _line(text, start, end)
    left = max(line_start, start - _NETWORK_ON_THE_LINE)
    right = min(line_end, end + _NETWORK_ON_THE_LINE)
    named = {f"{word.group(1).lower()}net" for word in _NETWORK.finditer(text, left, right)}
    if not named:
        before = max(0, line_start - _NETWORK_BEFORE_THE_LINE)
        named = {
            f"{word.group(1).lower()}net" for word in _NETWORK.finditer(text, before, line_start)
        }
    return named.pop() if len(named) == 1 else None


def _said_kind(text: str, start: int, end: int, others: list[tuple[int, int]]) -> str | None:
    """What the word next to the id says it is: the last word before it on its line, or else the
    first word after it. A word that another id separates from this id is not counted."""
    line_start, line_end = _line(text, start, end)
    last_id_before = max((right for _, right in others if right <= start), default=0)
    left = max(line_start, start - _KIND_REACH, last_id_before)
    before = list(_KIND.finditer(text, left, start))
    if before:
        return before[-1].lastgroup
    next_id_after = min((left for left, _ in others if left >= end), default=len(text))
    after = _KIND.search(text, end, min(line_end, end + _KIND_REACH, next_id_after))
    return after.lastgroup if after else None


def _kept(text: str, start: int, end: int) -> str:
    piece = text[max(0, start - _KEPT_BEFORE) : min(len(text), end + _KEPT_AFTER)]
    return " ".join(piece.split())


def _merge(mentions: list[FoundId]) -> list[FoundId]:
    """One record for each id and network. A place that names the network, the kind or a
    HashScan link tells more than a place that does not, so its words are the ones kept."""
    order: list[str] = []
    by_entity: dict[str, list[FoundId]] = {}
    for mention in mentions:
        if mention.entity_id not in by_entity:
            order.append(mention.entity_id)
        by_entity.setdefault(mention.entity_id, []).append(mention)
    merged: list[FoundId] = []
    for entity in order:
        places = by_entity[entity]
        networks = list(dict.fromkeys(p.network for p in places if p.network))
        for network in networks or [None]:
            here = [p for p in places if p.network == network] if network else places
            # The most telling place first: a link, then a place that says what the thing is.
            best = min(here, key=lambda p: (not p.in_hashscan_link, p.said_kind is None))
            kind = best.said_kind or next((p.said_kind for p in places if p.said_kind), None)
            merged.append(FoundId(entity, network, kind, best.words_around, best.in_hashscan_link))
    return merged
