"""The review sheet of Test 1 (design 13.2): each page and its card side by side, for grading.

    python -m evals.test1.sheet                  writes the sheet into data/evals/test1, once
    python -m evals.test1.sheet --show N         prints the page of project N
    python -m evals.test1.sheet --show N --card  prints the card of project N

The sheet is one HTML file that needs no network: a grader opens it in a browser, grades each
project as guideline.md says, and saves the grades into the same folder. --show is for a grader
who reads in a terminal, in the same order: the page first, the card after. The folder holds the
texts of the pages and of the cards, so it stays on the maintainer's laptop, out of git (design
13.1).

What the program does, once:

* it takes the 60 pages of evals/sets/test1.json, the text that the model read, and the card of
  the model and the version of the instructions in use;
* it puts the projects in an order drawn with a fixed seed, so that the six groups are mixed;
* it picks the 10 projects of the parser check, with another fixed seed;
* it plants a few wrong fields, picked with a seed that is not kept, and writes them into a key
  that no grader opens before both are done (design 13.1);
* it finds each quote in the text, so that the sheet can show it there.

A sheet is never written over, because the grades belong to one sheet. To start again, delete
the folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION, Category
from hackathon_memory.read.quotes import FIELDS, KEPT
from hackathon_memory.read.quotes import place_of as quote_place
from hackathon_memory.read.sets import SetError, pages_of
from hackathon_memory.settings import Settings

TEST1 = Path(__file__).parent.parent / "sets" / "test1.json"
TEMPLATE = Path(__file__).parent / "sheet.html"
DATA_FILE = "sheet-data.json"
SHEET_FILE = "sheet.html"
KEY_FILE = "planted-key.json"
MAINTAINER_GRADES = "grades-maintainer.json"
SECOND_GRADES = "grades-second.json"
PLACEHOLDER = "__SHEET_DATA__"
ORDER_SEED = 20261014
PARSER_SEED = 20261015
PARSER_CHECKS = 10
FEWEST_PLANTS, MOST_PLANTS = 3, 6

FIELD_TITLES = {
    "what_it_does": ("What it does", "One plain sentence on what the project does."),
    "how_it_works": ("How it works", "Three to six short steps."),
    "for_whom": ("For whom", "Who uses it."),
    "hedera_services": (
        "Hedera services",
        "Which Hedera services the page says the project uses, and for what.",
    ),
    "category": ("Category", "One field of life, from the fixed list."),
    "problem": ("Problem", "The problem that the project solves."),
    "solution": ("Solution", "How the project solves it."),
}
# The network services that Hedera's library names (hiero-sdk-python 0.2.10, its gRPC services,
# read on 13 October 2026), with the mirror node and the Agent Kit, which pages name often.
SERVICES = (
    ("accounts", "Accounts and HBAR transfers", "accounts, HBAR payments, crypto transfers"),
    ("consensus", "Consensus Service", "HCS, topics, consensus messages"),
    ("token", "Token Service", "HTS, Hedera tokens, NFTs made with the token service"),
    ("contracts", "Smart contracts", "Solidity contracts on Hedera, the EVM of Hedera"),
    ("file", "File Service", "HFS, files stored on Hedera"),
    ("schedule", "Scheduled transactions", "the Schedule Service, scheduled transactions"),
    ("mirror", "Mirror node", "the mirror node, its REST API"),
    ("agent_kit", "Agent Kit", "the Hedera Agent Kit"),
    ("none", "None", "the page names no Hedera service as used"),
)

# What a planted field is made of. A text field gets the same field of a card outside the sheet,
# so that no grader meets its words twice. A service is swapped for one the page never names.
SWAPPED_FIELDS = ("what_it_does", "for_whom", "problem", "solution")
SERVICE_NAMES = {
    "consensus": ("Hedera Consensus Service", "Consensus Service", "HCS"),
    "token": ("Hedera Token Service", "Token Service", "HTS"),
    "file": ("Hedera File Service", "File Service", "HFS"),
}
SWAP, SERVICE, CATEGORY = "another project's words", "another service", "another category"


class SheetError(ValueError):
    """The sheet cannot be made, or would be written over."""


@dataclass(frozen=True)
class Block:
    kind: str  # name, short_line or section
    title: str
    text: str


@dataclass(frozen=True)
class Case:
    page: str
    blocks: tuple[Block, ...]
    card: dict  # the checked fields, as the table cards keeps them


def _blocks(name: str, short_line: str, sections: list) -> tuple[Block, ...]:
    blocks = [Block("name", "", name.strip()), Block("short_line", "", short_line.strip())]
    blocks += [Block("section", title.strip(), body.strip()) for title, body in sections]
    return tuple(block for block in blocks if block.text)


def cases_of(conninfo: str, pages: Sequence[str], model: str, version: str) -> list[Case]:
    """The page text and the card of every page of the set. Every page must have its card."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.page_url, p.name, p.short_line, "
            "coalesce(json_agg(json_build_array(coalesce(s.title, ''), s.body) "
            "ORDER BY s.position) FILTER (WHERE s.project_id IS NOT NULL), '[]'), c.fields "
            "FROM projects p JOIN cards c ON c.project_id = p.id "
            "AND c.model = %s AND c.instructions_version = %s "
            "LEFT JOIN sections s ON s.project_id = p.id "
            "WHERE p.page_url = ANY(%s) "
            "GROUP BY p.id, c.project_id, c.model, c.instructions_version",
            (model, version, list(pages)),
        ).fetchall()
    found = {
        page: Case(page, _blocks(name, short_line or "", sections), fields)
        for page, name, short_line, sections, fields in rows
    }
    missing = [page for page in pages if page not in found]
    if missing:
        raise SheetError(f"{len(missing)} page(s) of the set have no card of {model}, {version}")
    return [found[page] for page in pages]


def donor_fields(conninfo: str, pages: Sequence[str], model: str, version: str) -> list[dict]:
    """The fields of the cards of the same model and version that are not in the sheet."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT c.fields FROM cards c JOIN projects p ON p.id = c.project_id "
            "WHERE c.model = %s AND c.instructions_version = %s AND NOT p.page_url = ANY(%s) "
            "ORDER BY p.id",
            (model, version, list(pages)),
        ).fetchall()
    return [fields for (fields,) in rows]


def places(case: Case, quote: str) -> list[list[int]]:
    """Where a quote stands: [block, start, end] in the first block that holds it."""
    for number, block in enumerate(case.blocks):
        found = quote_place(quote, block.text)
        if found:
            return [[number, *found]]
    return []


def _named(text: str, names: Sequence[str]) -> bool:
    return any(re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE) for name in names)


def _service_swap(case: Case, rng: random.Random) -> dict | None:
    """The field of the services, with the one service it names swapped for one that the page
    never names; None when the field names no such service, or more than one."""
    field = case.card["hedera_services"]
    if field["state"] != KEPT:
        return None
    named = [key for key, names in SERVICE_NAMES.items() if _named(field["value"], names)]
    page = " ".join(block.text for block in case.blocks)
    unnamed = [key for key, names in SERVICE_NAMES.items() if not _named(page, names)]
    if len(named) != 1 or not unnamed:
        return None
    old, new = SERVICE_NAMES[named[0]], SERVICE_NAMES[rng.choice(unnamed)]
    value = field["value"]
    for before, after in zip(old, new, strict=True):  # the longest names first
        value = re.sub(rf"\b{re.escape(before)}\b", after, value, flags=re.IGNORECASE)
    return {**field, "value": value}


def plant(
    cases: list[Case], donors: list[dict], rng: random.Random
) -> tuple[list[Case], list[dict]]:
    """The cases with a few fields made wrong on purpose, and the key that names them."""
    count = rng.randint(FEWEST_PLANTS, MOST_PLANTS)
    planted: dict[int, tuple[str, dict, str]] = {}
    order = list(range(len(cases)))
    rng.shuffle(order)
    kinds = [SWAP, SERVICE, CATEGORY]
    for number in order:
        if len(planted) == count:
            break
        case = cases[number]
        rng.shuffle(kinds)
        for kind in kinds:
            made = _planted_field(case, kind, donors, rng)
            if made:
                planted[number] = made
                break
    if len(planted) < FEWEST_PLANTS:
        raise SheetError("too few fields could be planted")
    changed = list(cases)
    key = []
    for number, (name, field, kind) in sorted(planted.items()):
        case = cases[number]
        changed[number] = Case(case.page, case.blocks, {**case.card, name: field})
        key.append({"page": case.page, "field": name, "kind": kind})
    return changed, key


def _planted_field(
    case: Case, kind: str, donors: list[dict], rng: random.Random
) -> tuple[str, dict, str] | None:
    if kind == SERVICE:
        field = _service_swap(case, rng)
        return ("hedera_services", field, kind) if field else None
    if kind == CATEGORY:
        field = case.card["category"]
        if field["state"] != KEPT:
            return None
        others = [c.value for c in Category if c.value not in (field["value"], "Other")]
        return "category", {**field, "value": rng.choice(others)}, kind
    names = [name for name in SWAPPED_FIELDS if case.card[name]["state"] == KEPT]
    rng.shuffle(names)
    for name in names:
        own = case.card[name]["value"]
        given = [d[name]["value"] for d in donors if d[name]["state"] == KEPT]
        given = [value for value in given if value and value != own]
        if given:
            return name, {**case.card[name], "value": rng.choice(given)}, kind
    return None


def _card(case: Case) -> dict:
    card = {}
    for name in FIELDS:
        field = case.card[name]
        card[name] = {
            "label": field["label"],
            "state": field["state"],
            "value": field["value"],
            "quotes": [{"text": q, "at": places(case, q)} for q in field["quotes"]],
            "removed": field["removed"],
        }
    return card


def build(
    cases: list[Case],
    *,
    donors: list[dict],
    model: str,
    version: str,
    grades_file: str,
    rng: random.Random | None = None,
) -> tuple[dict, dict]:
    """The data of the sheet, and the key of its planted fields."""
    planted, key = plant(cases, donors, rng or secrets.SystemRandom())
    ordered = sorted(planted, key=lambda case: case.page)
    # The order and the parser checks must be the same at every run, not secret: fixed seeds.
    random.Random(ORDER_SEED).shuffle(ordered)  # noqa: S311
    every_page = sorted(case.page for case in cases)
    drawn = random.Random(PARSER_SEED).sample(every_page, min(PARSER_CHECKS, len(cases)))  # noqa: S311
    checks = set(drawn)
    made_on = datetime.now(UTC).strftime("%Y-%m-%d")
    data = {
        "sheet": "test1",
        "made_on": made_on,
        "model": model,
        "instructions_version": version,
        "set_file": "evals/sets/test1.json",
        "order_seed": ORDER_SEED,
        "parser_seed": PARSER_SEED,
        "grades_file": grades_file,
        "fields": [{"name": n, "title": t, "help": h} for n, (t, h) in FIELD_TITLES.items()],
        "categories": [category.value for category in Category],
        "services": [{"key": k, "title": t, "words": w} for k, t, w in SERVICES],
        "cases": [
            {
                "number": number,
                "page": case.page,
                "parser_check": case.page in checks,
                "blocks": [vars(block) for block in case.blocks],
                "card": _card(case),
            }
            for number, case in enumerate(ordered, start=1)
        ],
    }
    data["fingerprint"] = fingerprint(data)
    return data, {"made_on": made_on, "sheet": data["fingerprint"], "plants": key}


def fingerprint(data: dict) -> str:
    """The fingerprint of the data of a sheet, without its own fingerprint."""
    rest = {name: value for name, value in data.items() if name != "fingerprint"}
    text = json.dumps(rest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_sheet(folder: Path, data: dict, key: dict, template: Path = TEMPLATE) -> Path:
    """Writes the data, the key and the sheet. Never writes over a sheet."""
    if (folder / DATA_FILE).exists():
        raise SheetError(f"a sheet is already in {folder.as_posix()}: delete the folder first")
    page = template.read_text(encoding="utf-8")
    if page.count(PLACEHOLDER) != 1:
        raise SheetError("the template of the sheet has no single place for its data")
    embedded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    folder.mkdir(parents=True, exist_ok=True)
    for name, record in ((DATA_FILE, data), (KEY_FILE, key)):
        text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
    sheet = folder / SHEET_FILE
    sheet.write_text(page.replace(PLACEHOLDER, embedded), encoding="utf-8", newline="\n")
    return sheet


def show(folder: Path, number: int, *, card: bool) -> int:
    """Prints the page or the card of one project of the sheet, for a grader in a terminal."""
    data = json.loads((folder / DATA_FILE).read_text(encoding="utf-8"))
    cases = data["cases"]
    if not 1 <= number <= len(cases):
        print(f"There are {len(cases)} projects: give a number from 1 to {len(cases)}.")
        return 2
    case = cases[number - 1]
    check = "yes" if case["parser_check"] else "no"
    print(f"== {number} of {len(cases)}: {case['page']}  (parser check: {check})")
    if not card:
        for block in case["blocks"]:
            print(f"-- {block['title'] or block['kind'].replace('_', ' ')}")
            print(block["text"])
        return 0
    titles = {field["name"]: field["title"] for field in data["fields"]}
    for name, field in case["card"].items():
        state = field["state"].replace("_", " ")
        print(f"-- {titles[name]}  [{field['label'].replace('_', ' ')}, {state}]")
        value = field["value"]
        if isinstance(value, list):
            for step, text in enumerate(value, start=1):
                print(f"  {step}. {text}")
        else:
            print(value or "(empty)")
        for quote in field["quotes"]:
            print(f"   quote: {quote['text']}")
        if field["removed"]:
            print(f"   ({field['removed']} quote(s) removed by the check)")
    return 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.test1.sheet",
        description="Writes the review sheet of Test 1, once, or prints one of its projects.",
    )
    parser.add_argument("--show", type=int, metavar="N", help="print the page of project N")
    parser.add_argument("--card", action="store_true", help="with --show: print its card")
    arguments = parser.parse_args(argv)
    settings = Settings()
    folder = Path(settings.data_dir) / "evals" / "test1"
    if arguments.show is not None:
        return show(folder, arguments.show, card=arguments.card)
    if arguments.card:
        parser.error("--card goes with --show N")
    model = settings.gemini_rewrite_model
    try:
        pages = pages_of(TEST1)
        conninfo = settings.database_conninfo()
        cases = cases_of(conninfo, pages, model, INSTRUCTIONS_VERSION)
        data, key = build(
            cases,
            donors=donor_fields(conninfo, pages, model, INSTRUCTIONS_VERSION),
            model=model,
            version=INSTRUCTIONS_VERSION,
            grades_file=str((folder / MAINTAINER_GRADES).resolve()),
        )
        sheet = write_sheet(folder, data, key)
    except (SetError, SheetError) as error:
        print(f"Stopped: {error}")
        return 1
    checks = sum(case["parser_check"] for case in data["cases"])
    print(f"Written: {sheet.as_posix()} ({len(cases)} projects, {checks} parser checks).")
    print(f"A few fields are planted. Their key is {KEY_FILE}: no grader opens it before both")
    print("have graded.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
