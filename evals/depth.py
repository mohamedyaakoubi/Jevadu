"""Depth of use, first measure (design 13.9, 25 October 2026).

    python -m evals.depth              the counts over the collection
    python -m evals.depth --check 20   and a second counting of 20 projects, drawn at random

What the ledger tells about the use of Hedera beyond "this ID exists, made during the event", for
every project whose card shows a depth of use (check/depth.py): how many projects' own IDs took
transactions with accounts that their page does not name, how many have tokens held by such
accounts, on how many days they were active, and each sign that stays on paper. Counts only, each
share with its range by project.

What the page alone does not say (29 October 2026): for how many projects the ledger or the code
shows something that a reader of the page would miss: its IDs used a Hedera service that its page
does not name, its page names a service that its IDs did not use in the time of the table, its only
proof is in its code, a sign stays on paper, or the ID of its page does not fit the event. A
project with no depth of use has nothing to read on the ledger, so it can have none of these.

A check of the counting (--check): for projects drawn at random among those with transactions in
the time of the table, the transactions of their own IDs in that time, and the accounts that took
part, are counted a second time by a plain reading of the mirror node's lists, apart from the
tool's code (its client, its histories and its tables). The two countings must agree. A program
that counts is checked by another way of counting, not by itself (design 13.1). A project whose
history the limit of 2,000 events cut is left out of the draw: its counts are known to be low.

It writes evals/results/<UTC time>-depth.json: numbers only, and the projects by their number in
the database, never a text of their page.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import requests

from evals.test1.report import Counts, share
from hackathon_memory import __version__
from hackathon_memory.check.history import NETWORK_ACCOUNTS
from hackathon_memory.check.proof import ANOTHER_KIND, DATES_DO_NOT_FIT, PROOF_FOUND
from hackathon_memory.check.story import time_of
from hackathon_memory.hedera.mirror import MIRROR_URLS
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, SCHEDULE, TOKEN, TOPIC, TRANSACTION
from hackathon_memory.settings import Settings
from hackathon_memory.web.data import project_card

RESULTS = Path(__file__).parent / "results"
SEED = 20261025
PAUSE = 0.25  # seconds between two questions of the plain reading
MANY_DAYS = 3
# Each sign that stays on paper, by the words of its sentence (check/depth.py).
SIGNS = {
    "topic_with_no_message": "has no message",
    "contract_never_called": "was never called after its deployment",
    "token_held_only_by_its_own": "is held only by accounts that the project names",
    "token_held_by_nobody": "No account holds its token",
    "accounts_only_moved_hbar": "only moved HBAR",
    "package_with_no_call": "names a Hedera package, and calls no Hedera service",
    "no_id_of_its_own": "has no ID of its own",
}
# What "How they are set up" says, by the words of its sentences (check/setup.py, 28 October 2026).
SETUP = {
    "token_with_custom_fees": ("royalty of", "a fee of", "fixed fee"),
    "token_with_no_key": ("no key, so nobody can change it",),
    "topic_with_a_submit_key": ("submit key",),
    "topic_with_a_fee": ("a fee for each message", "each message pays a fee"),
    "account_with_an_ecdsa_key": ("ECDSA key",),
    "account_with_several_keys": ("several keys",),
}


# What the ledger and the code show that the page alone does not say (29 October 2026).
MISSES = (
    "used_a_service_the_page_does_not_name",
    "named_a_service_with_no_transaction",
    "proof_only_in_the_code",
    "a_sign_on_paper",
    "the_page_id_does_not_fit",
)


def what_the_page_misses(proof: str, card: object) -> set[str]:
    """The reasons for which the ledger or the code of one project shows something that its page
    alone does not say (MISSES)."""
    story = getattr(card, "story", None)
    facts = getattr(card, "facts", None)
    found = {
        "used_a_service_the_page_does_not_name": bool(getattr(story, "seen_not_named", ())),
        "named_a_service_with_no_transaction": bool(getattr(story, "named_not_seen", ())),
        "proof_only_in_the_code": bool(getattr(facts, "proven_by_code_only", False)),
        "a_sign_on_paper": bool(card.depth.on_paper),  # type: ignore[attr-defined]
        "the_page_id_does_not_fit": proof in (DATES_DO_NOT_FIT, ANOTHER_KIND),
    }
    return {key for key, yes in found.items() if yes}


def cards(conninfo: str, model: str) -> list[tuple[int, str, object]]:
    """Every project with a depth of use: its number, its proof status and its card."""
    with psycopg.connect(conninfo) as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM projects ORDER BY id")]
    found = []
    for project_id in ids:
        card = project_card(conninfo, project_id, model=model, version=INSTRUCTIONS_VERSION)
        if card is not None and card.depth is not None:
            found.append((project_id, card.facts.proof_status or "", card))
    return found


def one_share(rows: Sequence[bool]) -> dict:
    return share(Counts(tuple(int(row) for row in rows), tuple(1 for _ in rows)))


def measure(found: Sequence[tuple[int, str, object]]) -> dict:
    """The counts, over every project with a depth of use and over those with a proof found."""
    result: dict = {}
    for name, chosen in (("all", found), ("proof_found", [one for one in found
                                                          if one[1] == PROOF_FOUND])):  # fmt: skip
        depths = [card.depth for _, _, card in chosen]
        active = [depth for depth in depths if depth.did]
        signs = Counter()
        for depth in depths:
            for key, words in SIGNS.items():
                signs[key] += any(words in sentence for sentence in depth.on_paper)
        setup = Counter()
        for depth in depths:
            for key, all_words in SETUP.items():
                setup[key] += any(words in sentence for sentence in depth.setup
                                  for words in all_words)  # fmt: skip
        stories = [getattr(card, "story", None) for _, _, card in chosen]
        reached = Counter()
        for story in stories:
            lines = [line for line in story.lines if line.from_contracts] if story else []
            for line in lines:
                reached[line.service] += 1
            for words in story.contract_others if story else ():
                reached[words.split(" in ")[0]] += 1
        result[name] = {
            "projects": len(depths),
            "read_with_what_each_transaction_was": sum(depth.read for depth in depths),
            "with_transactions_in_the_time": len(active),
            "others_took_part": one_share([bool(depth.others) for depth in active]),
            "tokens_held_by_others": one_share([bool(depth.held_by_others) for depth in active]),
            "active_on_3_days_or_more": one_share([depth.days >= MANY_DAYS for depth in active]),
            "with_a_failed_transaction": one_share([bool(depth.failed) for depth in active]),
            "with_a_sign_on_paper": one_share([bool(depth.on_paper) for depth in depths]),
            "signs_on_paper": dict(signs),
            # the three reads of 28 October 2026 (design 7.5)
            "with_a_setup_said": sum(bool(depth.setup) for depth in depths),
            "setup": dict(setup),
            "contracts_reached_a_system_contract": sum(
                bool(story and (any(line.from_contracts for line in story.lines)
                                or story.contract_others)) for story in stories),
            "reached": dict(reached),
            "mainnet": sum(bool(getattr(getattr(card, "facts", None), "mainnet", False))
                           for _, _, card in chosen),
            "the_page_alone_misses": misses_of(chosen),
        }  # fmt: skip
    result["per_project"] = [
        {"project": pid, "proof": proof, "transactions": card.depth.total,
         "others": card.depth.others,
         "held_by_others": card.depth.held_by_others, "days": card.depth.days,
         "signs": [key for key, words in SIGNS.items()
                   if any(words in one for one in card.depth.on_paper)]}
        for pid, proof, card in found
    ]  # fmt: skip
    return result


def misses_of(chosen: Sequence[tuple[int, str, object]]) -> dict[str, int]:
    """How many projects show something that their page alone does not say, in all and for each
    reason."""
    each = [what_the_page_misses(proof, card) for _, proof, card in chosen]
    return {"any": sum(bool(reasons) for reasons in each),
            **{key: sum(key in reasons for reasons in each) for key in MISSES}}  # fmt: skip


# ---------------------------------------------------------------------------- a second counting


def plain_rows(session: requests.Session, network: str, path: str, key: str) -> list[dict]:
    """Every row of one of the mirror node's lists, page by page, with requests and nothing of
    the tool's client."""
    rows: list[dict] = []
    url = f"{MIRROR_URLS[network]}/api/v1{path}"
    while url:
        time.sleep(PAUSE)
        answer = session.get(url, timeout=30)
        if answer.status_code == 404:
            return rows
        answer.raise_for_status()
        body = answer.json()
        rows += body.get(key) or []
        following = (body.get("links") or {}).get("next")
        url = f"{MIRROR_URLS[network]}{following}" if following else ""
    return rows


def ledger_ids(conninfo: str, card: object) -> dict[tuple[str, str], str]:
    """The ID that the ledger gives each own ID of a card, such as 0.0.123 for an EVM address:
    the mirror node's list of transactions takes an account by that ID only."""
    with psycopg.connect(conninfo) as conn:
        return {(entity, network): ledger_id for entity, network, ledger_id in conn.execute(
            "SELECT entity_id, network, ledger_id FROM ledger_facts WHERE entity_id = ANY(%s)",
            ([one.entity_id for one in card.story.ids],)) if ledger_id}  # fmt: skip


def recount(
    session: requests.Session, card: object, ids: dict[tuple[str, str], str]
) -> tuple[int, set[str]]:
    """The transactions of a project's own IDs in the time of the table, each moment once, and
    the accounts that paid or took part, counted by a plain reading of the mirror node. `ids`
    gives the ledger's ID of an own ID that the page names by its EVM address."""
    story = card.story
    span = time_of(card.facts.event_starts_at, card.facts.event_ends_on)
    window = f"timestamp=gte:{span[0].timestamp():.9f}&timestamp=lte:{span[1].timestamp():.9f}"

    def inside(stamp: str) -> bool:
        return span[0].timestamp() <= float(stamp) <= span[1].timestamp()

    moments: set[str] = set()
    accounts: set[str] = set()
    for one in story.ids:
        if one.asked_at is None:
            continue
        entity, network = ids.get((one.entity_id, one.network), one.entity_id), one.network
        if one.kind == TOPIC:
            for row in plain_rows(session, network, f"/topics/{entity}/messages?limit=100&"
                                  f"{window}", "messages"):  # fmt: skip
                moments.add(row["consensus_timestamp"])
                accounts.add(row.get("payer_account_id") or "")
        elif one.kind == CONTRACT:
            for row in plain_rows(session, network, f"/contracts/{entity}/results?limit=100&"
                                  f"{window}", "results"):  # fmt: skip
                moments.add(row["timestamp"])
                accounts.add(_account_of(row.get("from")))
        elif one.kind == ACCOUNT:
            for row in plain_rows(session, network, f"/transactions?account.id={entity}&"
                                  f"limit=100&{window}", "transactions"):  # fmt: skip
                moments.add(row["consensus_timestamp"])
                accounts |= accounts_of(row)
        elif one.kind == TOKEN:
            time.sleep(PAUSE)
            answer = session.get(f"{MIRROR_URLS[network]}/api/v1/tokens/{entity}", timeout=30)
            body = answer.json() if answer.status_code == 200 else {}
            if body.get("created_timestamp") and inside(body["created_timestamp"]):
                moments.add(body["created_timestamp"])
                accounts.add(body.get("treasury_account_id") or "")
            if body.get("type") == "NON_FUNGIBLE_UNIQUE":
                for row in plain_rows(session, network, f"/tokens/{entity}/nfts?limit=100",
                                      "nfts"):  # fmt: skip
                    if inside(row["created_timestamp"]):
                        moments.add(row["created_timestamp"])
                        accounts.add(row.get("account_id") or "")
        elif one.kind == SCHEDULE:
            time.sleep(PAUSE)
            answer = session.get(f"{MIRROR_URLS[network]}/api/v1/schedules/{entity}", timeout=30)
            body = answer.json() if answer.status_code == 200 else {}
            for key in ("consensus_timestamp", "executed_timestamp"):
                if body.get(key) and inside(body[key]):
                    moments.add(body[key])
                    accounts.update({body.get("payer_account_id") or "",
                                     body.get("creator_account_id") or ""})  # fmt: skip
        elif one.kind == TRANSACTION:
            time.sleep(PAUSE)
            answer = session.get(f"{MIRROR_URLS[network]}/api/v1/transactions/{entity}",
                                 timeout=30)  # fmt: skip
            items = (answer.json() if answer.status_code == 200 else {}).get("transactions") or []
            parent = next((item for item in items if not item.get("nonce")), None)
            if parent and inside(parent["consensus_timestamp"]):
                moments.add(parent["consensus_timestamp"])
                accounts |= accounts_of(parent)
    accounts -= NETWORK_ACCOUNTS | {""}
    return len(moments), accounts


def accounts_of(transaction: dict) -> set[str]:
    """The accounts of one transaction of the mirror node: the one that paid, and those of its
    transfers of HBAR, tokens and NFTs, without the node that took it."""
    accounts = {str(transaction.get("transaction_id") or "").split("-", 1)[0]}
    for part in (transaction.get("transfers") or []) + (transaction.get("token_transfers") or []):
        accounts.add(str(part.get("account") or ""))
    for part in transaction.get("nft_transfers") or []:
        accounts.update(str(part.get(side) or "") for side in
                        ("sender_account_id", "receiver_account_id"))  # fmt: skip
    accounts.discard(str(transaction.get("node") or ""))
    return accounts


def _account_of(address: object) -> str:
    text = str(address or "").lower()
    if text.startswith("0x" + "0" * 24):
        return f"0.0.{int(text[26:], 16)}"
    return text


def check(found: Sequence[tuple[int, str, object]], conninfo: str, size: int) -> dict:
    """The second counting of `size` projects drawn at random, and how often it agrees."""
    drawable = [one for one in found if one[2].depth.did and one[2].depth.strip is not None
                and one[2].story is not None and not one[2].story.cut]  # fmt: skip
    drawn = random.Random(SEED).sample(drawable, min(size, len(drawable)))  # noqa: S311
    session = requests.Session()
    session.headers["User-Agent"] = f"HackathonMemory-research/{__version__} (evals.depth)"
    rows = []
    for pid, _, card in drawn:
        with psycopg.connect(conninfo) as conn:
            rows_named = conn.execute(
                "SELECT DISTINCT entity_id FROM hedera_ids WHERE project_id = %s", (pid,)
            ).fetchall()
        named = {row[0] for row in rows_named}
        tool_count = card.depth.total
        plain_count, accounts = recount(session, card, ledger_ids(conninfo, card))
        plain_others = len(accounts - named)
        rows.append({"project": pid, "tool_transactions": tool_count,
                     "plain_transactions": plain_count, "tool_others": card.depth.others,
                     "plain_others": plain_others})  # fmt: skip
    agree = [row["tool_transactions"] == row["plain_transactions"]
             and row["tool_others"] == row["plain_others"] for row in rows]  # fmt: skip
    return {"drawn": len(rows), "of": len(drawable), "seed": SEED,
            "both_agree": one_share(agree), "rows": rows}  # fmt: skip


def main(argv: Sequence[str]) -> int:
    size = int(argv[argv.index("--check") + 1]) if "--check" in argv else 0
    settings = Settings()
    conninfo = settings.database_conninfo()
    found = cards(conninfo, settings.gemini_rewrite_model)
    now = datetime.now(UTC)
    result = {"test": "depth", "made_on": now.date().isoformat(), **measure(found)}
    if size:
        result["second_counting"] = check(found, conninfo, size)
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-depth.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    every, proven = result["all"], result["proof_found"]
    print(f"Projects with a depth of use: {every['projects']} (read with what each transaction "
          f"was: {every['read_with_what_each_transaction_was']}); with transactions in the time: "
          f"{every['with_transactions_in_the_time']}. Others took part: "
          f"{every['others_took_part']}. Among those with a proof found: "
          f"{proven['others_took_part']}. Signs on paper: {every['signs_on_paper']}.")  # fmt: skip
    if size:
        print(f"Second counting: {result['second_counting']['both_agree']}.")
    print(f"Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
