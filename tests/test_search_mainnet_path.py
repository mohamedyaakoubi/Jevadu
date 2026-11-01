"""The path of a project on the main network (search/mainnet_path.py): the order of its lines, and
its days against the event. Everything is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime

from hackathon_memory.check.mainnet_what import DEPLOYED
from hackathon_memory.search.mainnet_path import Own, Path, Step

DAY = datetime(2026, 3, 7, 10, tzinfo=UTC)


def own(ledger_id: str, kind: str, made_at: datetime | None) -> Own:
    return Own(ledger_id, ledger_id, kind, made_at, "0.0.7001", None, (), None, None, None)


def step(ledger_id: str, kind: str, what: str | None, name: str, first: datetime,
         count: int = 1) -> Step:  # fmt: skip
    return Step(ledger_id, kind, what, name, first, first, count, 0, True)


def path(owns: tuple[Own, ...], steps: tuple[Step, ...]) -> Path:
    return Path(1, "Pebble Pay", "Sample Event", datetime(2026, 3, 6, tzinfo=UTC),
                date(2026, 3, 8), owns, steps, (), 0, (), None, None)  # fmt: skip


def test_the_making_of_an_id_is_one_line_and_comes_first() -> None:
    contract = own("0.0.5002", "contract", DAY)
    topic = own("0.0.5001", "topic", DAY.replace(hour=9))  # its making is not among its moments
    deployed = step("0.0.5002", "contract", DEPLOYED, "ETHEREUMTRANSACTION", DAY)
    calls = step("0.0.5002", "contract", "launch", "ETHEREUMTRANSACTION", DAY, count=3)
    lines = path((contract, topic), (deployed, calls)).lines()
    assert [(line.own.ledger_id, line.made, line.step) for line in lines] == [
        ("0.0.5001", True, None),
        ("0.0.5002", True, deployed),
        ("0.0.5002", False, calls),
    ]


def test_an_id_that_is_a_transaction_is_one_line() -> None:
    one = own("0.0.7-1780000000-1", "transaction", DAY)
    transfer = step("0.0.7-1780000000-1", "transaction", None, "CRYPTOTRANSFER", DAY)
    (line,) = path((one,), (transfer,)).lines()
    assert line.made and line.step == transfer


def test_a_moment_is_before_during_or_after_the_days_of_the_event() -> None:
    one = path((), ())
    assert one.when(datetime(2026, 3, 5, tzinfo=UTC)) == "before"
    assert one.when(datetime(2026, 3, 8, 23, 59, tzinfo=UTC)) == "during"  # its last day, UTC
    assert one.when(datetime(2026, 3, 9, tzinfo=UTC)) == "after"
    assert one.days_after(datetime(2026, 3, 15, tzinfo=UTC)) == 7
    assert one.days_after(datetime(2026, 3, 7, tzinfo=UTC)) is None
    unknown = Path(1, "x", "y", None, None, (), (), (), 0, (), None, None)
    assert unknown.when(DAY) == "unknown" and unknown.days_after(DAY) is None
