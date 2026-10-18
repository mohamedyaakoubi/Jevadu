"""The public register on Hedera (design 9.2 to 9.5, screen S4): the record of one submission,
written to the tool's topic, read back from the mirror node, and found again at any event.

The record is the fixed form of design 9.3, version 2, in compact JSON, and nothing else:

    {"v":2,"event":"ethglobal.com/prague","code":"<64 hex>","commit":"<40 hex>"}
    {"v":2,"event":"days/2026-10-01/2026-10-20","code":"<64 hex>","commit":"<40 hex>",
     "account":"<64 hex>"}

Version 1 had no "commit"; none was ever written, because the topic did not exist yet.

* "code" is the SHA-256 of the link of the repository, in the one spelling of collect/github.py.
  The link itself is never written: it holds the name of its owner, and a message can never be
  deleted (design rule 8). Anybody can compute the fingerprint again from the link and find its
  records.
* "commit" is the ID of the newest commit of the repository when it was checked
  (collect/github_commits.py): it is computed from every file of that version, so the record
  says which code existed at that time, and not only which address. A repository that is later
  deleted or made private keeps this proof; only a copy of the code can show it again.
* "account" is the SHA-256 of the team's Hedera account, only when the team gives one.
* "event" names the event by its site and its short name, or, for an event that the collection
  does not hold, by its first and its last day.

The topic has no admin key and one submit key, the tool's own (design 9.5): only the tool can
write, and nobody can delete the register or change its rules. It lives on the test network in
the first version (hedera/register.py, require_testnet).

    python -m hackathon_memory.hedera.registry open

creates the topic once, checks its keys on the mirror node, and says which line to put in .env.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

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
    when,
)
from hackathon_memory.hedera.register import MessageSubmitted, RegisterError
from hackathon_memory.settings import Settings

VERSION = 2
MAX_RECORD = 384  # bytes; one message holds 1,024, and the record must stay far below (design 9.3)
PAGE = 100  # messages asked for at once
MAX_PAGES = 50  # 5,000 registrations; more would need another way to find a fingerprint
_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_EVENT = re.compile(r"^(?:[a-z0-9.-]+/[a-z0-9._-]+|days/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2})$")
_ACCOUNT = re.compile(r"^0\.0\.[1-9]\d{0,11}$")

Write = Callable[[bytes], MessageSubmitted]


def code_fingerprint(repository: str) -> str:
    """The fingerprint of a repository: the SHA-256 of its link in the one spelling."""
    return hashlib.sha256(repository.encode("utf-8")).hexdigest()


def account_of(text: str) -> str | None:
    """A Hedera account as a person typed it, such as 0.0.12345, or None when it is not one."""
    text = text.strip()
    return text if _ACCOUNT.match(text) else None


def account_fingerprint(account: str) -> str:
    return hashlib.sha256(account.encode("utf-8")).hexdigest()


def event_key(site: str, slug: str) -> str:
    return f"{site}/{slug}"


def days_key(first: date, last: date) -> str:
    return f"days/{first.isoformat()}/{last.isoformat()}"


def readme_line(event: str, code: str) -> str:
    """The line that a team adds to its README before a registration (design 9.2). Only who can
    change the repository can add it, so it shows that the code is the team's, and that the team
    agrees to the record. It is made from the event and the fingerprint of the link, so it serves
    for this pair only."""
    digest = hashlib.sha256(f"{event}|{code}".encode()).digest()
    return f"hackathon-memory: {base64.b32encode(digest).decode()[:8]}"


def carries_line(text: str, line: str) -> bool:
    """Whether a README carries the line, with any spaces around its colon, in any case."""
    word, _, mark = line.partition(": ")
    found = re.search(rf"{re.escape(word)}\s*:\s*{re.escape(mark)}(?![A-Za-z0-9])", text,
                      re.IGNORECASE)  # fmt: skip
    return found is not None


def record(event: str, code: str, commit: str, account: str | None = None) -> bytes:
    """The bytes of the record. Refuses anything that is not the fixed form."""
    if (not _EVENT.match(event) or not _HEX.match(code) or not _COMMIT.match(commit)
            or (account and not _HEX.match(account))):  # fmt: skip
        raise RegisterError("The record holds only the event and fingerprints (design 9.3).")
    body = {"v": VERSION, "event": event, "code": code, "commit": commit}
    if account:
        body["account"] = account
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_RECORD:
        raise RegisterError(f"The record is {len(payload)} bytes; it must stay below {MAX_RECORD}.")
    return payload


@dataclass(frozen=True)
class Registration:
    """One record of the register, as the mirror node returns it."""

    sequence_number: int
    consensus_timestamp: str  # as the mirror node writes it: seconds.nanoseconds
    event: str
    code: str
    commit: str
    account: str | None

    @property
    def registered_at(self) -> datetime:
        return when(self.consensus_timestamp)

    def link(self, network: str) -> str:
        return hashscan_transaction(network, self.consensus_timestamp)


def read_record(message: dict) -> Registration | None:
    """A message of the topic as a registration, or None when it is not a record of this version."""
    try:
        body = json.loads(decode_message(message).decode("utf-8"))
        sequence, stamp = int(message["sequence_number"]), str(message["consensus_timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("v") != VERSION:
        return None
    event, code, account = body.get("event"), body.get("code"), body.get("account")
    commit = body.get("commit")
    parts = ((event, _EVENT), (code, _HEX), (commit, _COMMIT))
    parts_fit = all(isinstance(value, str) and pattern.match(value) for value, pattern in parts)
    account_fits = account is None or (isinstance(account, str) and bool(_HEX.match(account)))
    if not (parts_fit and account_fits):
        return None
    return Registration(sequence, stamp, event, code, commit, account)


def registrations(mirror: MirrorNode, topic_id: str) -> list[Registration]:
    """Every registration of the register, oldest first, read from the mirror node."""
    found: list[Registration] = []
    first = 1
    for _ in range(MAX_PAGES):
        page = mirror.topic_messages_from(topic_id, first, limit=PAGE)
        for message in page:
            registration = read_record(message)
            if registration is not None:
                found.append(registration)
        if len(page) < PAGE:
            break
        first = int(page[-1]["sequence_number"]) + 1
    return found


def register_submission(
    write: Write, mirror: MirrorNode, topic_id: str, payload: bytes, *, timeout: float = 30
) -> Registration:
    """Write the record, and read it back from the mirror node, which is a few seconds behind."""
    sent = write(payload)
    message = mirror.wait_for_message(topic_id, sent.sequence_number, timeout=timeout, interval=1)
    registration = read_record(message)
    if registration is None or decode_message(message) != payload:
        raise RegisterError("The mirror node returns another record than the one written.")
    return registration


def operator_key(settings: Settings, mirror: MirrorNode) -> PrivateKey:
    """The key of the tool's account, checked against the key that the ledger shows for it."""
    operator_id = settings.hedera_operator_id.strip()
    key_text = settings.hedera_operator_key.get_secret_value()
    if not operator_id or not key_text:
        raise RegisterError("HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY are empty in .env.")
    account = mirror.account(operator_id)
    if account is None:
        raise RegisterError(f"The account {operator_id} is not on the {mirror.network} network.")
    ledger_key = account.get("key") or {}
    try:
        key = load_operator_key(key_text, ledger_key.get("_type"))
    except OperatorKeyError as error:  # its words hold no part of the key
        raise RegisterError(str(error)) from None
    if not matches_ledger_key(key, ledger_key):
        raise RegisterError("The key in .env is not the key of the account HEDERA_OPERATOR_ID.")
    return key


def writer(settings: Settings, mirror: MirrorNode) -> Write:
    """What writes one record to the register, with the tool's account."""
    register.require_testnet(settings.hedera_network)
    topic_id = settings.hedera_topic_id.strip()
    if not topic_id:
        raise RegisterError("The register is not open: HEDERA_TOPIC_ID is empty in .env.")
    key = operator_key(settings, mirror)
    client = register.new_testnet_client(settings.hedera_operator_id.strip(), key)
    return lambda payload: register.submit_message(client, topic_id, payload)


def open_register(
    settings: Settings,
    mirror: MirrorNode,
    *,
    new_client: Callable[..., object] = register.new_testnet_client,
    create_topic: Callable[..., register.TopicCreated] = register.create_topic,
) -> str:
    """Create the topic of the register (design 9.5) and check its keys on the mirror node."""
    register.require_testnet(settings.hedera_network)
    if settings.hedera_topic_id.strip():
        raise RegisterError(f"The register is open already: {settings.hedera_topic_id.strip()}.")
    key = operator_key(settings, mirror)
    client = new_client(settings.hedera_operator_id.strip(), key)
    try:
        created = create_topic(client, key.public_key(), auto_renew=True)
    except RegisterError as error:
        if error.status != register.AUTORENEW_NOT_ALLOWED:
            raise
        # The older rule of the network: no auto-renew account without an admin key.
        created = create_topic(client, key.public_key(), auto_renew=False)
    topic = mirror.wait_for_topic(created.topic_id)
    submit = str((topic.get("submit_key") or {}).get("key", "")).lower()
    if topic.get("admin_key") is not None or submit != public_key_hex(key):
        raise RegisterError(
            f"The topic {created.topic_id} does not have the keys of design 9.5. Do not use it."
        )
    return created.topic_id


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["open"]:
        print(__doc__)
        return 2
    settings = Settings()
    try:
        topic_id = open_register(settings, MirrorNode(settings.hedera_network))
    except (RegisterError, MirrorError) as error:
        print(f"Not opened: {error}")
        return 1
    network = settings.hedera_network
    print(f"The register is open: topic {topic_id} on the {network} network.")
    print(f"It has no admin key and one submit key: {hashscan_topic(network, topic_id)}")
    print(f"Put this line in .env: HEDERA_TOPIC_ID={topic_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
