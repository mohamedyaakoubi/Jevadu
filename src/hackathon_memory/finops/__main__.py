"""Command line for the cost of the model calls.

    python -m hackathon_memory.finops report      where the money went (the environment in use)
    python -m hackathon_memory.finops budget      where both budgets stand
    python -m hackathon_memory.finops prices      the price book, with the day each price begins
    python -m hackathon_memory.finops reconcile --billed 1.23
                                                  our own count against the amount on Google's bill

Options of `report`: --env test|prod, --days N (the last N days), --items N (what N project pages
would cost at the measured cost of one), --save (also write the numbers to a dated file in the
data folder). Options of `reconcile`: --env test|prod|all, --from and --to (days, UTC).

None of these commands calls a model, so none of them costs anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from hackathon_memory.finops import budget as budgets
from hackathon_memory.finops import prices, report
from hackathon_memory.finops.calls import ENVIRONMENTS, CallStore, LedgerNotReady, open_ledger
from hackathon_memory.settings import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.finops", add_help=True)
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("report")
    show.add_argument("--env", choices=ENVIRONMENTS)
    show.add_argument("--days", type=int)
    show.add_argument("--items", type=int)
    show.add_argument("--save", action="store_true")
    commands.add_parser("budget")
    commands.add_parser("prices")
    check = commands.add_parser("reconcile")
    check.add_argument("--billed", type=float, required=True)
    check.add_argument("--env", choices=(*ENVIRONMENTS, "all"), default="all")
    check.add_argument("--from", dest="first", type=date.fromisoformat)
    check.add_argument("--to", dest="last", type=date.fromisoformat)
    return parser


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _prices() -> str:
    lines = [f"Price book, read on {prices.READ_ON.isoformat()}", f"Source: {prices.SOURCE}", ""]
    lines.append("Dollars for a million tokens. Output includes the thinking tokens.")
    for price in prices.PRICE_BOOK:
        line = (
            f"  {price.model}, from {price.valid_from.isoformat()}: input {price.input_usd:.3f}, "
            f"output {price.output_usd:.3f}"
        )
        if price.cached_input_usd is not None:
            line += f", cached input {price.cached_input_usd:.3f}"
        if price.long_above_tokens is not None:
            line += (
                f". A prompt above {price.long_above_tokens:,} tokens: input "
                f"{price.long_input_usd:.3f}, output {price.long_output_usd:.3f}"
            )
        lines.append(line)
    lines += [
        "",
        f"A batch job costs {prices.BATCH_FACTOR:.0%} of these prices.",
        "A model that is not in this list has no cost in the reports: it is counted, not priced.",
    ]
    return "\n".join(lines)


def _report(args: argparse.Namespace, settings: Settings, store: CallStore, now: datetime) -> str:
    environment = args.env or settings.llm_environment
    since = _start(now.date() - timedelta(days=args.days - 1)) if args.days else None
    calls = store.calls(environment)
    built = report.build(calls, environment, since=since)
    status = budgets.status(budgets.from_settings(settings, environment), store, now)
    text = report.render(
        built,
        status=status,
        today=now.date(),
        items_planned=args.items,
        other_models=(settings.gemini_rewrite_model, settings.gemini_search_model),
        all_calls=calls,
    )
    if args.save:
        folder = Path(settings.data_dir) / "finops"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{environment}.json"
        data = report.as_dict(built) | {"written_at": now.isoformat()}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        text += f"\n\nSaved: {path}"
    return text


def _budget(settings: Settings, store: CallStore, now: datetime) -> str:
    lines = [f"The environment in use is '{settings.llm_environment}' (LLM_ENVIRONMENT in .env)."]
    for environment in ENVIRONMENTS:
        status = budgets.status(budgets.from_settings(settings, environment), store, now)
        line = (
            f"  {environment}: spent ${status.spent_total_usd:.4f} of ${status.total_usd:.2f}"
            + (
                f", today ${status.spent_today_usd:.4f} of ${status.per_day_usd:.2f}"
                if status.per_day_usd is not None
                else ""
            )
            + f". Left now: ${status.left_usd:.4f}. State: {status.state.upper()}."
        )
        lines.append(line)
    lines.append(
        "A call that could go over a budget is not made. The caps are in .env (LLM_BUDGET_...)."
    )
    return "\n".join(lines)


def _reconcile(args: argparse.Namespace, store: CallStore) -> str:
    since = _start(args.first) if args.first else None
    until = _start(args.last + timedelta(days=1)) if args.last else None
    environment = None if args.env == "all" else args.env
    calls = store.calls(environment, since, until)
    counted = sum(c.cost_usd or 0.0 for c in calls)
    unpriced = sum(1 for c in calls if c.cost_usd is None)
    result = report.reconcile(counted, args.billed, unpriced)
    lines = [
        f"Our count: ${result.counted_usd:.4f} ({len(calls)} call(s), environment {args.env})",
        f"Google's bill: ${result.billed_usd:.4f}",
        f"Gap: ${result.gap_usd:+.4f}"
        + (f" ({result.gap_percent:+.1f}% of the bill)" if result.gap_percent is not None else ""),
        result.verdict,
        "",
        "Where to read the bill: Google Cloud console, Billing, Reports. Choose the project, the",
        "same days, and the service of the Gemini models. Use the cost BEFORE credits, because a",
        "credit pays the bill but does not change what the calls cost.",
    ]
    return "\n".join(lines)


def main(
    argv: list[str],
    settings: Settings | None = None,
    store: CallStore | None = None,
    now: datetime | None = None,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    if args.command == "prices":
        print(_prices())
        return 0
    settings = settings or Settings()
    moment = now or datetime.now(UTC)
    try:
        ledger = store if store is not None else open_ledger(settings)
    except LedgerNotReady as problem:
        print(f"Cannot read the ledger. {problem}")
        return 2
    if args.command == "report":
        print(_report(args, settings, ledger, moment))
    elif args.command == "budget":
        print(_budget(settings, ledger, moment))
    else:
        print(_reconcile(args, ledger))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
