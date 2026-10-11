"""Command line for the collectors.

    python -m hackathon_memory.collect ethglobal --plan    what each command would read
    python -m hackathon_memory.collect ethglobal --look    a look: 2 requests, no page saved
    python -m hackathon_memory.collect ethglobal --find    walk the Hedera list of the showcase
    python -m hackathon_memory.collect ethglobal           a live run (needs the maintainer's yes)

The first form never touches the network. The others refuse to start unless every rule of design
5.7 can be kept, and each needs the maintainer's yes for the pages it reads (design rule 17).

A walk and a run can be made in parts. `--find --pages 5` reads at most five pages of the list.
`--pages 3` with no other option is a run that asks for at most three new project pages. Started
again, each goes on where it stopped, and nothing is asked for twice.

`--pause 10` makes a walk or a run slower: ten seconds between two requests in place of two. The
pause can be made longer, never shorter.

When the site answers "too many requests" (429), the run stops. The tool then sends nothing for
one hour, and after that it goes on five times slower. `--wait` lets a walk or a run wait for
the end of that hour by itself and go on, in place of stopping.

When the site answers that it does not want a request at all (403, a bot check), the tool sends
nothing more to that site. A person decides how to go on, and says so with
`--after-refusal "<the decision>"`. That command sends no request.
"""

from __future__ import annotations

import argparse
import sys

from hackathon_memory.collect.ethglobal import build_collector, clear_refusal, plan
from hackathon_memory.collect.ethglobal_find import build_walker, walk_plan
from hackathon_memory.collect.look import build_looker, look_plan
from hackathon_memory.collect.polite import PAUSE_SECONDS, CollectorRefused
from hackathon_memory.settings import Settings

USAGE = (
    "python -m hackathon_memory.collect ethglobal "
    '[--plan | --look | --find | --after-refusal "<decision>"] '
    "[--pages N] [--pause SECONDS] [--wait]"
)


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
    what.add_argument("--after-refusal", metavar="DECISION")
    parser.add_argument("--pages", type=int)
    parser.add_argument("--pause", type=float)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args(argv)
    reads_many = not (args.plan or args.look or args.after_refusal is not None)
    if args.pages is not None and (not reads_many or args.pages < 1):
        raise ValueError("--pages goes with --find or with a run, and is 1 or more")
    if args.pause is not None and (not reads_many or args.pause < PAUSE_SECONDS):
        raise ValueError("--pause goes with --find or with a run, and is 2 seconds or more")
    if args.wait and not reads_many:
        raise ValueError("--wait goes with --find or with a run")
    return args


def main(argv: list[str]) -> int:
    try:
        args = _arguments(argv)
    except ValueError:
        print(f"usage: {USAGE}")
        return 2
    settings = Settings()
    slower: dict[str, object] = {} if args.pause is None else {"pause_seconds": args.pause}
    if args.wait:
        slower["wait_for_cooldown"] = True
    try:
        if args.plan:
            sections = (walk_plan(settings), plan(settings), look_plan(settings))
            print("\n\n".join("\n".join(lines) for lines in sections))
            return 0
        if args.after_refusal is not None:
            print("\n".join(clear_refusal(settings, args.after_refusal)))
            return 0
        if args.look:
            report = build_looker(settings).run()
            print("\n".join(report.lines))
            return 2 if report.stopped else 0
        if args.find:
            walk = build_walker(settings, max_pages=args.pages, **slower).run()
            print(
                f"Done. Read {walk.pages_read} page(s) of the list from page {walk.first_page}: "
                f"{walk.projects_listed} projects, {walk.projects_with_prize} with a prize. "
                f"Requests {walk.requests_made}. "
                + ("The last page was reached." if walk.complete else "The list is not finished.")
            )
            return 2 if walk.stopped else 0
        summary = build_collector(settings, max_new_pages=args.pages, **slower).run()
    except CollectorRefused as refusal:
        print(f"Refused: {refusal}")
        return 1
    print(
        f"Done. Saved {summary.pages_saved}, already saved {summary.pages_already_saved}, "
        f"not kept {len(summary.pages_without_hedera_prize)}, "
        f"left for a later run {summary.pages_left_for_later}, "
        f"requests {summary.requests_made}, errors {len(summary.errors)}."
    )
    return 2 if summary.stopped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
