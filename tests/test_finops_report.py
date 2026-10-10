"""The report of the costs: sums, unit costs, second attempts, other prices, and the bill."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from hackathon_memory.db.migrate import migrate
from hackathon_memory.finops import budget as budgets
from hackathon_memory.finops import report
from hackathon_memory.finops.__main__ import main
from hackathon_memory.finops.budget import Budget
from hackathon_memory.finops.calls import Call, MemoryStore, PostgresStore
from hackathon_memory.settings import Settings

FLASH = "gemini-3.8-flash"
PRO = "gemini-3.1-pro-preview"
EMBED = "gemini-embedding-001"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


def call(**changes: object) -> Call:
    values: dict = {
        "environment": "test",
        "purpose": "rewrite",
        "model": PRO,
        "input_tokens": 1000,
        "output_tokens": 200,
        "thinking_tokens": 300,
        "thinking_level": "HIGH",
        "latency_ms": 10_000,
        "called_at": NOW,
    }
    return Call(**(values | changes)).priced()


def ledger() -> list[Call]:
    """Three project pages (one needed a second attempt), two searches, one failed call."""
    return [
        call(item_ref="p1", latency_ms=12_000),  # 0.008
        call(item_ref="p2", latency_ms=14_000, called_at=NOW + timedelta(minutes=1)),  # first try
        call(item_ref="p2", latency_ms=16_000, called_at=NOW + timedelta(minutes=2)),  # second try
        call(item_ref="p3", latency_ms=20_000, called_at=NOW - timedelta(days=1)),
        call(
            purpose="embed_query",
            model=EMBED,
            run_id="s1",
            input_tokens=9,
            output_tokens=0,
            thinking_tokens=0,
            thinking_level=None,
            latency_ms=300,
        ),
        call(purpose="search", model=FLASH, run_id="s1", latency_ms=40_000),  # 0.002625
        call(purpose="search", model=FLASH, run_id="s2", latency_ms=50_000),
        call(
            purpose="search",
            model=FLASH,
            run_id="s3",
            input_tokens=0,
            output_tokens=0,
            thinking_tokens=0,
            ok=False,
            error_kind="ServerError",
            latency_ms=900,
        ),
        call(environment="prod", purpose="search", model=FLASH, run_id="live-1"),
    ]


# --------------------------------------------------------------------- sums


def test_the_total_counts_one_environment_only() -> None:
    built = report.build(ledger(), "test")
    assert built.total.calls == 8
    assert built.total.failed == 1
    assert built.total.unpriced_calls == 1  # the embedding call
    assert built.total.cost_usd == pytest.approx(4 * 0.008 + 2 * 0.002625)
    assert built.total.thinking_share == pytest.approx(1800 / 3000)
    assert report.build(ledger(), "prod").total.calls == 1


def test_the_calls_are_grouped_by_use_and_the_dearest_use_comes_first() -> None:
    built = report.build(ledger(), "test")
    labels = [g.label for g in built.by_use]
    assert labels[0] == ("rewrite", PRO, "HIGH")
    assert ("search", FLASH, "HIGH") in labels
    assert ("embed_query", EMBED, "-") in labels
    rewrite = built.by_use[0]
    assert (rewrite.calls, rewrite.cost_usd) == (4, pytest.approx(0.032))
    assert rewrite.mean_cost_usd == pytest.approx(0.008)
    assert (rewrite.latency_p50_ms, rewrite.latency_p95_ms) == (14_000, 20_000)


def test_the_time_of_a_failed_call_is_not_mixed_with_the_time_of_an_answer() -> None:
    search = next(g for g in report.build(ledger(), "test").by_use if g.label[0] == "search")
    assert search.failed == 1
    assert search.latency_p50_ms == 40_000  # of the two calls that answered


def test_the_calls_are_grouped_by_day_in_utc() -> None:
    built = report.build(ledger(), "test")
    assert [(d, n) for d, n, _ in built.by_day] == [(TODAY - timedelta(days=1), 1), (TODAY, 7)]


def test_a_range_of_time_leaves_out_what_is_outside() -> None:
    built = report.build(ledger(), "test", since=NOW - timedelta(hours=1))
    assert built.total.calls == 7
    assert report.build(ledger(), "test", until=NOW).total.calls == 1


@pytest.mark.parametrize(
    ("values", "share", "expected"),
    [
        ([], 0.5, None),
        ([5.0], 0.95, 5.0),
        ([1.0, 2.0, 3.0, 4.0], 0.5, 2.0),
        ([1.0, 2.0, 3.0, 4.0], 0.95, 4.0),
    ],
)
def test_percentile(values: list[float], share: float, expected: float | None) -> None:
    assert report.percentile(values, share) == expected


# --------------------------------------------------------------------- unit costs


def test_one_project_page_has_a_cost_and_second_attempts_are_counted() -> None:
    [rewrite] = report.build(ledger(), "test").per_item
    assert (rewrite.label, rewrite.units, rewrite.calls) == ("rewrite", 3, 4)
    assert rewrite.total_usd == pytest.approx(0.032)
    assert rewrite.mean_usd == pytest.approx(0.032 / 3)
    assert rewrite.p95_usd == pytest.approx(0.016)  # the page that needed two attempts
    assert (rewrite.extra_calls, rewrite.extra_usd) == (1, pytest.approx(0.008))


def test_one_search_has_a_cost_that_adds_its_calls() -> None:
    run = report.build(ledger(), "test").per_run
    assert run is not None
    assert (run.units, run.calls) == (3, 4)  # s1 has two calls: the embedding and the model
    assert run.mean_usd == pytest.approx(2 * 0.002625 / 3)


def test_a_ledger_with_no_item_and_no_run_has_no_unit_cost() -> None:
    built = report.build([call()], "test")
    assert built.per_item == []
    assert built.per_run is None


# --------------------------------------------------------------------- other prices


def test_the_same_tokens_can_be_priced_with_another_model() -> None:
    pages = [c for c in ledger() if c.purpose == "rewrite"]
    assert report.repriced(pages) == pytest.approx(0.032)
    assert report.repriced(pages, model=FLASH) == pytest.approx(4 * 0.002625)
    assert report.repriced(pages, model="gemini-9-unknown") is None


def test_an_announced_change_of_price_is_shown_for_the_calls_that_it_touches() -> None:
    changes = report.price_changes([c for c in ledger() if c.environment == "test"], TODAY)
    [flash] = changes  # Pro has no change that is known, and the embedding model has no price
    assert (flash.model, flash.day) == (FLASH, date(2027, 1, 1))
    assert flash.cost_then_usd == pytest.approx(2 * flash.cost_now_usd)


# --------------------------------------------------------------------- the budget in time


def test_the_daily_rate_and_the_days_that_are_left() -> None:
    built = report.build(ledger(), "test")
    rate = report.daily_rate(built, TODAY, days=7)
    assert rate == pytest.approx((4 * 0.008 + 2 * 0.002625) / 7)
    store = MemoryStore()
    for line in ledger():
        store.add(line)
    status = budgets.status(Budget("test", 1.0), store, NOW)
    assert report.days_left(status, rate) == pytest.approx((1.0 - 0.03725) / rate, abs=0.1)
    assert report.days_left(status, 0.0) is None


# --------------------------------------------------------------------- the bill


def test_a_count_close_to_the_bill_agrees() -> None:
    result = report.reconcile(counted_usd=9.80, billed_usd=10.00)
    assert (result.gap_usd, result.gap_percent) == (pytest.approx(0.20), 2.0)
    assert "agree" in result.verdict


def test_a_bill_that_is_higher_points_at_what_is_not_counted() -> None:
    result = report.reconcile(counted_usd=6.0, billed_usd=10.0, unpriced_calls=12)
    assert result.gap_percent == 40.0
    assert "HIGHER" in result.verdict
    assert "12 counted call(s) have no known price" in result.verdict


def test_a_bill_that_is_lower_points_at_the_price_book_or_the_days() -> None:
    result = report.reconcile(counted_usd=10.0, billed_usd=6.0)
    assert "LOWER" in result.verdict
    assert report.reconcile(0.0, 0.0).verdict.startswith("Nothing")


# --------------------------------------------------------------------- as text and as data


def test_the_text_of_the_report_says_the_main_things() -> None:
    lines = ledger()
    store = MemoryStore()
    for line in lines:
        store.add(line)
    built = report.build(lines, "test")
    status = budgets.status(Budget("test", 1.0), store, NOW)
    text = report.render(
        built,
        status=status,
        today=TODAY,
        items_planned=2100,
        other_models=(PRO, FLASH),
        all_calls=lines,
    )
    assert "environment 'test'" in text
    assert "Calls: 8 (1 failed)" in text
    assert "Spent: $0.0372" in text
    assert "NOT in this sum: 1 call(s)" in text
    assert "Thinking is 60% of the output tokens" in text
    assert "State: OK" in text
    assert "rewrite / gemini-3.1-pro-preview / HIGH: 4 call(s), $0.0320" in text
    assert "1 second attempt(s) cost $0.0080 (25% of this work)" in text
    assert "2,100 items at this cost: $22.4000" in text
    assert f"All with {FLASH}" in text
    assert "gemini-3.8-flash from 2027-01-01" in text
    assert "reconcile --billed" in text


def test_the_report_as_data_has_no_text_of_a_page_and_names_its_price_source() -> None:
    data = report.as_dict(report.build(ledger(), "test"))
    assert data["total"]["calls"] == 8
    assert data["per_item"][0]["units"] == 3
    assert data["price_book_read_on"] == "2026-10-10"
    json.dumps(data)  # it must be plain data


# --------------------------------------------------------------------- the command line


def filled() -> MemoryStore:
    store = MemoryStore()
    for line in ledger():
        store.add(line)
    return store


def test_the_command_report_prints_the_environment_in_use(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["report", "--items", "70"], Settings(_env_file=None), filled(), NOW)
    out = capsys.readouterr().out
    assert code == 0
    assert "environment 'test'" in out
    assert "70 items at this cost" in out
    assert main(["report", "--env", "prod"], Settings(_env_file=None), filled(), NOW) == 0
    assert "environment 'prod'" in capsys.readouterr().out


def test_the_command_report_can_take_the_last_days_only(capsys: pytest.CaptureFixture[str]) -> None:
    main(["report", "--days", "1"], Settings(_env_file=None), filled(), NOW)
    assert "Calls: 7 (1 failed)" in capsys.readouterr().out


def test_the_command_report_can_save_a_dated_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    assert main(["report", "--save"], settings, filled(), NOW) == 0
    [saved] = list((tmp_path / "finops").glob("*.json"))
    assert saved.name == "20261010T120000Z-test.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["total"]["calls"] == 8
    assert "Saved:" in capsys.readouterr().out


def test_the_command_budget_shows_both_environments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["budget"], Settings(_env_file=None), filled(), NOW) == 0
    out = capsys.readouterr().out
    assert "test: spent $0.0372 of $15.00" in out
    assert "prod: spent $0.0026 of $30.00, today $0.0026 of $5.00" in out


def test_the_command_prices_needs_no_database(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["prices"]) == 0
    out = capsys.readouterr().out
    assert "gemini-3.8-flash, from 2027-01-01: input 1.500, output 7.500" in out
    assert "A prompt above 200,000 tokens" in out


def test_the_command_reconcile_compares_with_the_bill(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["reconcile", "--billed", "0.04", "--env", "test"], Settings(_env_file=None), filled(), NOW
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Our count: $0.0372 (8 call(s), environment test)" in out
    assert "BEFORE credits" in out
    main(
        ["reconcile", "--billed", "0.008", "--from", "2026-10-09", "--to", "2026-10-09"],
        Settings(_env_file=None),
        filled(),
        NOW,
    )
    assert "Our count: $0.0080 (1 call(s), environment all)" in capsys.readouterr().out


def test_a_wrong_command_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["spend-it-all"]) == 2
    assert main(["reconcile"]) == 2  # the amount on the bill is needed
    capsys.readouterr()


def test_the_commands_say_what_to_do_when_the_table_is_missing(
    empty_database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, database_url=empty_database)
    assert main(["budget"], settings) == 2
    assert "db migrate" in capsys.readouterr().out
    migrate(empty_database)
    PostgresStore(empty_database).add(call())
    assert main(["budget"], settings, now=NOW) == 0
    assert "test: spent $0.0080 of $15.00" in capsys.readouterr().out


def test_the_commands_say_what_to_do_when_the_database_does_not_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unreachable = "postgresql://nobody:nothing@127.0.0.1:1/none?connect_timeout=2"
    assert main(["report"], Settings(_env_file=None, database_url=unreachable)) == 2
    out = capsys.readouterr().out
    assert "docker compose up" in out
    assert "nothing" not in out  # the connection text is never shown
