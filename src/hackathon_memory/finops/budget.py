"""The budget guard: a call is refused BEFORE it is made, when it could go over the budget.

Each environment has its own budget, so the test work cannot spend the money of the running tool,
and the running tool cannot be emptied by one busy day:

* "test" has one cap for all its calls.
* "prod" has a cap for all its calls and a cap for one day (the day is counted in UTC).
* "public", the public copy of the website (design 12.5), has the same two caps, of its own: a
  busy day of strangers cannot spend more than a day's share, nor the money of the tool.

The guard looks at the worst case of the next call: its prompt at the input price, and the most
output the call may produce at the output price. So the money that is really spent stays under the
cap, also when the last call is a big one. A warning starts at a share of the cap (80% by default).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from hackathon_memory.finops.calls import ENVIRONMENTS, CallStore
from hackathon_memory.settings import Settings


class BudgetExceeded(Exception):
    """The next call could go over the budget, so it is not made. The message gives the numbers."""


@dataclass(frozen=True)
class Budget:
    environment: str
    total_usd: float  # for all the calls of this environment
    per_day_usd: float | None = None  # for one day in UTC, or None for no daily cap
    warn_percent: int = 80

    def __post_init__(self) -> None:
        if self.environment not in ENVIRONMENTS:
            raise ValueError(f"The environment must be one of {', '.join(ENVIRONMENTS)}.")
        if self.total_usd < 0 or (self.per_day_usd is not None and self.per_day_usd < 0):
            raise ValueError("A budget cannot be negative.")
        if not 1 <= self.warn_percent <= 100:
            raise ValueError("The warning starts between 1 and 100 percent.")


@dataclass(frozen=True)
class BudgetStatus:
    environment: str
    spent_total_usd: float
    spent_today_usd: float
    total_usd: float
    per_day_usd: float | None
    state: str  # "ok", "warn" or "stop"
    reason: str

    @property
    def left_usd(self) -> float:
        """What can still be spent now: the smaller of the two amounts that are left."""
        left = self.total_usd - self.spent_total_usd
        if self.per_day_usd is not None:
            left = min(left, self.per_day_usd - self.spent_today_usd)
        return round(max(left, 0.0), 6)


def from_settings(settings: Settings, environment: str | None = None) -> Budget:
    """The budget of an environment, as .env sets it. The default is the environment in use."""
    name = environment or settings.llm_environment
    if name == "prod":
        return Budget(
            "prod",
            total_usd=settings.llm_budget_prod_usd,
            per_day_usd=settings.llm_budget_prod_per_day_usd,
            warn_percent=settings.llm_budget_warn_percent,
        )
    if name == "public":
        return Budget(
            "public",
            total_usd=settings.llm_budget_public_usd,
            per_day_usd=settings.llm_budget_public_per_day_usd,
            warn_percent=settings.llm_budget_warn_percent,
        )
    return Budget(
        "test",
        total_usd=settings.llm_budget_test_usd,
        warn_percent=settings.llm_budget_warn_percent,
    )


def status(
    budget: Budget,
    store: CallStore,
    now: datetime | None = None,
    next_call_usd: float = 0.0,
) -> BudgetStatus:
    """Where the budget stands, if a call that may cost `next_call_usd` were made now."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    spent_total = store.spent(budget.environment)
    spent_today = store.spent(budget.environment, since=start_of_day)

    def money(value: float) -> str:
        return f"{value:.4f}"

    state, reason = "ok", "inside the budget"
    if spent_total + next_call_usd > budget.total_usd:
        state = "stop"
        reason = (
            f"the budget of '{budget.environment}' is {money(budget.total_usd)} dollars, "
            f"{money(spent_total)} are spent, and the next call may cost {money(next_call_usd)}"
        )
    elif budget.per_day_usd is not None and spent_today + next_call_usd > budget.per_day_usd:
        state = "stop"
        reason = (
            f"the budget of '{budget.environment}' for one day is {money(budget.per_day_usd)} "
            f"dollars, {money(spent_today)} are spent today, and the next call may cost "
            f"{money(next_call_usd)}"
        )
    else:
        share = budget.warn_percent / 100
        if budget.total_usd > 0 and spent_total >= share * budget.total_usd:
            state = "warn"
            reason = (
                f"{money(spent_total)} of {money(budget.total_usd)} dollars are spent "
                f"({spent_total / budget.total_usd:.0%} of the budget of '{budget.environment}')"
            )
        elif (
            budget.per_day_usd is not None
            and budget.per_day_usd > 0
            and spent_today >= share * budget.per_day_usd
        ):
            state = "warn"
            reason = (
                f"{money(spent_today)} of {money(budget.per_day_usd)} dollars are spent today "
                f"({spent_today / budget.per_day_usd:.0%} of the budget of one day)"
            )
    return BudgetStatus(
        environment=budget.environment,
        spent_total_usd=round(spent_total, 6),
        spent_today_usd=round(spent_today, 6),
        total_usd=budget.total_usd,
        per_day_usd=budget.per_day_usd,
        state=state,
        reason=reason,
    )


def require(
    budget: Budget,
    store: CallStore,
    now: datetime | None = None,
    next_call_usd: float = 0.0,
) -> BudgetStatus:
    """The status, or BudgetExceeded when the next call must not be made."""
    current = status(budget, store, now, next_call_usd)
    if current.state == "stop":
        raise BudgetExceeded(
            f"The call was not made: {current.reason}. Change the budget in .env "
            "(LLM_BUDGET_...) if this is wanted."
        )
    return current
