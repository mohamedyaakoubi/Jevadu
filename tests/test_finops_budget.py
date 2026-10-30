"""The budget guard: a call is refused before it is made, when it could go over the budget."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hackathon_memory.finops import budget as budgets
from hackathon_memory.finops.budget import Budget, BudgetExceeded
from hackathon_memory.finops.calls import Call, MemoryStore
from hackathon_memory.settings import Settings

PRO = "gemini-3.1-pro-preview"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def spend(
    store: MemoryStore, dollars: float, environment: str = "test", when: datetime = NOW
) -> None:
    """Add one call that costs exactly this much (output tokens of Pro at 12 dollars a million)."""
    tokens = round(dollars * 1_000_000 / 12)
    store.add(Call(environment, "rewrite", PRO, 0, output_tokens=tokens, called_at=when))


def test_an_empty_ledger_is_inside_the_budget() -> None:
    status = budgets.status(Budget("test", 10.0), MemoryStore(), NOW)
    assert (status.state, status.spent_total_usd, status.left_usd) == ("ok", 0.0, 10.0)


def test_the_warning_starts_at_the_share_that_was_set() -> None:
    store = MemoryStore()
    spend(store, 7.9)
    assert budgets.status(Budget("test", 10.0), store, NOW).state == "ok"
    spend(store, 0.2)  # 8.1 of 10
    status = budgets.status(Budget("test", 10.0), store, NOW)
    assert status.state == "warn"
    assert "81%" in status.reason
    assert budgets.status(Budget("test", 10.0, warn_percent=90), store, NOW).state == "ok"


def test_a_call_that_could_go_over_the_cap_is_stopped_before_it_is_made() -> None:
    store = MemoryStore()
    spend(store, 9.5)
    budget = Budget("test", 10.0)
    assert budgets.status(budget, store, NOW, next_call_usd=0.4).state == "warn"
    status = budgets.status(budget, store, NOW, next_call_usd=0.6)
    assert status.state == "stop"
    with pytest.raises(BudgetExceeded) as refusal:
        budgets.require(budget, store, NOW, next_call_usd=0.6)
    text = str(refusal.value)
    assert "10.0000" in text and "9.5000" in text and "0.6000" in text  # the numbers are given
    assert "LLM_BUDGET" in text  # and where to change the cap


def test_the_money_that_is_spent_stays_under_the_cap() -> None:
    """With the worst case checked before each call, the total never passes the cap."""
    store = MemoryStore()
    budget = Budget("test", 1.0)
    made = 0
    for _ in range(100):
        try:
            budgets.require(budget, store, NOW, next_call_usd=0.03)
        except BudgetExceeded:
            break
        spend(store, 0.03)
        made += 1
    assert made == 33
    assert store.spent("test") <= 1.0


def test_one_environment_does_not_spend_the_budget_of_the_other() -> None:
    store = MemoryStore()
    spend(store, 9.9, environment="test")
    assert budgets.status(Budget("test", 10.0), store, NOW, next_call_usd=0.5).state == "stop"
    assert budgets.status(Budget("prod", 10.0), store, NOW, next_call_usd=0.5).state == "ok"


def test_the_daily_cap_counts_the_day_in_utc_only() -> None:
    store = MemoryStore()
    spend(store, 4.0, environment="prod", when=NOW - timedelta(days=1))
    spend(store, 1.9, environment="prod", when=NOW)
    budget = Budget("prod", total_usd=30.0, per_day_usd=2.0)
    assert budgets.status(budget, store, NOW).spent_today_usd == pytest.approx(1.9, abs=1e-4)
    stopped = budgets.status(budget, store, NOW, next_call_usd=0.2)
    assert stopped.state == "stop"
    assert "one day" in stopped.reason
    # At the first second of the next day the daily cap is fresh, and the total still counts.
    tomorrow = datetime(2026, 10, 11, 0, 0, 1, tzinfo=UTC)
    fresh = budgets.status(budget, store, tomorrow, next_call_usd=0.2)
    assert (fresh.state, fresh.spent_today_usd) == ("ok", 0.0)
    assert fresh.spent_total_usd == pytest.approx(5.9, abs=1e-4)


def test_what_is_left_is_the_smaller_of_the_two_caps() -> None:
    store = MemoryStore()
    spend(store, 1.5, environment="prod")
    assert budgets.status(Budget("prod", 30.0, per_day_usd=2.0), store, NOW).left_usd == 0.5
    assert budgets.status(Budget("prod", 1.6, per_day_usd=2.0), store, NOW).left_usd == 0.1
    spend(store, 5.0, environment="prod")
    assert budgets.status(Budget("prod", 1.6, per_day_usd=2.0), store, NOW).left_usd == 0.0


def test_the_budgets_come_from_the_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_budget_test_usd=3.0,
        llm_budget_prod_usd=40.0,
        llm_budget_prod_per_day_usd=4.0,
        llm_budget_public_usd=20.0,
        llm_budget_public_per_day_usd=2.0,
        llm_budget_warn_percent=70,
    )
    assert budgets.from_settings(settings) == Budget("test", 3.0, None, 70)  # test is the default
    assert budgets.from_settings(settings, "prod") == Budget("prod", 40.0, 4.0, 70)
    assert budgets.from_settings(settings, "public") == Budget("public", 20.0, 2.0, 70)
    in_prod = Settings(_env_file=None, llm_environment="PROD")
    assert budgets.from_settings(in_prod).environment == "prod"


def test_the_default_budgets_are_small() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_environment == "test"
    assert budgets.from_settings(settings).total_usd == 15.0
    prod = budgets.from_settings(settings, "prod")
    assert (prod.total_usd, prod.per_day_usd) == (30.0, 5.0)
    public = budgets.from_settings(settings, "public")  # the public copy's own (design 12.5)
    assert (public.total_usd, public.per_day_usd) == (30.0, 5.0)


def test_the_public_copy_never_spends_the_budget_of_the_tool() -> None:
    store = MemoryStore()
    spend(store, 29.9, environment="public")
    public = budgets.status(Budget("public", 30.0, 5.0), store, NOW, next_call_usd=0.5)
    assert public.state == "stop"
    assert budgets.status(Budget("prod", 30.0, 5.0), store, NOW, next_call_usd=0.5).state == "ok"


@pytest.mark.parametrize(
    "bad",
    [
        {"environment": "staging", "total_usd": 1.0},
        {"environment": "test", "total_usd": -1.0},
        {"environment": "prod", "total_usd": 1.0, "per_day_usd": -0.5},
        {"environment": "test", "total_usd": 1.0, "warn_percent": 0},
        {"environment": "test", "total_usd": 1.0, "warn_percent": 101},
    ],
)
def test_a_budget_that_makes_no_sense_is_refused(bad: dict) -> None:
    with pytest.raises(ValueError):
        Budget(**bad)


def test_a_setting_that_makes_no_sense_is_refused() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_environment="staging")
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_budget_test_usd=-1)
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_budget_warn_percent=0)
