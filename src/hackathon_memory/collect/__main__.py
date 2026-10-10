"""Command line for the collectors.

    python -m hackathon_memory.collect ethglobal --plan    what each command would read
    python -m hackathon_memory.collect ethglobal --look    a look: 2 requests, no page saved
    python -m hackathon_memory.collect ethglobal --find    walk the Hedera list of the showcase
    python -m hackathon_memory.collect ethglobal           a live run (needs the maintainer's yes)

The first form never touches the network. The others refuse to start unless every promise of
design 5.7 can be kept, and each needs the maintainer's yes for the pages it reads (design
rule 17). `--find --pages 5` reads at most five pages of the list and can be started again.
"""

from __future__ import annotations

import argparse
import sys

from hackathon_memory.collect.ethglobal import build_collector, plan
from hackathon_memory.collect.ethglobal_find import build_walker, walk_plan
from hackathon_memory.collect.look import build_looker, look_plan
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.settings import Settings

USAGE = "python -m hackathon_memory.collect ethglobal [--plan | --look | --find [--pages N]]"


class _Quiet(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit; the caller prints the usage
        raise ValueError(message)


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = _Quiet(prog="python -m hackathon_memory.collect", add_help=False)
    parser.add_argument("site", choices=["ethglobal"])
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--plan", action="store_true")
    what.add_argument("--look", action="store_true")
    what.add_argument("--find", action="store_true")
    parser.add_argument("--pages", type=int)
    args = parser.parse_args(argv)
    if args.pages is not None and (not args.find or args.pages < 1):
        raise ValueError("--pages goes with --find, and is 1 or more")
    return args


def main(argv: list[str]) -> int:
    try:
        args = _arguments(argv)
    except ValueError:
        print(f"usage: {USAGE}")
        return 2
    settings = Settings()
    try:
        if args.plan:
            sections = (walk_plan(settings), plan(settings), look_plan(settings))
            print("\n\n".join("\n".join(lines) for lines in sections))
            return 0
        if args.look:
            report = build_looker(settings).run()
            print("\n".join(report.lines))
            return 2 if report.stopped else 0
        if args.find:
            walk = build_walker(settings, max_pages=args.pages).run()
            print(
                f"Done. Read {walk.pages_read} page(s) of the list from page {walk.first_page}: "
                f"{walk.projects_listed} projects, {walk.projects_with_prize} with a prize. "
                f"Requests {walk.requests_made}. "
                + ("The last page was reached." if walk.complete else "The list is not finished.")
            )
            return 2 if walk.stopped else 0
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
