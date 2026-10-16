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
    """One way to search that the page offers, with what its test measured."""

    key: str
    label: str
    found: int | None  # known similar projects in the first 10, in Test 2
    known: int | None
    seconds: float | None  # the middle time of a search, from the measure of the modes
    words: str  # what it does, in plain words

    @property
    def facts(self) -> str:
        parts = [self.words]
        if self.found is not None and self.known:
            share = round(100 * self.found / self.known)
            parts.append(f"In Test 2 it put {self.found} of {self.known} known similar projects "
                         f"in its first 10 ({share}%).")  # fmt: skip
        if self.seconds is not None:
            parts.append(f"A search takes about {self.seconds:.1f} s.")
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


WORDS = {
    "both": ("Meaning and words",
             "Finds projects close in meaning, and projects that use your words."),
    "meaning": ("Meaning only",
                "Finds projects with the same idea, also when they use other words."),
    "words": ("Your words only",
              "Finds the projects that use your words. Best for a name or an exact term."),
}  # fmt: skip


def search_modes(folder: Path | None = None) -> list[Mode]:
    """The modes of the search, each with its numbers from Test 2 and from the measure of the
    modes, when those files exist."""
    test2 = newest("test2", folder) or {}
    measured = (newest("search-modes", folder) or {}).get("modes", {})
    other = test2.get("other_setups", {})
    counts = {
        "both": test2.get("numbers", {}).get("all", {}),
        "meaning": other.get("meaning only", {}),
        "words": other.get("words only", {}),
    }
    modes = []
    for key, (label, words) in WORDS.items():
        number = counts.get(key) or {}
        seconds = (measured.get(key) or {}).get("seconds_middle")
        modes.append(Mode(key, label, number.get("found"), number.get("known"), seconds, words))
    return modes
