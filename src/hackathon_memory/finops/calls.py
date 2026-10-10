"""One line for every call to a model, and the place where the lines are kept.

A line holds numbers only: which model, how many tokens, how long it took, what it cost. It never
holds the text that was sent or the text that came back. So the table of calls can be shown,
exported and compared with the bill without showing a page or an idea of a user.

Two places keep the lines. `PostgresStore` is the real one (table llm_calls, migration 0002).
`MemoryStore` is for tests and for a dry run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Protocol

import psycopg

from hackathon_memory.finops import prices
from hackathon_memory.settings import Settings, SettingsError

# "test" is all the work before the tool is shown: the proofs, the tests, the first runs.
# "prod" is the tool while people use it.
ENVIRONMENTS = ("test", "prod")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class CallError(ValueError):
    """A line of the ledger is not valid. The message holds no text of a page."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Call:
    """One call to a model. Tokens are the numbers that Google reported for it."""

    environment: str
    purpose: str  # what the call was for: rewrite, search, embed_document, embed_query, proof
    model: str
    input_tokens: int
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0
    thinking_level: str | None = None
    location: str | None = None
    batch: bool = False
    latency_ms: int | None = None
    ok: bool = True
    error_kind: str | None = None  # the class of the error, never its text
    run_id: str | None = None  # one job, one test run, or one search of a user
    item_ref: str | None = None  # what the call was for: a project, a test case
    called_at: datetime = field(default_factory=_now)
    cost_usd: float | None = None  # None when the price of the model is not known
    price_read_on: date | None = None

    def __post_init__(self) -> None:
        if self.environment not in ENVIRONMENTS:
            raise CallError(f"The environment must be one of {', '.join(ENVIRONMENTS)}.")
        if not _SLUG.match(self.purpose):
            raise CallError("The purpose must be a short word in small letters, like 'rewrite'.")
        if not self.model:
            raise CallError("A call needs the name of its model.")
        counts = (self.input_tokens, self.output_tokens, self.thinking_tokens, self.cached_tokens)
        if any(count < 0 for count in counts):
            raise CallError("A count of tokens cannot be negative.")
        if self.called_at.tzinfo is None:
            raise CallError("The time of a call must say its time zone.")

    def priced(self) -> Call:
        """The same call with its cost, from the price book of the day it was made."""
        day = self.called_at.astimezone(UTC).date()
        cost = prices.cost_usd(
            self.model,
            day,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            thinking_tokens=self.thinking_tokens,
            cached_tokens=self.cached_tokens,
            batch=self.batch,
        )
        price = prices.price_on(self.model, day)
        return replace(self, cost_usd=cost, price_read_on=price.read_on if price else None)

    def repriced(self, model: str | None = None, on: date | None = None) -> float | None:
        """What the same tokens would cost with another model, or on another day."""
        day = on or self.called_at.astimezone(UTC).date()
        return prices.cost_usd(
            model or self.model,
            day,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            thinking_tokens=self.thinking_tokens,
            cached_tokens=self.cached_tokens,
            batch=self.batch,
        )


class CallStore(Protocol):
    def add(self, call: Call) -> None: ...

    def spent(self, environment: str, since: datetime | None = None) -> float: ...

    def calls(
        self,
        environment: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Call]: ...


class MemoryStore:
    """Keeps the lines in a list. For tests, and for a run that must not touch the database."""

    def __init__(self) -> None:
        self._calls: list[Call] = []

    def add(self, call: Call) -> None:
        self._calls.append(call if call.cost_usd is not None else call.priced())

    def spent(self, environment: str, since: datetime | None = None) -> float:
        return round(sum(c.cost_usd or 0.0 for c in self.calls(environment, since)), 8)

    def calls(
        self,
        environment: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Call]:
        return [
            c
            for c in self._calls
            if (environment is None or c.environment == environment)
            and (since is None or c.called_at >= since)
            and (until is None or c.called_at < until)
        ]


_COLUMNS = (
    "called_at, environment, purpose, model, thinking_level, location, batch, input_tokens, "
    "output_tokens, thinking_tokens, cached_tokens, latency_ms, ok, error_kind, cost_usd, "
    "price_read_on, run_id, item_ref"
)


class PostgresStore:
    """Keeps the lines in the table llm_calls. Opens a short connection for each operation."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._conninfo, autocommit=True)

    def add(self, call: Call) -> None:
        priced = call if call.cost_usd is not None else call.priced()
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO llm_calls ({_COLUMNS}) VALUES "  # noqa: S608  (no user input)
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    priced.called_at,
                    priced.environment,
                    priced.purpose,
                    priced.model,
                    priced.thinking_level,
                    priced.location,
                    priced.batch,
                    priced.input_tokens,
                    priced.output_tokens,
                    priced.thinking_tokens,
                    priced.cached_tokens,
                    priced.latency_ms,
                    priced.ok,
                    priced.error_kind,
                    priced.cost_usd,
                    priced.price_read_on,
                    priced.run_id,
                    priced.item_ref,
                ),
            )

    def spent(self, environment: str, since: datetime | None = None) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls "
                "WHERE environment = %s AND (%s::timestamptz IS NULL OR called_at >= %s)",
                (environment, since, since),
            ).fetchone()
        return float(row[0]) if row else 0.0

    def calls(
        self,
        environment: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Call]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM llm_calls "  # noqa: S608  (no user input)
                "WHERE (%s::text IS NULL OR environment = %s) "
                "AND (%s::timestamptz IS NULL OR called_at >= %s) "
                "AND (%s::timestamptz IS NULL OR called_at < %s) ORDER BY called_at, id",
                (environment, environment, since, since, until, until),
            ).fetchall()
        return [
            Call(
                called_at=row[0],
                environment=row[1],
                purpose=row[2],
                model=row[3],
                thinking_level=row[4],
                location=row[5],
                batch=row[6],
                input_tokens=row[7],
                output_tokens=row[8],
                thinking_tokens=row[9],
                cached_tokens=row[10],
                latency_ms=row[11],
                ok=row[12],
                error_kind=row[13],
                cost_usd=float(row[14]) if row[14] is not None else None,
                price_read_on=row[15],
                run_id=row[16],
                item_ref=row[17],
            )
            for row in rows
        ]


class LedgerNotReady(Exception):
    """The ledger cannot be written. The message says what to do, and holds no connection text."""


def open_ledger(settings: Settings) -> PostgresStore:
    """The ledger of the settings, after a check that it answers. Raises LedgerNotReady if not.

    A job that pays for calls uses this before its first call: a call that cannot be counted
    must not be made.
    """
    try:
        store = PostgresStore(settings.database_conninfo())
        store.spent(settings.llm_environment)
    except SettingsError as problem:
        raise LedgerNotReady(str(problem)) from None
    except psycopg.errors.UndefinedTable:
        raise LedgerNotReady(
            "The table of calls does not exist yet. Run: python -m hackathon_memory.db migrate"
        ) from None
    except psycopg.OperationalError:
        # The text of this error is not shown on purpose: it can hold connection details.
        raise LedgerNotReady(
            "The database does not answer. Start it with: docker compose up -d --wait db"
        ) from None
    return store
