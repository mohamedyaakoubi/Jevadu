"""The ledger of calls: one line for each call, numbers only, in memory and in PostgreSQL."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest

from hackathon_memory.db.migrate import migrate
from hackathon_memory.finops.calls import (
    Call,
    CallError,
    LedgerNotReady,
    MemoryStore,
    PostgresStore,
    open_ledger,
)
from hackathon_memory.settings import Settings

FLASH = "gemini-3.8-flash"
PRO = "gemini-3.1-pro-preview"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def call(**changes: object) -> Call:
    values: dict = {
        "environment": "test",
        "purpose": "rewrite",
        "model": PRO,
        "input_tokens": 1000,
        "output_tokens": 200,
        "thinking_tokens": 300,
        "called_at": NOW,
    }
    return Call(**(values | changes))


# --------------------------------------------------------------------- one line


def test_a_line_gets_its_cost_from_the_price_book_of_its_day() -> None:
    priced = call().priced()
    assert priced.cost_usd == pytest.approx(0.008)  # 1000 in at 2.00, 500 out at 12.00
    assert priced.price_read_on == date(2026, 10, 10)
    in_2027 = call(model=FLASH, called_at=datetime(2027, 1, 1, tzinfo=UTC)).priced()
    in_2026 = call(model=FLASH).priced()
    assert in_2027.cost_usd == pytest.approx(2 * in_2026.cost_usd)


def test_a_line_of_a_model_with_no_known_price_has_no_cost() -> None:
    priced = call(model="gemini-embedding-001", output_tokens=0, thinking_tokens=0).priced()
    assert priced.cost_usd is None
    assert priced.price_read_on is None


def test_the_same_tokens_can_be_priced_with_another_model_or_day() -> None:
    line = call()
    assert line.repriced(FLASH) == pytest.approx(0.002625)
    assert line.repriced(FLASH, on=date(2027, 1, 1)) == pytest.approx(0.00525)
    assert line.repriced("gemini-9-unknown") is None


@pytest.mark.parametrize(
    "bad",
    [
        {"environment": "staging"},
        {"purpose": "Rewrite pages!"},
        {"purpose": ""},
        {"model": ""},
        {"input_tokens": -1},
        {"thinking_tokens": -5},
        {"called_at": datetime(2026, 10, 10, 12, 0)},  # no time zone
    ],
)
def test_a_line_that_is_not_valid_is_refused(bad: dict) -> None:
    with pytest.raises(CallError):
        call(**bad)


# --------------------------------------------------------------------- in memory


def test_the_memory_store_adds_up_by_environment_and_by_time() -> None:
    store = MemoryStore()
    store.add(call())  # 0.008
    store.add(call(environment="prod", model=FLASH))  # 0.002625
    store.add(call(called_at=NOW - timedelta(days=2)))  # 0.008, two days ago
    assert store.spent("test") == pytest.approx(0.016)
    assert store.spent("prod") == pytest.approx(0.002625)
    assert store.spent("test", since=NOW - timedelta(hours=1)) == pytest.approx(0.008)
    assert len(store.calls()) == 3
    assert len(store.calls("test", until=NOW)) == 1


def test_a_call_with_no_known_price_adds_nothing_to_what_was_spent() -> None:
    store = MemoryStore()
    store.add(call(model="gemini-embedding-001", output_tokens=0, thinking_tokens=0))
    assert store.spent("test") == 0.0
    assert store.calls()[0].cost_usd is None


# --------------------------------------------------------------------- in PostgreSQL


def test_the_database_keeps_a_line_as_it_was_written(empty_database: str) -> None:
    migrate(empty_database)
    store = PostgresStore(empty_database)
    written = call(
        thinking_level="HIGH",
        location="global",
        latency_ms=13800,
        run_id="run-1",
        item_ref="project-7",
        cached_tokens=100,
    )
    store.add(written)
    [read] = store.calls("test")
    assert read == written.priced()


def test_the_database_adds_up_like_the_memory_store(empty_database: str) -> None:
    migrate(empty_database)
    store = PostgresStore(empty_database)
    store.add(call())
    store.add(call(environment="prod", model=FLASH))
    store.add(call(called_at=NOW - timedelta(days=2)))
    store.add(call(model="gemini-embedding-001", output_tokens=0, thinking_tokens=0))
    assert store.spent("test") == pytest.approx(0.016)
    assert store.spent("prod") == pytest.approx(0.002625)
    assert store.spent("test", since=NOW - timedelta(hours=1)) == pytest.approx(0.008)
    # Oldest first: the call of two days ago, then the three of today in the order they were added.
    assert [c.environment for c in store.calls()] == ["test", "test", "prod", "test"]
    assert len(store.calls("test", since=NOW)) == 2
    assert store.calls("test", since=NOW)[-1].cost_usd is None  # the price was not known


def test_a_failed_call_is_kept_with_the_class_of_its_error(empty_database: str) -> None:
    migrate(empty_database)
    store = PostgresStore(empty_database)
    store.add(
        call(input_tokens=0, output_tokens=0, thinking_tokens=0, ok=False, error_kind="ServerError")
    )
    [read] = store.calls()
    assert (read.ok, read.error_kind, read.cost_usd) == (False, "ServerError", 0.0)


def test_the_table_refuses_a_line_that_the_code_would_refuse(empty_database: str) -> None:
    migrate(empty_database)
    insert = (
        "INSERT INTO llm_calls (environment, purpose, model, input_tokens, ok) "
        "VALUES (%s, %s, %s, %s, true)"
    )
    for bad in (
        ("staging", "rewrite", PRO, 10),
        ("test", "Rewrite pages!", PRO, 10),
        ("test", "rewrite", "", 10),
        ("test", "rewrite", PRO, -1),
    ):
        with psycopg.connect(empty_database, autocommit=True) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(insert, bad)


def test_the_table_has_no_column_for_the_text_of_a_call(empty_database: str) -> None:
    """The ledger holds numbers and labels. A column for a prompt or an answer must not appear."""
    migrate(empty_database)
    with psycopg.connect(empty_database) as conn:
        columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'llm_calls'"
            )
        }
    assert columns == {
        "id",
        "called_at",
        "environment",
        "purpose",
        "model",
        "thinking_level",
        "location",
        "batch",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "cached_tokens",
        "latency_ms",
        "ok",
        "error_kind",
        "cost_usd",
        "price_read_on",
        "run_id",
        "item_ref",
    }


# --------------------------------------------------------------------- a ledger that is checked


def test_a_ready_ledger_is_opened(empty_database: str) -> None:
    migrate(empty_database)
    store = open_ledger(Settings(_env_file=None, database_url=empty_database))
    store.add(call())
    assert store.spent("test") == pytest.approx(0.008)


def test_a_ledger_with_no_table_says_how_to_make_it(empty_database: str) -> None:
    with pytest.raises(LedgerNotReady, match="db migrate"):
        open_ledger(Settings(_env_file=None, database_url=empty_database))


def test_a_ledger_that_does_not_answer_says_so_without_the_connection_text() -> None:
    unreachable = "postgresql://nobody:hidden-word@127.0.0.1:1/none?connect_timeout=2"
    with pytest.raises(LedgerNotReady, match="docker compose up") as problem:
        open_ledger(Settings(_env_file=None, database_url=unreachable))
    assert "hidden-word" not in str(problem.value)


def test_a_ledger_with_no_password_says_what_is_missing() -> None:
    with pytest.raises(LedgerNotReady, match="POSTGRES_PASSWORD"):
        open_ledger(Settings(_env_file=None))
