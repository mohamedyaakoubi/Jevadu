"""Invented projects and cards for the tests of the review sheet of Test 1."""

from __future__ import annotations

import random

from evals.test1.sheet import Block, Case, build

MODEL = "gemini-3.1-pro-preview"
SALE = "It writes each sale to the Hedera Consensus Service."


def seeded(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - a repeatable draw for a test, not a secret


def field(label: str, value: object, quotes: list[str], state: str = "kept") -> dict:
    return {"label": label, "value": value, "quotes": quotes, "removed": 0, "state": state,
            "why": ""}  # fmt: skip


def card(number: int, services: str = SALE + " (HCS)") -> dict:
    return {
        "what_it_does": field(
            "stated",
            f"Project {number} lets a vendor take a coin.",
            ["lets a street vendor take a coin"],
        ),
        "how_it_works": field(
            "inferred", ["A buyer pays.", "The sale is written."], ["Buyers check the record."]
        ),
        "for_whom": field("stated", "Street vendors.", ["lets a street vendor take a coin"]),
        "hedera_services": field("stated", services, [SALE]),
        "category": field("inferred", "Payments and remittance", ["Buyers check the record."]),
        "problem": field("not_found", "", [], "not_found"),
        "solution": field("stated", "", [], "dropped"),
    }


def case(number: int) -> Case:
    text = f"Project {number} lets a street vendor take a coin. {SALE} Buyers check the record."
    return Case(
        f"https://ethglobal.com/showcase/project-{number}-x1y2z",
        (
            Block("name", "", f"Project {number}"),
            Block("short_line", "", f"Coins for vendor {number}."),
            Block("section", "Project Description", text),
        ),
        card(number),
    )


DONOR = {
    **card(99),
    "what_it_does": field("stated", "It counts the trees of a forest.", ["counts trees"]),
    "for_whom": field("stated", "Foresters.", ["for foresters"]),
}


def made(count: int = 12, seed: int = 7) -> tuple[dict, dict]:
    """The data and the key of a sheet of `count` invented projects."""
    cases = [case(number) for number in range(1, count + 1)]
    return build(cases, donors=[DONOR], model=MODEL, version="card-form-9",
                 grades_file="grades.json", rng=seeded(seed))  # fmt: skip
