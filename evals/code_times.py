"""How long the reading of a repository's code takes, measured on the readings that were saved.

    python -m evals.code_times

Each saved reading of an archive (collect/github_code.py) keeps the size of the archive and how
long its two requests and its reading took, pauses included: the time that a person waits when
the check of a submission reads a repository that the tool has not read before. This script
gathers them, and sends no request.

It writes evals/results/<UTC time>-code-times.json, in numbers only, with no name of a
repository: how many readings, the seconds and the megabytes at the middle (the median), at 90
and at 95 of 100 and at the largest, the time of all of them, and how many stay under both
limits of a live check.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hackathon_memory.collect import github
from hackathon_memory.collect.github_code import LIVE_MAX_BYTES, LIVE_SECONDS, SUFFIX
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
MEGABYTE = 1_000_000


def measured(store: RawStore) -> list[tuple[int, float]]:
    """The size in bytes and the seconds of every saved reading of an archive that kept its
    time."""
    found = []
    for saved in store.saved(SUFFIX):
        answer = saved.meta.get("answer") or {}
        if saved.url.endswith("/tarball") and saved.meta["status"] == 200 and "seconds" in answer:
            found.append((int(answer["archive_bytes"]), float(answer["seconds"])))
    return found


def at(values: list[float], part: float) -> float:
    """The value that `part` of the values do not pass (the nearest rank)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(part * len(ordered)) - 1)]


def spread(values: list[float]) -> dict[str, float]:
    return {"median": round(statistics.median(values), 2), "p90": round(at(values, 0.9), 2),
            "p95": round(at(values, 0.95), 2), "largest": round(max(values), 2),
            "all": round(sum(values), 1)}  # fmt: skip


def summary(found: list[tuple[int, float]]) -> dict:
    """The numbers of the readings, or only their count when there is none."""
    if not found:
        return {"readings": 0}
    under = sum(1 for size, took in found if size <= LIVE_MAX_BYTES and took <= LIVE_SECONDS)
    return {
        "readings": len(found),
        "seconds": spread([took for _, took in found]),
        "megabytes": spread([size / MEGABYTE for size, _ in found]),
        "live_limits": {"megabytes": LIVE_MAX_BYTES / MEGABYTE, "seconds": LIVE_SECONDS},
        "under_both_live_limits": under,
    }


def main(argv: Sequence[str], settings: Settings | None = None) -> int:
    if argv:
        print("usage: python -m evals.code_times")
        return 2
    settings = settings or Settings()
    numbers = summary(measured(RawStore(github.raw_dir(settings))))
    now = datetime.now(UTC)
    result = {"test": "code-times", "made_on": now.date().isoformat(),
              "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **numbers}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-code-times.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if numbers["readings"]:
        seconds = numbers["seconds"]
        print(
            f"Readings: {numbers['readings']}. Seconds: median {seconds['median']}, 95 of 100 "
            f"under {seconds['p95']}, largest {seconds['largest']}, all {seconds['all']}. "
            f"Under both live limits: {numbers['under_both_live_limits']}. Written: {path}"
        )
    else:
        print(f"No reading kept its time yet. Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
