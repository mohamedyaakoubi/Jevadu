"""Where the money goes: the report of the calls of one environment.

It answers, from the lines of the ledger and nothing else:

* How much was spent, by what, with which model, on which day?
* What does ONE project page cost to rewrite, and ONE search? (the unit costs)
* How much went into second attempts, because a first answer was not a valid form?
* How much of the output was thinking?
* What would the same calls cost with the other model, and after the next change of price?
* At this speed, how many days does the budget last?

Every number is our own count. A call of a model with no known price is counted and listed, and
its cost is left out of the sums. The report says how many such calls there are.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from hackathon_memory.finops import prices
from hackathon_memory.finops.budget import BudgetStatus
from hackathon_memory.finops.calls import Call


def percentile(values: list[float], share: float) -> float | None:
    """The value below which `share` of the values lie (nearest rank). None for no value."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class Group:
    """The calls that share a label, added up."""

    label: tuple[str, ...]
    calls: int
    failed: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cached_tokens: int
    cost_usd: float
    unpriced_calls: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None

    @property
    def mean_cost_usd(self) -> float | None:
        priced = self.calls - self.unpriced_calls
        return self.cost_usd / priced if priced else None

    @property
    def thinking_share(self) -> float | None:
        """The share of the output that was thinking. Thinking is billed as output."""
        out = self.output_tokens + self.thinking_tokens
        return self.thinking_tokens / out if out else None


@dataclass(frozen=True)
class UnitCost:
    """What one unit of work costs: one project page, one search."""

    label: str
    units: int
    calls: int
    total_usd: float
    mean_usd: float
    p95_usd: float
    extra_calls: int  # calls after the first one for the same unit: second attempts
    extra_usd: float


@dataclass(frozen=True)
class Report:
    environment: str
    since: datetime | None
    until: datetime | None
    total: Group
    by_use: list[Group]  # purpose, model, thinking level
    by_day: list[tuple[date, int, float]]
    per_item: list[UnitCost]  # by purpose: the cost of one item (one project page)
    per_run: UnitCost | None  # the cost of one run that has no item (one search)
    dearest: list[Call] = field(default_factory=list)


def _group(label: tuple[str, ...], calls: list[Call]) -> Group:
    latencies = [float(c.latency_ms) for c in calls if c.latency_ms is not None and c.ok]
    return Group(
        label=label,
        calls=len(calls),
        failed=sum(1 for c in calls if not c.ok),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        thinking_tokens=sum(c.thinking_tokens for c in calls),
        cached_tokens=sum(c.cached_tokens for c in calls),
        cost_usd=round(sum(c.cost_usd or 0.0 for c in calls), 8),
        unpriced_calls=sum(1 for c in calls if c.cost_usd is None),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
    )


def _unit_cost(label: str, units: dict[str, list[Call]]) -> UnitCost | None:
    if not units:
        return None
    totals: list[float] = []
    extra_calls = 0
    extra_usd = 0.0
    for calls in units.values():
        ordered = sorted(calls, key=lambda c: c.called_at)
        totals.append(sum(c.cost_usd or 0.0 for c in ordered))
        extra_calls += len(ordered) - 1
        extra_usd += sum(c.cost_usd or 0.0 for c in ordered[:-1])
    return UnitCost(
        label=label,
        units=len(units),
        calls=sum(len(calls) for calls in units.values()),
        total_usd=round(sum(totals), 8),
        mean_usd=round(sum(totals) / len(totals), 8),
        p95_usd=round(percentile(totals, 0.95) or 0.0, 8),
        extra_calls=extra_calls,
        extra_usd=round(extra_usd, 8),
    )


def build(
    calls: list[Call],
    environment: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Report:
    """The report of the calls of one environment in a range of time."""
    chosen = [
        c
        for c in calls
        if c.environment == environment
        and (since is None or c.called_at >= since)
        and (until is None or c.called_at < until)
    ]
    by_use: dict[tuple[str, ...], list[Call]] = defaultdict(list)
    by_day: dict[date, list[Call]] = defaultdict(list)
    items: dict[str, dict[str, list[Call]]] = defaultdict(lambda: defaultdict(list))
    runs: dict[str, list[Call]] = defaultdict(list)
    for call in chosen:
        by_use[(call.purpose, call.model, call.thinking_level or "-")].append(call)
        by_day[call.called_at.astimezone(UTC).date()].append(call)
        if call.item_ref is not None:
            items[call.purpose][call.item_ref].append(call)
        if call.run_id is not None and call.item_ref is None:
            # A run with items is a job, and its unit is the item. A run with no item is
            # its own unit: one search of a user.
            runs[call.run_id].append(call)
    per_item = [u for u in (_unit_cost(p, units) for p, units in sorted(items.items())) if u]
    dearest = sorted(
        (c for c in chosen if c.cost_usd), key=lambda c: c.cost_usd or 0.0, reverse=True
    )[:5]
    return Report(
        environment=environment,
        since=since,
        until=until,
        total=_group(("all",), chosen),
        by_use=sorted(
            (_group(label, group) for label, group in by_use.items()),
            key=lambda g: g.cost_usd,
            reverse=True,
        ),
        by_day=[
            (day, len(group), round(sum(c.cost_usd or 0.0 for c in group), 8))
            for day, group in sorted(by_day.items())
        ],
        per_item=per_item,
        per_run=_unit_cost("run", runs),
        dearest=dearest,
    )


def repriced(calls: list[Call], model: str | None = None, on: date | None = None) -> float | None:
    """The cost of the same tokens with another model, or on another day. None if a price lacks."""
    total = 0.0
    for call in calls:
        cost = call.repriced(model=model, on=on)
        if cost is None:
            return None
        total += cost
    return round(total, 8)


@dataclass(frozen=True)
class PriceChange:
    model: str
    day: date
    cost_now_usd: float
    cost_then_usd: float


def price_changes(calls: list[Call], today: date) -> list[PriceChange]:
    """For each model whose price will change: the same calls at today's price and the new one."""
    by_model: dict[str, list[Call]] = defaultdict(list)
    for call in calls:
        by_model[call.model].append(call)
    changes: list[PriceChange] = []
    for model, group in sorted(by_model.items()):
        change = prices.next_change(model, today)
        if change is None:
            continue
        now = repriced(group, on=today)
        then = repriced(group, on=change.valid_from)
        if now is not None and then is not None:
            changes.append(PriceChange(model, change.valid_from, now, then))
    return changes


def daily_rate(report: Report, today: date, days: int = 7) -> float:
    """The mean cost of one day over the last `days` days, today included."""
    first = today - timedelta(days=days - 1)
    return round(sum(cost for day, _, cost in report.by_day if first <= day <= today) / days, 8)


def days_left(status: BudgetStatus, rate_per_day: float) -> float | None:
    """How many days the whole budget lasts at this rate. None when nothing is being spent."""
    left = status.total_usd - status.spent_total_usd
    return round(max(left, 0.0) / rate_per_day, 1) if rate_per_day > 0 else None


@dataclass(frozen=True)
class Reconciliation:
    counted_usd: float
    billed_usd: float
    gap_usd: float
    gap_percent: float | None
    verdict: str


def reconcile(counted_usd: float, billed_usd: float, unpriced_calls: int = 0) -> Reconciliation:
    """Our own count against the amount on Google's bill for the same days."""
    gap = round(billed_usd - counted_usd, 6)
    percent = round(100 * gap / billed_usd, 1) if billed_usd > 0 else None
    if billed_usd == 0 and counted_usd == 0:
        verdict = "Nothing was counted and nothing was billed."
    elif percent is not None and abs(percent) <= 5:
        verdict = "The count and the bill agree (5 percent or less apart)."
    elif gap > 0:
        verdict = (
            "The bill is HIGHER than the count. Something is not counted: a call that does not go "
            "through the meter, another program on the same Google project, or a price that is "
            "not in the price book."
        )
        if unpriced_calls:
            verdict += f" {unpriced_calls} counted call(s) have no known price: start there."
    else:
        verdict = (
            "The bill is LOWER than the count. The price book may be too high (a discount, cached "
            "input, a free allowance), or the bill does not cover the same days yet: Google's "
            "billing can be a day late."
        )
    return Reconciliation(round(counted_usd, 6), round(billed_usd, 6), gap, percent, verdict)


# ------------------------------------------------------------------------------- as text


def _usd(value: float | None) -> str:
    return "not known" if value is None else f"${value:.4f}"


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value / 1000:.1f} s"


def render(
    report: Report,
    status: BudgetStatus | None = None,
    today: date | None = None,
    items_planned: int | None = None,
    other_models: tuple[str, ...] = (),
    all_calls: list[Call] | None = None,
) -> str:
    day = today or prices.today()
    total = report.total
    lines = [f"Cost of the model calls, environment '{report.environment}'"]
    if report.since or report.until:
        first = report.since.date().isoformat() if report.since else "the start"
        last = report.until.date().isoformat() if report.until else "now"
        lines.append(f"From {first} to {last} (UTC).")
    lines.append("")
    lines.append(
        f"Calls: {total.calls} ({total.failed} failed). "
        f"Tokens in: {total.input_tokens:,}. Tokens out: {total.output_tokens:,}. "
        f"Thinking tokens: {total.thinking_tokens:,}."
    )
    lines.append(f"Spent: {_usd(total.cost_usd)}")
    if total.unpriced_calls:
        lines.append(
            f"NOT in this sum: {total.unpriced_calls} call(s) of a model whose price is not in "
            "the price book. Their cost is not guessed."
        )
    if total.thinking_share is not None:
        lines.append(
            f"Thinking is {total.thinking_share:.0%} of the output tokens, "
            "and it is billed as output."
        )

    if status is not None:
        lines += ["", "Budget"]
        lines.append(
            f"  All: {_usd(status.spent_total_usd)} of {_usd(status.total_usd)}"
            + (
                f". Today: {_usd(status.spent_today_usd)} of {_usd(status.per_day_usd)}"
                if status.per_day_usd is not None
                else ""
            )
        )
        lines.append(f"  State: {status.state.upper()} ({status.reason}).")
        rate = daily_rate(report, day)
        left = days_left(status, rate)
        if left is not None:
            lines.append(
                f"  The last 7 days cost {_usd(rate)} a day. At this speed the budget lasts "
                f"{left} more day(s)."
            )

    if report.by_use:
        lines += ["", "By use (purpose, model, thinking level)"]
        for group in report.by_use:
            unknown = group.unpriced_calls == group.calls
            cost = (
                "cost not known"
                if unknown
                else f"{_usd(group.cost_usd)}, one call {_usd(group.mean_cost_usd)}"
            )
            lines.append(
                f"  {' / '.join(group.label)}: {group.calls} call(s), {cost}"
                f", time {_ms(group.latency_p50_ms)} (half of the calls) and "
                f"{_ms(group.latency_p95_ms)} (95 of 100)"
                + (f", {group.failed} failed" if group.failed else "")
                + (
                    f", {group.unpriced_calls} with no known price"
                    if group.unpriced_calls and not unknown
                    else ""
                )
            )

    if report.per_item:
        lines += ["", "What one item costs (for a rewrite, one item is one project page)"]
        for unit in report.per_item:
            lines.append(
                f"  {unit.label}: {unit.units} item(s), one item {_usd(unit.mean_usd)} "
                f"(95 of 100 cost {_usd(unit.p95_usd)} or less)"
            )
            if unit.extra_calls:
                lines.append(
                    f"    {unit.extra_calls} second attempt(s) cost {_usd(unit.extra_usd)} "
                    f"({unit.extra_usd / unit.total_usd:.0%} of this work)."
                    if unit.total_usd
                    else f"    {unit.extra_calls} second attempt(s)."
                )
            if items_planned:
                planned = _usd(unit.mean_usd * items_planned)
                lines.append(f"    {items_planned:,} items at this cost: {planned}.")
    if report.per_run is not None:
        run = report.per_run
        lines += ["", "What one run costs (for a search, one run is one search of a user)"]
        lines.append(
            f"  {run.units} run(s), {run.calls} call(s), one run {_usd(run.mean_usd)} "
            f"(95 of 100 cost {_usd(run.p95_usd)} or less)"
        )

    chosen = [
        c
        for c in (all_calls or [])
        if c.environment == report.environment
        and (report.since is None or c.called_at >= report.since)
        and (report.until is None or c.called_at < report.until)
    ]
    priced = [c for c in chosen if c.cost_usd is not None and c.output_tokens + c.thinking_tokens]
    if priced and other_models:
        lines += ["", "The same tokens with another model (a first idea only: another model uses"]
        lines.append("other numbers of tokens, and gives other answers)")
        now = repriced(priced, on=day)
        lines.append(f"  As it was, at today's prices: {_usd(now)}")
        for model in other_models:
            lines.append(f"  All with {model}: {_usd(repriced(priced, model=model, on=day))}")
    changes = price_changes(chosen, day)
    if changes:
        lines += ["", "A change of price that is already announced"]
        for change in changes:
            lines.append(
                f"  {change.model} from {change.day.isoformat()}: the same calls cost "
                f"{_usd(change.cost_then_usd)} and not {_usd(change.cost_now_usd)}."
            )

    if report.by_day:
        lines += ["", "By day (UTC)"]
        for when, count, cost in report.by_day[-14:]:
            lines.append(f"  {when.isoformat()}: {count} call(s), {_usd(cost)}")
    if report.dearest:
        lines += ["", "The dearest calls"]
        for call in report.dearest:
            lines.append(
                f"  {_usd(call.cost_usd)}  {call.purpose} / {call.model}: "
                f"{call.input_tokens:,} in, {call.output_tokens:,} out, "
                f"{call.thinking_tokens:,} thinking"
                + (f", item {call.item_ref}" if call.item_ref else "")
            )
    lines += [
        "",
        "These numbers are our own count: the tokens that Google reported, times the prices that",
        "Google published. Google's bill is the truth. Compare with:",
        "  python -m hackathon_memory.finops reconcile --billed <dollars on the bill>",
    ]
    return "\n".join(lines)


def as_dict(report: Report) -> dict:
    """The report as plain data, for a dated result file. It holds no text of a page."""

    def group(g: Group) -> dict:
        return {
            "label": list(g.label),
            "calls": g.calls,
            "failed": g.failed,
            "input_tokens": g.input_tokens,
            "output_tokens": g.output_tokens,
            "thinking_tokens": g.thinking_tokens,
            "cached_tokens": g.cached_tokens,
            "cost_usd": g.cost_usd,
            "unpriced_calls": g.unpriced_calls,
            "latency_p50_ms": g.latency_p50_ms,
            "latency_p95_ms": g.latency_p95_ms,
        }

    def unit(u: UnitCost) -> dict:
        return {
            "label": u.label,
            "units": u.units,
            "calls": u.calls,
            "total_usd": u.total_usd,
            "mean_usd": u.mean_usd,
            "p95_usd": u.p95_usd,
            "extra_calls": u.extra_calls,
            "extra_usd": u.extra_usd,
        }

    return {
        "environment": report.environment,
        "since": report.since.isoformat() if report.since else None,
        "until": report.until.isoformat() if report.until else None,
        "total": group(report.total),
        "by_use": [group(g) for g in report.by_use],
        "by_day": [{"day": d.isoformat(), "calls": n, "cost_usd": c} for d, n, c in report.by_day],
        "per_item": [unit(u) for u in report.per_item],
        "per_run": unit(report.per_run) if report.per_run else None,
        "price_book_read_on": prices.READ_ON.isoformat(),
        "price_book_source": prices.SOURCE,
    }
