"""Who made a project's own things (check/makers.py, design 7.5), with a stand-in mirror node.
Every ID, account and date is invented, except the shape of the node's answer (read on 29 October
2026)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from hackathon_memory.check.makers import (
    Earlier,
    Made,
    ask_maker,
    made_lines,
    maker_in,
    payer_of,
)

STARTS = datetime(2025, 10, 10, tzinfo=UTC)  # an invented event, as OmniShield's
TEAM, STRANGER = "0.0.7001", "0.0.3001"


class Node:
    """The transactions of one moment; `asked` keeps each question."""

    def __init__(self, transactions: list[dict]) -> None:
        self.transactions = transactions
        self.asked: list[tuple[datetime, datetime]] = []

    def transactions_at(self, since: datetime, until: datetime, *, limit: int = 25) -> list[dict]:
        del limit
        self.asked.append((since, until))
        return self.transactions


def test_the_payer_is_the_first_part_of_a_transaction_id() -> None:
    assert payer_of("0.0.10941897-1792665693-564781427") == "0.0.10941897"
    assert payer_of("") is None and payer_of("0.0.5") is None and payer_of("abc-1-2") is None


def test_the_maker_is_the_payer_of_the_transaction_that_made_the_thing() -> None:
    """The moment is asked a few microseconds wide, since the database keeps microseconds, and
    the transaction whose entity is the thing gives its payer."""
    made = datetime(2026, 10, 22, 6, 1, 42, 157973, tzinfo=UTC)
    node = Node([{"entity_id": "0.0.9", "transaction_id": "0.0.1-1792665693-1"},
                 {"entity_id": "0.0.11126502", "name": "CONSENSUSCREATETOPIC",
                  "transaction_id": "0.0.10941897-1792665693-564781427"}])  # fmt: skip
    assert ask_maker(node, "0.0.11126502", made) == "0.0.10941897"
    ((since, until),) = node.asked
    assert since < made < until and until - since <= timedelta(microseconds=4)
    assert ask_maker(Node([]), "0.0.11126502", made) is None


def test_a_history_that_holds_the_creation_gives_its_payer() -> None:
    made = datetime(2024, 2, 9, 10, 50, 5, tzinfo=UTC)
    events = [(made, STRANGER), (made + timedelta(days=7), TEAM)]
    assert maker_in(events, made) == STRANGER
    assert maker_in(events[1:], made) is None
    assert maker_in([(made, None)], made) is None


def test_who_made_its_things_is_said_by_account_and_the_one_made_long_before_stands_out() -> None:
    """The case of OmniShield: four contracts made during its event by one account, and one made
    20 months before by an account that made none of the others (29 October 2026)."""
    own = [Made(f"0.0.{n}", "contract", datetime(2025, 10, 17 + n, tzinfo=UTC), TEAM)
           for n in range(4)]  # fmt: skip
    oracle = Made("0xa2aa", "contract", datetime(2024, 2, 9, tzinfo=UTC), STRANGER)
    assert made_lines([*own, oracle], {TEAM}, STARTS) == (
        f"Its 4 contracts, from 17 to 20 October 2025: made by {TEAM}, an account that the "
        "project lists.",
        f"Its contract 0xa2aa, on 9 February 2024: made by {STRANGER}, an account that the "
        "project does not list.",
        "Its contract 0xa2aa was made 20 months before the event, by an account that made none of "
        "its other IDs: it may belong to someone else, such as a public service.",
    )  # fmt: skip


def test_nothing_stands_out_when_the_maker_is_listed_made_more_or_the_time_is_near() -> None:
    long_before = datetime(2023, 1, 5, tzinfo=UTC)
    topic = Made("0.0.5", "topic", long_before, TEAM)
    token = Made("0.0.6", "token", datetime(2025, 10, 11, tzinfo=UTC), STRANGER)
    assert len(made_lines([topic, token], {TEAM}, STARTS)) == 2  # listed: no line stands out
    both = [topic, Made("0.0.6", "token", datetime(2025, 10, 11, tzinfo=UTC), TEAM)]
    assert made_lines(both, set(), STARTS) == (
        f"Its 1 topic and 1 token, from 5 January 2023 to 11 October 2025: made by {TEAM}, an "
        "account that the project does not list.",
    )  # fmt: skip
    near = Made("0.0.7", "topic", STARTS - timedelta(days=20), STRANGER)
    assert len(made_lines([near], set(), STARTS)) == 1  # inside the 30 days before
    assert len(made_lines([topic], set(), None)) == 1  # the days of the event are not known


def test_a_lone_thing_made_long_before_and_one_whose_maker_is_not_known() -> None:
    lone = Made("0.0.5", "topic", datetime(2022, 6, 1, tzinfo=UTC), STRANGER)
    assert made_lines([lone], set(), STARTS)[-1] == (
        "Its topic 0.0.5 was made 3 years and 4 months before the event, by an account that the "
        "project does not list: it may belong to someone else, such as a public service."
    )  # fmt: skip
    unknown = Made("0.0.8", "token", datetime(2025, 10, 12, tzinfo=UTC), None)
    assert made_lines([unknown], set(), STARTS) == (
        "Its token 0.0.8, on 12 October 2025: who made it is not known.",
    )
    assert made_lines([], set(), STARTS) == ()


def test_a_thing_made_at_an_earlier_entry_of_the_same_code_says_so() -> None:
    """A team that came back: its token was made at its first event, five months before this one
    (YourTurn, 29 October 2026). It is not "someone else's"."""
    token = Made("0.0.6", "token", datetime(2025, 5, 2, tzinfo=UTC), STRANGER)
    first = Earlier("ETHGlobal Cannes 2025", datetime(2025, 4, 3, tzinfo=UTC), date(2025, 4, 5))
    assert made_lines([token], set(), STARTS, [first])[-1] == (
        "Its token 0.0.6 was made 5 months before the event, in the time of its earlier entry at "
        "ETHGlobal Cannes 2025, with the same code."
    )  # fmt: skip
    far = Earlier("ETHGlobal Prague 2024", datetime(2024, 5, 30, tzinfo=UTC), date(2024, 6, 2))
    assert "may belong to someone else" in made_lines([token], set(), STARTS, [far])[-1]
