"""Command line for the collectors.

    python -m hackathon_memory.collect ethglobal --plan    what a live run would read (no request)
    python -m hackathon_memory.collect ethglobal           a live run (needs the maintainer's yes)

The first form never touches the network. The second refuses to start unless every promise of
design 5.7 can be kept.
"""

from __future__ import annotations

import sys

from hackathon_memory.collect.ethglobal import build_collector, plan
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.settings import Settings


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "ethglobal" or any(a not in ("--plan",) for a in argv[1:]):
        print("usage: python -m hackathon_memory.collect ethglobal [--plan]")
        return 2
    settings = Settings()
    if "--plan" in argv:
        print("\n".join(plan(settings)))
        return 0
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
