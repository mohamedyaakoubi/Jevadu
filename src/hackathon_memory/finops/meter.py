"""The meter: every call to a model is counted, and none can go around the count.

`MeteredClient` stands in for the Google client. The code that asks a model for something does not
change: it gets a metered client and uses it as before. Each call then does three things:

1. BEFORE: the budget guard looks at the worst case of the call. If it could go over the budget,
   the call is not made (BudgetExceeded).
2. The real call, with its time measured.
3. AFTER: one line goes to the ledger, with the tokens that Google reported. A call that failed
   gets a line too, with the class of its error.

The meter knows two calls: `generate_content` and `embed_content`. A method that would cost money
and that the meter does not know is REFUSED, not passed through: a new kind of call must be taught
to the meter first. That is how "every call is counted" stays true next month.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from hackathon_memory.finops import budget as budgets
from hackathon_memory.finops import prices
from hackathon_memory.finops.calls import Call, CallStore

# Methods of the Google client that cost nothing and may pass through uncounted.
_FREE_METHODS = frozenset({"count_tokens", "compute_tokens", "get", "list"})
# The most output a call may produce when it does not say (used for the worst case only).
DEFAULT_MAX_OUTPUT_TOKENS = 8192
# About 4 letters make one token in English. 3 is used, so that the estimate is on the high side.
_LETTERS_PER_TOKEN = 3


@dataclass(frozen=True)
class Tags:
    """What a call is for. They go into the ledger with the call."""

    purpose: str
    run_id: str | None = None
    item_ref: str | None = None


class Meter:
    def __init__(
        self,
        store: CallStore,
        environment: str,
        budget: budgets.Budget | None = None,
        location: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if budget is not None and budget.environment != environment:
            raise ValueError("The budget belongs to another environment than the meter.")
        self.store = store
        self.environment = environment
        self.budget = budget
        self.location = location
        self.now = now or (lambda: datetime.now(UTC))

    def before_call(self, model: str, input_tokens: int, max_output_tokens: int) -> None:
        """Refuse the call if its worst case could go over the budget."""
        if self.budget is None:
            return
        moment = self.now()
        worst = prices.cost_usd(
            model,
            moment.astimezone(UTC).date(),
            input_tokens=input_tokens,
            output_tokens=max_output_tokens,
        )
        # A model with no known price cannot be guarded: its calls are still counted.
        budgets.require(self.budget, self.store, moment, next_call_usd=worst or 0.0)

    def record(
        self,
        tags: Tags,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
        cached_tokens: int = 0,
        thinking_level: str | None = None,
        latency_ms: int | None = None,
        ok: bool = True,
        error_kind: str | None = None,
        batch: bool = False,
    ) -> Call:
        call = Call(
            environment=self.environment,
            purpose=tags.purpose,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cached_tokens=cached_tokens,
            thinking_level=thinking_level,
            location=self.location,
            batch=batch,
            latency_ms=latency_ms,
            ok=ok,
            error_kind=error_kind,
            run_id=tags.run_id,
            item_ref=tags.item_ref,
            called_at=self.now(),
        ).priced()
        self.store.add(call)
        return call


def _estimate_tokens(contents: Any, config: Any) -> int:
    """A count on the high side, from the length of the text. Used for the worst case only."""

    def letters(value: Any) -> int:
        if isinstance(value, str):
            return len(value)
        if isinstance(value, (list, tuple)):
            return sum(letters(item) for item in value)
        return 0

    system = getattr(config, "system_instruction", None)
    return (letters(contents) + letters(system)) // _LETTERS_PER_TOKEN + 1


def _thinking_level(config: Any) -> str | None:
    level = getattr(getattr(config, "thinking_config", None), "thinking_level", None)
    if level is None:
        return None
    return str(getattr(level, "name", level))


def _count(meta: Any, name: str) -> int:
    return int(getattr(meta, name, None) or 0) if meta is not None else 0


class _MeteredModels:
    def __init__(self, models: Any, meter: Meter, tags: Tags, clock: Callable[[], float]) -> None:
        self._models = models
        self._meter = meter
        self._tags = tags
        self._clock = clock

    def _run(self, call: Callable[[], Any], record: Callable[[Any, int], None], model: str) -> Any:
        start = self._clock()
        try:
            response = call()
        except Exception as error:
            # The class of the error is kept, never its text: a text can repeat what was sent.
            self._meter.record(
                self._tags,
                model=model,
                input_tokens=0,
                latency_ms=int((self._clock() - start) * 1000),
                ok=False,
                error_kind=type(error).__name__,
            )
            raise
        record(response, int((self._clock() - start) * 1000))
        return response

    def generate_content(
        self, *, model: str, contents: Any, config: Any = None, **more: Any
    ) -> Any:
        limit = getattr(config, "max_output_tokens", None) or DEFAULT_MAX_OUTPUT_TOKENS
        self._meter.before_call(model, _estimate_tokens(contents, config), int(limit))

        def record(response: Any, latency_ms: int) -> None:
            meta = getattr(response, "usage_metadata", None)
            self._meter.record(
                self._tags,
                model=model,
                input_tokens=_count(meta, "prompt_token_count"),
                output_tokens=_count(meta, "candidates_token_count"),
                thinking_tokens=_count(meta, "thoughts_token_count"),
                cached_tokens=_count(meta, "cached_content_token_count"),
                thinking_level=_thinking_level(config),
                latency_ms=latency_ms,
            )

        return self._run(
            lambda: self._models.generate_content(
                model=model, contents=contents, config=config, **more
            ),
            record,
            model,
        )

    def embed_content(self, *, model: str, contents: Any, config: Any = None, **more: Any) -> Any:
        self._meter.before_call(model, _estimate_tokens(contents, None), 0)

        def record(response: Any, latency_ms: int) -> None:
            tokens = 0
            for answer in getattr(response, "embeddings", None) or []:
                tokens += _count(getattr(answer, "statistics", None), "token_count")
            self._meter.record(self._tags, model=model, input_tokens=tokens, latency_ms=latency_ms)

        return self._run(
            lambda: self._models.embed_content(
                model=model, contents=contents, config=config, **more
            ),
            record,
            model,
        )

    def __getattr__(self, name: str) -> Any:
        if name in _FREE_METHODS:
            return getattr(self._models, name)
        raise AttributeError(
            f"'{name}' is not counted by the meter. A call that costs money must be taught to "
            "finops/meter.py before it is used."
        )


class MeteredClient:
    """A Google client whose calls are all counted. Use it wherever a client is expected."""

    def __init__(
        self,
        client: Any,
        meter: Meter,
        tags: Tags,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._client = client
        self._meter = meter
        self._tags = tags
        self._clock = clock
        self.models = _MeteredModels(client.models, meter, tags, clock)

    @property
    def meter(self) -> Meter:
        return self._meter

    @property
    def tags(self) -> Tags:
        return self._tags

    def tagged(self, **changes: str | None) -> MeteredClient:
        """The same client and the same meter, for another purpose, run or item."""
        return MeteredClient(self._client, self._meter, replace(self._tags, **changes), self._clock)


def metered_client(
    settings: Any,
    purpose: str,
    *,
    client: Any = None,
    store: CallStore | None = None,
    run_id: str | None = None,
    item_ref: str | None = None,
) -> MeteredClient:
    """The Google client of the settings, counted, with the budget of the environment in use.

    This is the one door to the models. The ledger is the table llm_calls of the database, unless
    another store is given (a test gives a MemoryStore).
    """
    from hackathon_memory.finops.calls import PostgresStore
    from hackathon_memory.llm.client import make_client

    ledger = store if store is not None else PostgresStore(settings.database_conninfo())
    meter = Meter(
        ledger,
        settings.llm_environment,
        budget=budgets.from_settings(settings),
        location=settings.google_cloud_location or None,
    )
    real = client if client is not None else make_client(settings)
    return MeteredClient(real, meter, Tags(purpose=purpose, run_id=run_id, item_ref=item_ref))
