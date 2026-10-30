"""The watch over the public copy's spending, for a scheduled job of GitHub Actions (design 12.5,
30 October 2026).

    python -m hackathon_memory.finops.watch

The public copy spends from a budget of its own (finops/budget.py): LLM_BUDGET_PUBLIC_USD in all
and LLM_BUDGET_PUBLIC_PER_DAY_USD a day, the day counted in UTC. The meter refuses a call past
either cap by itself, so this watch stops nothing: it says where the budget stands and what the
visitors used, and it fails once a share of a cap is spent (ALERT_SHARE), so that GitHub sends
an email, as it does for a failed scheduled run.

It reads the public copy's database with a role that may only read the three tables below
(PUBLIC_COSTS_DATABASE_URL), and it imports nothing but psycopg and the standard library, so the
job installs one package. The role was made once, by the role that owns the database:

    CREATE ROLE costs_reader LOGIN PASSWORD '...';
    ALTER ROLE costs_reader SET default_transaction_read_only = on;
    GRANT USAGE ON SCHEMA public TO costs_reader;
    GRANT SELECT ON llm_calls, visitor_uses, site_switches TO costs_reader;

On a laptop, a setting that is not in the environment is read from the .env of the working
folder, as the settings read it (31 October 2026: the command of the README said "not set" there,
since only the job gives its settings in the environment). The environment wins, as for the
settings, and a value is never printed.

Exit codes: 0 all is well, 1 a share of a cap is spent, 2 the database cannot be read.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg

ENVIRONMENT = "public"
# The defaults of settings.py (a test keeps them equal); the job may give others.
TOTAL_USD, PER_DAY_USD = 30.0, 5.0
ALERT_SHARE = 0.8
DATABASE = "PUBLIC_COSTS_DATABASE_URL"
GIVEN = (DATABASE, "LLM_BUDGET_PUBLIC_USD", "LLM_BUDGET_PUBLIC_PER_DAY_USD")  # by the job or .env
WHAT = {"ai": "asks of Gemini", "embed": "searches by meaning", "check": "checks",
        "refresh": "readings again", "register": "registrations"}  # fmt: skip
SWITCHES = ("ai", "register")  # those of web/public.py (a test keeps them equal): unset is off


@dataclass(frozen=True)
class Standing:
    """Where the public copy's budget stands, and what its visitors used."""

    spent_usd: float
    spent_today_usd: float
    calls: int
    calls_today: int
    failed_today: int
    unpriced: int  # calls with no known price: the budget cannot count them
    last_call: datetime | None
    by_purpose: tuple[tuple[str, int, float], ...]  # purpose, calls, dollars
    used: tuple[tuple[str, int, int], ...]  # kind, visitors, uses
    switches: tuple[tuple[str, bool], ...]


def standing(conninfo: str, now: datetime | None = None) -> Standing:
    """Read the budget and the uses of the public copy. Raises psycopg.Error."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    with psycopg.connect(conninfo, connect_timeout=20) as conn:
        spent, calls, unpriced, last = conn.execute(
            "SELECT coalesce(sum(cost_usd), 0), count(*), count(*) FILTER (WHERE cost_usd IS NULL),"
            " max(called_at) FROM llm_calls WHERE environment = %s",
            (ENVIRONMENT,),
        ).fetchone()
        today, calls_today, failed = conn.execute(
            "SELECT coalesce(sum(cost_usd), 0), count(*), count(*) FILTER (WHERE NOT ok) "
            "FROM llm_calls WHERE environment = %s AND called_at >= %s",
            (ENVIRONMENT, day),
        ).fetchone()
        purposes = conn.execute(
            "SELECT purpose, count(*), coalesce(sum(cost_usd), 0) FROM llm_calls "
            "WHERE environment = %s GROUP BY purpose ORDER BY 3 DESC, 1",
            (ENVIRONMENT,),
        ).fetchall()
        used = conn.execute(
            "SELECT kind, count(*), coalesce(sum(count), 0) FROM visitor_uses "
            "WHERE scope = 'visitor' GROUP BY kind ORDER BY kind"
        ).fetchall()
        switches = conn.execute(
            "SELECT name, turned_on FROM site_switches ORDER BY name"
        ).fetchall()
    return Standing(
        spent_usd=float(spent), spent_today_usd=float(today), calls=calls,
        calls_today=calls_today, failed_today=failed, unpriced=unpriced, last_call=last,
        by_purpose=tuple((name, count, float(cost)) for name, count, cost in purposes),
        used=tuple((kind, visitors, int(uses)) for kind, visitors, uses in used),
        switches=tuple((name, bool(on)) for name, on in switches),
    )  # fmt: skip


def alerts(found: Standing, total_usd: float, per_day_usd: float,
           share: float = ALERT_SHARE) -> list[str]:  # fmt: skip
    """The caps of which `share` is spent, in plain words; none when all is well."""
    said = []
    if found.spent_usd >= share * total_usd:
        said.append(f"{found.spent_usd / total_usd:.0%} of the whole budget is spent "
                    f"(${found.spent_usd:.2f} of ${total_usd:.2f}).")  # fmt: skip
    if found.spent_today_usd >= share * per_day_usd:
        said.append(f"{found.spent_today_usd / per_day_usd:.0%} of today's budget is spent "
                    f"(${found.spent_today_usd:.2f} of ${per_day_usd:.2f}, "
                    "the day in UTC).")  # fmt: skip
    return said


def report(found: Standing, total_usd: float, per_day_usd: float, warned: Sequence[str]) -> str:
    """The standing in Markdown, for the job's summary and its log."""
    lines = ["## The public copy's spending", ""]
    lines += [f"- **Alert:** {one}" for one in warned] or ["- No cap is near."]
    lines += [
        f"- Spent: ${found.spent_usd:.4f} of ${total_usd:.2f}, in {found.calls} calls to a model.",
        f"- Today (UTC): ${found.spent_today_usd:.4f} of ${per_day_usd:.2f}, in "
        f"{found.calls_today} calls, {found.failed_today} of them failed.",
        "- Last call: " + (found.last_call.astimezone(UTC).strftime("%d %B %Y, %H:%M UTC")
                           if found.last_call else "none yet") + ".",
    ]  # fmt: skip
    if found.unpriced:
        lines.append(f"- **Calls with no known price: {found.unpriced}.** The budget does not "
                     "count them: add their model to the price book.")  # fmt: skip
    turned = dict(found.switches)
    switches = ", ".join(f"{name} {'on' if turned.get(name) else 'off'}" for name in SWITCHES)
    lines.append(f"- Switches: {switches}.")
    if found.by_purpose:
        lines += ["", "| What the calls were for | Calls | Dollars |", "|---|---:|---:|"]
        lines += [f"| {name} | {count} | {cost:.4f} |" for name, count, cost in found.by_purpose]
    if found.used:
        lines += ["", "| What the visitors used | Visitors | Uses |", "|---|---:|---:|"]
        lines += [f"| {WHAT.get(kind, kind)} | {visitors} | {uses} |"
                  for kind, visitors, uses in found.used]  # fmt: skip
    return "\n".join(lines) + "\n"


def from_dotenv(path: Path, names: Sequence[str]) -> dict[str, str]:
    """The values of `names` in a .env file (NAME=value, the value maybe in quotes), with the
    standard library only, like the rest of the watch. No file, no values."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    found = {}
    for line in lines:
        name, equals, value = line.strip().removeprefix("export ").partition("=")
        if equals and name.strip() in names:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            found[name.strip()] = value
    return found


def main(environ: Mapping[str, str] | None = None, dotenv: Path | None = None) -> int:
    if environ is None:  # a real run: the environment, then the .env of the working folder
        environ, dotenv = os.environ, Path(".env")
    if dotenv is not None:
        environ = {**from_dotenv(dotenv, GIVEN), **environ}
    conninfo = environ.get(DATABASE, "")
    if not conninfo:
        print(f"{DATABASE} is not set, in the environment or in .env: the watch cannot read the "
              "public copy's database.")  # fmt: skip
        return 2
    total = float(environ.get("LLM_BUDGET_PUBLIC_USD") or TOTAL_USD)
    per_day = float(environ.get("LLM_BUDGET_PUBLIC_PER_DAY_USD") or PER_DAY_USD)
    try:
        found = standing(conninfo)
    except psycopg.Error as error:
        # the message of a connection error can hold the connection text, so only its kind
        print(f"The public copy's database could not be read ({type(error).__name__}).")
        return 2
    warned = alerts(found, total, per_day)
    text = report(found, total, per_day, warned)
    print(text)
    summary = environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as kept:
            kept.write(text)
    return 1 if warned else 0


if __name__ == "__main__":
    sys.exit(main())
