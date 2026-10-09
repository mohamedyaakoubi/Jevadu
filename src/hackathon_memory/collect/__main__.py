"""Command line for the collectors.

    python -m hackathon_memory.collect ethglobal --plan    what a run or a look would read
    python -m hackathon_memory.collect ethglobal --look    a look: 3 requests, nothing saved
    python -m hackathon_memory.collect ethglobal           a live run (needs the maintainer's yes)

The first form never touches the network. The other two refuse to start unless every promise of
design 5.7 can be kept, and each needs the maintainer's yes for the pages it reads (hard
constraint 17).
"""

from __future__ import annotations

import sys

from hackathon_memory.collect.ethglobal import build_collector, plan
from hackathon_memory.collect.look import build_looker, look_plan
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.settings import Settings

USAGE = "usage: python -m hackathon_memory.collect ethglobal [--plan | --look]"


def main(argv: list[str]) -> int:
    if (
        not argv
        or argv[0] != "ethglobal"
        or len(argv) > 2
        or argv[1:] not in ([], ["--plan"], ["--look"])
    ):
        print(USAGE)
        return 2
    settings = Settings()
    if argv[1:] == ["--plan"]:
        print("\n".join(plan(settings)))
        print()
        print("\n".join(look_plan(settings)))
        return 0
    if argv[1:] == ["--look"]:
        try:
            report = build_looker(settings).run()
        except CollectorRefused as refusal:
            print(f"Refused: {refusal}")
            return 1
        print("\n".join(report.lines))
        return 2 if report.stopped else 0
    try:
        summary = build_collector(settings).run()
    except CollectorRefused as refusal:
        print(f"Refused: {refusal}")
        return 1
    print(
        f"Done. Saved {summary.pages_saved}, already saved {summary.pages_already_saved}, "
        f"requests {summary.requests_made}, errors {len(summary.errors)}."
    )
    return 2 if summary.stopped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
