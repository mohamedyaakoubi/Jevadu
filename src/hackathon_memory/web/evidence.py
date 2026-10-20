"""The numbers that the pages show about the tests, read from the dated result files.

No number is shown unless a test in evals/ with a dated result file gives it (design rule 6). So
the pages never carry a number of their own: they read the newest result file of each test, and
show nothing when it is missing. The files are those of the repository (evals/results).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[3] / "evals" / "results"


@dataclass(frozen=True)
class Mode:
    """One way to search, with what the measure of the modes found for it."""

    key: str  # the value in the address of the page; "" for a way that is not offered
    label: str
    words: str  # what it does, in plain words
    found: int | None = None  # known similar projects in the first 10, on the cases of Test 2
    known: int | None = None
    low: float | None = None  # the range of the share found
    high: float | None = None
    seconds: float | None = None  # the middle time of a search
    slow_seconds: float | None = None  # 95 of 100 searches were faster than this
    cost_usd: float | None = None  # the cost of a search
    why_not: str = ""  # why a measured way is not offered

    @property
    def share(self) -> int | None:
        return (
            round(100 * self.found / self.known) if self.found is not None and self.known else None
        )

    @property
    def facts(self) -> str:
        parts = [self.words]
        if self.share is not None:
            parts.append(f"On the cases of Test 2 it put {self.found} of {self.known} known "
                         f"similar projects in its first 10 ({self.share}%).")  # fmt: skip
        if self.seconds is not None:
            cost = (f", and costs about {100 * self.cost_usd:.1f} cent"
                    if self.cost_usd else "")  # fmt: skip
            parts.append(f"A search takes about {max(self.seconds, 0.1):.1f} s{cost}.")
        return " ".join(parts)


def newest(name: str, folder: Path | None = None) -> dict | None:
    """The newest result file whose name ends with -<name>.json, or None."""
    folder = folder or RESULTS
    files = sorted(folder.glob(f"*-{name}.json")) if folder.is_dir() else []
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# The ways to search: the key on the page, the name in the result file, the label, the words.
WAYS = (
    ("ai", "meaning, then AI", "Sort and compare with Gemini",
     "Gemini 3.8 Flash sorts the 30 projects closest in meaning, on a click."),
    ("meaning", "meaning", "Semantic",
     "Finds projects with the same idea, also in other words."),
    ("words", "words", "Keyword",
     "Finds the projects that contain your words. Best for a name or an exact term."),
    ("", "both", "Semantic and keyword together",
     "Both lists merged by the place of each project in each (reciprocal rank fusion)."),
    ("", "both, then AI", "Semantic and keyword, then Gemini",
     "The top 30 of both lists together, sorted by the same model."),
    ("", "AI over every project", "Gemini over every project",
     "Gemini reads the tagline of every project and picks the 10 closest."),
)  # fmt: skip
WHY_NOT = {
    "both": "Not offered since 16 October 2026: it found fewer than semantic search alone.",
    "both, then AI": "Not offered: it found no more than Gemini on the 30 closest by "
    "meaning, and was slower.",
    "AI over every project": "Not offered: it found no more, and costs about seven times as "
    "much, because the model reads every project for every search.",
}


def measured_modes(folder: Path | None = None) -> list[Mode]:
    """Every way to search that the newest measure of the modes ran, offered or not."""
    numbers = (newest("search-modes", folder) or {}).get("modes", {})
    modes = []
    for key, name, label, words in WAYS:
        one = numbers.get(name) or {}
        low, high = (one.get("range") or [None, None])[:2]
        modes.append(Mode(key, label, words, one.get("found"), one.get("known"), low, high,
                          one.get("seconds_middle"), one.get("seconds_95_of_100"),
                          one.get("cost_usd_per_search"), WHY_NOT.get(name, "")))  # fmt: skip
    return modes


def search_modes(folder: Path | None = None) -> list[Mode]:
    """The ways to search that the search page offers: Gemini's order, then the two quick ones."""
    return [mode for mode in measured_modes(folder) if mode.key]


def mode_named(key: str, folder: Path | None = None) -> Mode | None:
    """The measured way to search of this key on the page, or None."""
    return next((mode for mode in measured_modes(folder) if mode.key == key), None)


@dataclass(frozen=True)
class Comparing:
    """What one comparison of ten projects took, at the thinking level in use."""

    level: str
    seconds: float  # the middle time of a call
    cost_usd: float  # the cost of one call


def compare_numbers(level: str = "LOW", folder: Path | None = None) -> Comparing | None:
    """The middle time and the cost of one comparison, from the newest measure of the levels."""
    one = ((newest("compare-levels", folder) or {}).get("levels") or {}).get(level) or {}
    if not one.get("calls"):
        return None
    return Comparing(level, float(one["seconds_middle"]), float(one["cost_usd"]) / one["calls"])
