"""Test 3 (design 13.4): the three numbers, from the hand answers and the tool's tables.

    python -m evals.test3.run

It reads data/evals/test3/answers.json, where the person wrote the IDs of each page as
guideline.md says, and the IDs that the tool found, with the status that it gave each one. For
each page that is checked: the IDs of the hand check that the tool found in the same place
(found), the IDs of the tool that the hand check does not count (invented), and, for the IDs that
both found, whether the two statuses are the same (status). Each number has its range by project,
computed as in Test 1.

Three planted IDs, which stand in no text, are added to the answers of three checked pages, drawn
with a fixed seed: the script must count them as missed. They are shown apart, and left out of
the numbers.

It writes evals/results/<UTC time>-test3.json: the numbers, and for each page its address and its
IDs, where they stand and their two statuses. An ID is a fact of the ledger, not a text of a page.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from evals.test1.report import Counts, share
from hackathon_memory.check.proof import ORDER
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent.parent / "results"
PASS_MARKS = {"found": 0.95, "invented": 0.02, "status": 0.90}  # fixed on 9 October 2026
PLANTED, PLANT_SEED = 3, 20261019
PLANTED_ID = ("page", "0.0.999999999")  # stands in no text of the set
NOT_CHECKED = "not checked"
_AT = re.compile(r"(0\.0\.\d+)@(\d+)\.(\d+)")
_DASHES = re.compile(r"(0\.0\.\d+)-(\d+)-(\d+)")


def key(entity: str) -> str:
    """One spelling of an ID: lower case, and a transaction in the form with dashes, its
    nanoseconds in nine digits. After "@" they are the decimals of a second, so zeros are added
    on the right; after a dash they are a whole number, so "58986056" is "058986056"."""
    entity = entity.strip().lower()
    found = _AT.fullmatch(entity)
    if found:
        return f"{found.group(1)}-{found.group(2)}-{found.group(3).ljust(9, '0')}"
    found = _DASHES.fullmatch(entity)
    if found:
        return f"{found.group(1)}-{found.group(2)}-{found.group(3).zfill(9)}"
    return entity


def best(statuses: list[str | None]) -> str:
    """The status that counts for an ID asked on more than one network: the best one."""
    known = [one for one in statuses if one in ORDER]
    return min(known, key=ORDER.index) if known else NOT_CHECKED


def tool_ids(conninfo: str, project_id: int) -> dict[tuple[str, str], str]:
    """(where, ID) -> the status that the tool gives it."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT h.found_in, h.entity_id, c.status FROM hedera_ids h "
            "LEFT JOIN id_checks c ON c.hedera_id = h.id WHERE h.project_id = %s", (project_id,)
        ).fetchall()  # fmt: skip
    statuses: dict[tuple[str, str], list[str | None]] = {}
    for where, entity, status in rows:
        statuses.setdefault((where, key(entity)), []).append(status)
    return {place: best(found) for place, found in statuses.items()}


def page_counts(hand: dict[tuple[str, str], str], tool: dict[tuple[str, str], str]) -> dict:
    """The counts of one page: found of the hand IDs, invented of the tool IDs, the same status
    of the IDs that both found."""
    both = [place for place in hand if place in tool]
    return {
        "found": (len(both), len(hand)),
        "invented": (sum(place not in hand for place in tool), len(tool)),
        "status": (sum(hand[place] == tool[place] for place in both), len(both)),
    }


def planted_pages(pages: Sequence[str], seed: int = PLANT_SEED) -> list[str]:
    """The checked pages that get a planted ID."""
    return sorted(random.Random(seed).sample(sorted(pages), min(PLANTED, len(pages))))  # noqa: S311


def numbers(per_page: list[dict]) -> dict:
    """Each number with its range by project (Test 1's way, evals/test1/report.py)."""
    found = {}
    for name in PASS_MARKS:
        counts = Counts(tuple(page[name][0] for page in per_page),
                        tuple(page[name][1] for page in per_page))  # fmt: skip
        found[name] = share(counts)
    return found


def main(argv: Sequence[str]) -> int:
    del argv
    settings = Settings()
    answers = json.loads(
        (Path(settings.data_dir) / "evals" / "test3" / "answers.json").read_text(encoding="utf-8")
    )
    conninfo = settings.database_conninfo()
    checked = [page for page in answers if page.get("checked")]
    planted = set(planted_pages([page["page"] for page in checked]))
    per_page, details, caught = [], [], 0
    for page in checked:
        hand = {(one["where"], key(one["id"])): one["status"] for one in page["ids"]}
        tool = tool_ids(conninfo, page["project"])
        counts = page_counts(hand, tool)
        per_page.append(counts)
        if page["page"] in planted:  # an ID in no text, counted apart: it must count as missed
            planted_counts = page_counts({**hand, PLANTED_ID: "proof_found"}, tool)["found"]
            missed = planted_counts[1] - planted_counts[0]
            caught += missed == counts["found"][1] - counts["found"][0] + 1
        details.append({
            "page": page["page"],
            "ids": [{"where": where, "id": entity, "hand": status,
                     "tool": tool.get((where, entity), "not found")}
                    for (where, entity), status in sorted(hand.items())],
            "only_the_tool": [{"where": where, "id": entity, "tool": status}
                              for (where, entity), status in sorted(tool.items())
                              if (where, entity) not in hand],
        })  # fmt: skip
    found = numbers(per_page)
    passes = {
        "found": found["found"]["share"] is not None
        and found["found"]["share"] >= PASS_MARKS["found"],
        "invented": found["invented"]["share"] is not None
        and found["invented"]["share"] <= PASS_MARKS["invented"],
        "status": found["status"]["share"] is not None
        and found["status"]["share"] >= PASS_MARKS["status"],
    }
    now = datetime.now(UTC)
    result = {"test": "test3", "made_on": now.date().isoformat(),
              "pages_checked": len(checked), "pages": len(answers), "numbers": found,
              "pass_marks": PASS_MARKS, "passes": passes,
              "planted": {"added": len(planted), "counted_as_missed": caught},
              "per_page": details}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-test3.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    shown = "; ".join(f"{name}: {value['share']} (range {value['range']})"
                      for name, value in found.items())  # fmt: skip
    print(f"Pages checked: {len(checked)} of {len(answers)}. {shown}. Planted IDs counted as "
          f"missed: {caught} of {len(planted)}. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
